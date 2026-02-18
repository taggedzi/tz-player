"""Embedded/sidecar artwork-to-ASCII visualizers with background processing."""

from __future__ import annotations

import atexit
import logging
import os
from collections import OrderedDict
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass
from importlib import import_module
from io import BytesIO
from pathlib import Path

from .base import VisualizerContext, VisualizerFrameInput

_ARTWORK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tz-artwork")
logger = logging.getLogger(__name__)


@atexit.register
def _shutdown_artwork_executor() -> None:
    _ARTWORK_EXECUTOR.shutdown(wait=False, cancel_futures=True)


@dataclass(frozen=True)
class ArtworkFingerprint:
    """File identity tuple used to invalidate cached artwork render output."""

    track_path: str
    mtime_ns: int
    size_bytes: int


@dataclass(frozen=True)
class AsciiArtFrame:
    """Color-aware ASCII frame laid out in row-major order."""

    width: int
    height: int
    chars: tuple[str, ...]
    colors: tuple[tuple[int, int, int] | None, ...]


@dataclass(frozen=True)
class ArtworkPayload:
    """Pipeline output containing either renderable art or placeholder message."""

    art: AsciiArtFrame | None
    message: str
    source: str | None = None


@dataclass(frozen=True)
class _BuildResult:
    fingerprint: ArtworkFingerprint | None
    payload: ArtworkPayload


@dataclass(frozen=True)
class _RenderRequest:
    track_path: str
    width: int
    height: int


@dataclass(frozen=True)
class _CacheKey:
    fingerprint: ArtworkFingerprint
    width: int
    height: int


_CHAR_RAMP = " .:-=+*#%@"
_CELL_HEIGHT_RATIO = 0.5
_SIDECAR_BASENAMES = ("cover", "folder", "front", "album", "artwork")
_SIDECAR_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
_MAX_SIDECAR_BYTES = 20 * 1024 * 1024


class ArtworkAsciiPipeline:
    """Loads embedded artwork in the background and caches ASCII frames."""

    def __init__(
        self,
        *,
        max_entries: int = 48,
        executor: Executor | None = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max_entries = max_entries
        self._executor = executor or _ARTWORK_EXECUTOR
        self._inflight: dict[_RenderRequest, Future[_BuildResult]] = {}
        self._cache: OrderedDict[_CacheKey, ArtworkPayload] = OrderedDict()
        self._latest_fp_by_path: dict[str, ArtworkFingerprint] = {}

    def get_payload(
        self,
        *,
        track_path: str | None,
        width: int,
        height: int,
    ) -> ArtworkPayload:
        """Return cached/pending/built payload for a track and viewport size."""
        if not track_path:
            return _placeholder("No track loaded", width, height)
        norm_path = _normalize_path(track_path)
        request = _RenderRequest(norm_path, max(1, width), max(1, height))
        cached = self._cached_payload(request)
        if cached is not None:
            return cached
        future = self._inflight.get(request)
        if future is None:
            self._inflight[request] = self._executor.submit(
                _build_ascii_payload,
                path=Path(track_path),
                width=request.width,
                height=request.height,
            )
            return _placeholder("Loading artwork...", request.width, request.height)
        if not future.done():
            return _placeholder("Loading artwork...", request.width, request.height)
        self._inflight.pop(request, None)
        try:
            result = future.result()
        except Exception:
            return _placeholder("Artwork decode failed", request.width, request.height)
        if result.fingerprint is not None:
            self._latest_fp_by_path[norm_path] = result.fingerprint
            self._cache_put(
                _CacheKey(result.fingerprint, request.width, request.height),
                result.payload,
            )
        return result.payload

    def _cached_payload(self, request: _RenderRequest) -> ArtworkPayload | None:
        fingerprint = self._latest_fp_by_path.get(request.track_path)
        if fingerprint is None:
            return None
        return self._cache.get(_CacheKey(fingerprint, request.width, request.height))

    def _cache_put(self, key: _CacheKey, value: ArtworkPayload) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
            return
        self._cache[key] = value
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)


_PIPELINE = ArtworkAsciiPipeline()


@dataclass
class CoverAsciiStaticVisualizer:
    """Static artwork visualizer rendering cached ASCII cover frames."""

    plugin_id: str = "cover.ascii.static"
    display_name: str = "Cover ASCII (Static)"
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        """Render centered static ASCII artwork or placeholder status text."""
        payload = _PIPELINE.get_payload(
            track_path=frame.track_path,
            width=max(1, frame.width),
            height=max(1, frame.height),
        )
        if payload.art is None:
            return payload.message
        return _render_art(
            payload.art,
            ansi_enabled=self._ansi_enabled,
            source=payload.source,
        )


@dataclass
class CoverAsciiMotionVisualizer:
    """Motion variant applying deterministic wipe/slide transforms per frame."""

    plugin_id: str = "cover.ascii.motion"
    display_name: str = "Cover ASCII (Motion)"
    _ansi_enabled: bool = True

    def on_activate(self, context: VisualizerContext) -> None:
        self._ansi_enabled = context.ansi_enabled

    def on_deactivate(self) -> None:
        return None

    def render(self, frame: VisualizerFrameInput) -> str:
        """Render animated artwork only while playing; otherwise render static."""
        payload = _PIPELINE.get_payload(
            track_path=frame.track_path,
            width=max(1, frame.width),
            height=max(1, frame.height),
        )
        if payload.art is None:
            return payload.message
        if frame.status != "playing":
            return _render_art(
                payload.art,
                ansi_enabled=self._ansi_enabled,
                source=payload.source,
            )
        animated = _animate_art(payload.art, frame.frame_index)
        return _render_art(
            animated,
            ansi_enabled=self._ansi_enabled,
            source=payload.source,
        )


def _build_ascii_payload(*, path: Path, width: int, height: int) -> _BuildResult:
    """Build ASCII payload from embedded art, then sidecar art as fallback."""
    fingerprint = _fingerprint(path)
    if fingerprint is None:
        return _BuildResult(
            None,
            _placeholder("Track missing", width, height),
        )
    image_bytes = _extract_embedded_art_bytes(path)
    source = "embedded"
    if image_bytes is None:
        image_bytes = _extract_sidecar_art_bytes(path)
        source = "sidecar"
    if image_bytes is None:
        return _BuildResult(
            fingerprint,
            _placeholder("No embedded/sidecar artwork", width, height),
        )
    art = _image_bytes_to_ascii_frame(image_bytes, width=width, height=height)
    if art is None:
        return _BuildResult(
            fingerprint,
            _placeholder("Artwork decode failed", width, height),
        )
    return _BuildResult(
        fingerprint,
        ArtworkPayload(art=art, message="", source=source),
    )


def _extract_embedded_art_bytes(path: Path) -> bytes | None:
    """Best-effort extraction of embedded artwork bytes via TinyTag."""
    try:
        tinytag_module = import_module("tinytag")
        TinyTag = tinytag_module.TinyTag
        tag = TinyTag.get(str(path), image=True, ignore_errors=True)
    except Exception as exc:
        logger.debug("tinytag artwork extraction failed for %s: %s", path, exc)
        return None
    images = getattr(tag, "images", None)
    if images is not None:
        any_image = getattr(images, "any", None)
        data = _as_bytes(getattr(any_image, "data", None))
        if data:
            return data
        as_dict = getattr(images, "as_dict", None)
        if callable(as_dict):
            try:
                for image_list in as_dict().values():
                    if not isinstance(image_list, list):
                        continue
                    for image in image_list:
                        data = _as_bytes(getattr(image, "data", None))
                        if data:
                            return data
            except Exception:
                logger.debug("tinytag image map parsing failed for %s", path)
    get_image = getattr(tag, "get_image", None)
    if callable(get_image):
        try:
            data = get_image()
        except Exception:
            return None
        out = _as_bytes(data)
        if out:
            return out
    return None


def _as_bytes(value: object) -> bytes | None:
    if isinstance(value, bytes):
        return value or None
    if isinstance(value, bytearray):
        return bytes(value) if value else None
    if isinstance(value, memoryview):
        out = value.tobytes()
        return out or None
    return None


def _extract_sidecar_art_bytes(track_path: Path) -> bytes | None:
    """Find and load nearby cover-art sidecar files in priority order."""
    directory = track_path.parent
    if not directory.exists() or not directory.is_dir():
        return None
    file_map: dict[str, Path] = {}
    try:
        for item in directory.iterdir():
            if not item.is_file():
                continue
            file_map[item.name.lower()] = item
    except OSError:
        return None
    ordered_names: list[str] = []
    for basename in _SIDECAR_BASENAMES:
        for ext in _SIDECAR_EXTENSIONS:
            ordered_names.append(f"{basename}{ext}")
    stem = track_path.stem.lower()
    for ext in _SIDECAR_EXTENSIONS:
        ordered_names.append(f"{stem}{ext}")
    for name in ordered_names:
        sidecar = file_map.get(name)
        if sidecar is None:
            continue
        payload = _safe_read_sidecar(sidecar)
        if payload:
            return payload
    return None


def _safe_read_sidecar(path: Path) -> bytes | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    if stat.st_size <= 0 or stat.st_size > _MAX_SIDECAR_BYTES:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data or None


def _image_bytes_to_ascii_frame(
    image_bytes: bytes,
    *,
    width: int,
    height: int,
) -> AsciiArtFrame | None:
    """Decode image bytes and map pixels into a centered ASCII color frame."""
    try:
        image_module = import_module("PIL.Image")
        resample = getattr(image_module, "Resampling", None)
        resample_method = (
            resample.BICUBIC if resample is not None else image_module.BICUBIC
        )
    except Exception:
        return None
    try:
        image = image_module.open(BytesIO(image_bytes))
        image = image.convert("RGB")
    except Exception:
        return None
    src_width, src_height = image.size
    if src_width <= 0 or src_height <= 0:
        return None
    target_width, target_height = _scaled_size(
        src_width=src_width,
        src_height=src_height,
        max_width=max(1, width),
        max_height=max(1, height),
    )
    resized = image.resize((target_width, target_height), resample=resample_method)
    pixels = resized.load()

    chars: list[str] = []
    colors: list[tuple[int, int, int] | None] = []
    for y in range(target_height):
        for x in range(target_width):
            r, g, b = pixels[x, y]
            brightness = int(round((0.2126 * r) + (0.7152 * g) + (0.0722 * b)))
            idx = int((brightness / 255.0) * (len(_CHAR_RAMP) - 1))
            chars.append(_CHAR_RAMP[idx])
            colors.append((r, g, b))
    return _center_ascii_frame(
        art_width=target_width,
        art_height=target_height,
        canvas_width=max(1, width),
        canvas_height=max(1, height),
        chars=chars,
        colors=colors,
    )


def _scaled_size(
    *,
    src_width: int,
    src_height: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int]:
    # Fit inside the pane while preserving source aspect ratio.
    # Terminal glyphs are taller than wide, so we compensate with cell height ratio.
    source_ratio = src_width / max(1.0, src_height * _CELL_HEIGHT_RATIO)
    pane_ratio = max_width / max(1, max_height)
    if pane_ratio >= source_ratio:
        out_height = max_height
        out_width = int(round(out_height * source_ratio))
    else:
        out_width = max_width
        out_height = int(round(out_width / source_ratio))
    out_width = max(1, min(max_width, out_width))
    out_height = max(1, min(max_height, out_height))
    return out_width, out_height


def _center_ascii_frame(
    *,
    art_width: int,
    art_height: int,
    canvas_width: int,
    canvas_height: int,
    chars: list[str],
    colors: list[tuple[int, int, int] | None],
) -> AsciiArtFrame:
    left_pad = max(0, (canvas_width - art_width) // 2)
    top_pad = max(0, (canvas_height - art_height) // 2)
    canvas_chars = [" "] * (canvas_width * canvas_height)
    canvas_colors: list[tuple[int, int, int] | None] = [None] * (
        canvas_width * canvas_height
    )
    for y in range(art_height):
        for x in range(art_width):
            src_idx = (y * art_width) + x
            dst_x = x + left_pad
            dst_y = y + top_pad
            if dst_x >= canvas_width or dst_y >= canvas_height:
                continue
            dst_idx = (dst_y * canvas_width) + dst_x
            canvas_chars[dst_idx] = chars[src_idx]
            canvas_colors[dst_idx] = colors[src_idx]
    return AsciiArtFrame(
        width=canvas_width,
        height=canvas_height,
        chars=tuple(canvas_chars),
        colors=tuple(canvas_colors),
    )


def _render_art(art: AsciiArtFrame, *, ansi_enabled: bool, source: str | None) -> str:
    """Render ASCII frame, optionally with per-cell ANSI truecolor escapes."""
    del source
    lines: list[str] = []
    width = art.width
    for y in range(art.height):
        parts: list[str] = []
        for x in range(width):
            idx = (y * width) + x
            ch = art.chars[idx]
            color = art.colors[idx]
            if ansi_enabled and color is not None and ch != " ":
                r, g, b = color
                parts.append(f"\x1b[38;2;{r};{g};{b}m{ch}\x1b[0m")
            else:
                parts.append(ch)
        lines.append("".join(parts))
    return "\n".join(lines)


def _animate_art(art: AsciiArtFrame, frame_index: int) -> AsciiArtFrame:
    """Alternate between wipe and slide effects on a deterministic schedule."""
    mode = (frame_index // 30) % 2
    if mode == 0:
        return _wipe_effect(art, frame_index=frame_index)
    return _slide_effect(art, frame_index=frame_index)


def _wipe_effect(art: AsciiArtFrame, *, frame_index: int) -> AsciiArtFrame:
    progress = _triangle_progress(frame_index=frame_index, period=32)
    visible_rows = int(round(progress * art.height))
    chars = list(art.chars)
    colors = list(art.colors)
    for y in range(art.height):
        if y < visible_rows:
            continue
        row_start = y * art.width
        row_end = row_start + art.width
        chars[row_start:row_end] = [" "] * art.width
        colors[row_start:row_end] = [None] * art.width
    return AsciiArtFrame(
        width=art.width,
        height=art.height,
        chars=tuple(chars),
        colors=tuple(colors),
    )


def _slide_effect(art: AsciiArtFrame, *, frame_index: int) -> AsciiArtFrame:
    phase = _signed_wave(frame_index=frame_index, period=40)
    max_shift = max(1, art.width // 5)
    offset = int(round(phase * max_shift))
    chars = [" "] * (art.width * art.height)
    colors: list[tuple[int, int, int] | None] = [None] * (art.width * art.height)
    for y in range(art.height):
        row_offset = offset if y % 2 == 0 else -offset
        for x in range(art.width):
            src_x = x - row_offset
            if src_x < 0 or src_x >= art.width:
                continue
            src_idx = (y * art.width) + src_x
            dst_idx = (y * art.width) + x
            chars[dst_idx] = art.chars[src_idx]
            colors[dst_idx] = art.colors[src_idx]
    return AsciiArtFrame(
        width=art.width,
        height=art.height,
        chars=tuple(chars),
        colors=tuple(colors),
    )


def _placeholder(message: str, width: int, height: int) -> ArtworkPayload:
    """Create centered placeholder text block for unavailable/loading artwork."""
    lines = [" " * max(1, width) for _ in range(max(1, height))]
    row = max(0, min(len(lines) - 1, height // 2))
    text = message[: max(1, width)]
    left = max(0, (width - len(text)) // 2)
    line = lines[row]
    lines[row] = f"{line[:left]}{text}{line[left + len(text) :]}"
    return ArtworkPayload(art=None, message="\n".join(lines))


def _normalize_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _fingerprint(path: Path) -> ArtworkFingerprint | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return ArtworkFingerprint(
        track_path=_normalize_path(str(path)),
        mtime_ns=int(stat.st_mtime_ns),
        size_bytes=int(stat.st_size),
    )


def _triangle_progress(*, frame_index: int, period: int) -> float:
    phase = (frame_index % max(2, period)) / max(1, period)
    return 1.0 - abs((2.0 * phase) - 1.0)


def _signed_wave(*, frame_index: int, period: int) -> float:
    phase = (frame_index % max(2, period)) / max(1, period)
    return (2.0 * phase) - 1.0

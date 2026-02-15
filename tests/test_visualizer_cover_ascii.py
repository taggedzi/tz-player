"""Tests for embedded-cover ASCII visualizers."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path

from tz_player.visualizers.base import VisualizerContext, VisualizerFrameInput
from tz_player.visualizers.cover_ascii import (
    ArtworkAsciiPipeline,
    ArtworkFingerprint,
    ArtworkPayload,
    AsciiArtFrame,
    CoverAsciiMotionVisualizer,
    CoverAsciiStaticVisualizer,
    _build_ascii_payload,
    _BuildResult,
    _extract_embedded_art_bytes,
    _extract_sidecar_art_bytes,
)
from tz_player.visualizers.registry import VisualizerRegistry


def _frame(
    *,
    width: int = 20,
    height: int = 6,
    frame_index: int = 0,
    status: str = "playing",
    track_path: str | None = "/tmp/song.mp3",
) -> VisualizerFrameInput:
    return VisualizerFrameInput(
        frame_index=frame_index,
        monotonic_s=0.0,
        width=width,
        height=height,
        status=status,
        position_s=10.0,
        duration_s=100.0,
        volume=80.0,
        speed=1.0,
        repeat_mode="OFF",
        shuffle=False,
        track_id=1,
        track_path=track_path,
        title="Track",
        artist="Artist",
        album="Album",
    )


@dataclass
class _FakePipeline:
    payload: ArtworkPayload

    def get_payload(
        self,
        *,
        track_path: str | None,
        width: int,
        height: int,
    ) -> ArtworkPayload:
        del track_path, width, height
        return self.payload


class _PendingExecutor:
    def __init__(self, future: Future[_BuildResult]) -> None:
        self.future = future
        self.calls = 0

    def submit(self, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        del fn, args, kwargs
        self.calls += 1
        return self.future


def _art(width: int = 6, height: int = 3) -> AsciiArtFrame:
    chars: list[str] = []
    colors: list[tuple[int, int, int] | None] = []
    for y in range(height):
        for x in range(width):
            chars.append("#" if (x + y) % 2 == 0 else ".")
            colors.append((120 + x, 50 + y, 200 - x))
    return AsciiArtFrame(
        width=width,
        height=height,
        chars=tuple(chars),
        colors=tuple(colors),
    )


def test_cover_ascii_plugins_are_registered_built_in() -> None:
    registry = VisualizerRegistry.built_in()
    assert registry.has_plugin("cover.ascii.static")
    assert registry.has_plugin("cover.ascii.motion")


def test_static_plugin_renders_placeholder_when_no_track(monkeypatch) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    plugin = CoverAsciiStaticVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    monkeypatch.setattr(
        cover_module,
        "_PIPELINE",
        _FakePipeline(payload=ArtworkPayload(art=None, message="No track loaded")),
    )
    output = plugin.render(_frame(track_path=None))
    assert "No track loaded" in output


def test_static_plugin_renders_art_and_ansi(monkeypatch) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    plugin = CoverAsciiStaticVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=True, unicode_enabled=True))
    monkeypatch.setattr(
        cover_module,
        "_PIPELINE",
        _FakePipeline(
            payload=ArtworkPayload(art=_art(), message="", source="embedded")
        ),
    )
    output = plugin.render(_frame(width=6, height=3))
    assert "\x1b[38;2;" in output
    assert len(output.splitlines()) == 3


def test_motion_plugin_changes_frames_while_playing(monkeypatch) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    plugin = CoverAsciiMotionVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    monkeypatch.setattr(
        cover_module,
        "_PIPELINE",
        _FakePipeline(
            payload=ArtworkPayload(
                art=_art(width=10, height=4),
                message="",
                source="sidecar",
            )
        ),
    )
    out1 = plugin.render(_frame(width=10, height=4, frame_index=5, status="playing"))
    out2 = plugin.render(_frame(width=10, height=4, frame_index=24, status="playing"))
    assert out1 != out2


def test_motion_plugin_is_static_when_paused(monkeypatch) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    plugin = CoverAsciiMotionVisualizer()
    plugin.on_activate(VisualizerContext(ansi_enabled=False, unicode_enabled=True))
    monkeypatch.setattr(
        cover_module,
        "_PIPELINE",
        _FakePipeline(payload=ArtworkPayload(art=_art(width=8, height=3), message="")),
    )
    out1 = plugin.render(_frame(width=8, height=3, frame_index=3, status="paused"))
    out2 = plugin.render(_frame(width=8, height=3, frame_index=30, status="paused"))
    assert out1 == out2


def test_pipeline_returns_loading_without_blocking() -> None:
    pending: Future[_BuildResult] = Future()
    executor = _PendingExecutor(pending)
    pipeline = ArtworkAsciiPipeline(executor=executor)
    payload = pipeline.get_payload(track_path="/tmp/song.mp3", width=20, height=6)
    assert executor.calls == 1
    assert payload.art is None
    assert "Loading artwork..." in payload.message


def test_pipeline_caches_completed_result(monkeypatch, tmp_path: Path) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    track = tmp_path / "song.mp3"
    track.write_bytes(b"placeholder")

    fingerprint = ArtworkFingerprint(
        track_path=str(track),
        mtime_ns=1,
        size_bytes=2,
    )
    art_payload = ArtworkPayload(art=_art(width=4, height=2), message="")
    monkeypatch.setattr(
        cover_module,
        "_build_ascii_payload",
        lambda *, path, width, height: _BuildResult(fingerprint, art_payload),
    )
    pipeline = ArtworkAsciiPipeline()

    first = pipeline.get_payload(track_path=str(track), width=12, height=4)
    second = pipeline.get_payload(track_path=str(track), width=12, height=4)
    assert first.art is None
    assert second.art is not None


def test_extract_embedded_art_bytes_uses_images_any(
    monkeypatch, tmp_path: Path
) -> None:
    class _Image:
        data = b"abc"

    class _Images:
        any = _Image()

    class _Tag:
        images = _Images()

    class _TinyTag:
        @staticmethod
        def get(path, image=False, ignore_errors=None):  # type: ignore[no-untyped-def]
            del path, image, ignore_errors
            return _Tag()

    class _Module:
        TinyTag = _TinyTag

    monkeypatch.setattr(
        "tz_player.visualizers.cover_ascii.import_module",
        lambda name: _Module(),
    )
    track = tmp_path / "song.mp3"
    track.write_bytes(b"")
    assert _extract_embedded_art_bytes(track) == b"abc"


def test_extract_embedded_art_bytes_returns_none_without_images(
    monkeypatch, tmp_path: Path
) -> None:
    class _Tag:
        images = None

    class _TinyTag:
        @staticmethod
        def get(path, image=False, ignore_errors=None):  # type: ignore[no-untyped-def]
            del path, image, ignore_errors
            return _Tag()

    class _Module:
        TinyTag = _TinyTag

    monkeypatch.setattr(
        "tz_player.visualizers.cover_ascii.import_module",
        lambda name: _Module(),
    )
    track = tmp_path / "song.mp3"
    track.write_bytes(b"")
    assert _extract_embedded_art_bytes(track) is None


def test_extract_embedded_art_bytes_accepts_memoryview_payload(
    monkeypatch, tmp_path: Path
) -> None:
    class _Image:
        data = memoryview(b"abc")

    class _Images:
        any = _Image()

    class _Tag:
        images = _Images()

    class _TinyTag:
        @staticmethod
        def get(path, image=False, ignore_errors=None):  # type: ignore[no-untyped-def]
            del path, image, ignore_errors
            return _Tag()

    class _Module:
        TinyTag = _TinyTag

    monkeypatch.setattr(
        "tz_player.visualizers.cover_ascii.import_module",
        lambda name: _Module(),
    )
    track = tmp_path / "song.mp3"
    track.write_bytes(b"")
    assert _extract_embedded_art_bytes(track) == b"abc"


def test_extract_embedded_art_bytes_uses_images_dict_when_any_missing(
    monkeypatch, tmp_path: Path
) -> None:
    class _Image:
        data = bytearray(b"xyz")

    class _Images:
        any = None

        @staticmethod
        def as_dict() -> dict[str, list[object]]:
            return {"front_cover": [_Image()]}

    class _Tag:
        images = _Images()

    class _TinyTag:
        @staticmethod
        def get(path, image=False, ignore_errors=None):  # type: ignore[no-untyped-def]
            del path, image, ignore_errors
            return _Tag()

    class _Module:
        TinyTag = _TinyTag

    monkeypatch.setattr(
        "tz_player.visualizers.cover_ascii.import_module",
        lambda name: _Module(),
    )
    track = tmp_path / "song.mp3"
    track.write_bytes(b"")
    assert _extract_embedded_art_bytes(track) == b"xyz"


def test_build_ascii_payload_returns_decode_failed_for_invalid_image(
    monkeypatch, tmp_path: Path
) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    track = tmp_path / "song.mp3"
    track.write_bytes(b"payload")

    monkeypatch.setattr(
        cover_module,
        "_extract_embedded_art_bytes",
        lambda path: b"not-image",
    )
    monkeypatch.setattr(
        cover_module,
        "_image_bytes_to_ascii_frame",
        lambda image_bytes, *, width, height: None,
    )
    result = _build_ascii_payload(path=track, width=20, height=6)
    assert result.fingerprint is not None
    assert result.payload.art is None
    assert "Artwork decode fail" in result.payload.message


def test_extract_sidecar_art_bytes_prefers_cover_name(tmp_path: Path) -> None:
    music_dir = tmp_path / "album"
    music_dir.mkdir()
    track = music_dir / "song.mp3"
    track.write_bytes(b"audio")
    (music_dir / "folder.jpg").write_bytes(b"folder")
    (music_dir / "cover.png").write_bytes(b"cover")

    assert _extract_sidecar_art_bytes(track) == b"cover"


def test_extract_sidecar_art_bytes_supports_track_stem_name(tmp_path: Path) -> None:
    music_dir = tmp_path / "album"
    music_dir.mkdir()
    track = music_dir / "my-song.flac"
    track.write_bytes(b"audio")
    (music_dir / "my-song.jpeg").write_bytes(b"stem")

    assert _extract_sidecar_art_bytes(track) == b"stem"


def test_build_ascii_payload_uses_sidecar_when_embedded_missing(
    monkeypatch, tmp_path: Path
) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    track = tmp_path / "song.mp3"
    track.write_bytes(b"audio")

    monkeypatch.setattr(cover_module, "_extract_embedded_art_bytes", lambda path: None)
    monkeypatch.setattr(
        cover_module,
        "_extract_sidecar_art_bytes",
        lambda path: b"sidecar-image",
    )
    monkeypatch.setattr(
        cover_module,
        "_image_bytes_to_ascii_frame",
        lambda image_bytes, *, width, height: _art(width=6, height=3),
    )
    result = _build_ascii_payload(path=track, width=20, height=6)
    assert result.payload.art is not None


def test_build_ascii_payload_reports_no_embedded_or_sidecar_when_missing(
    monkeypatch, tmp_path: Path
) -> None:
    import tz_player.visualizers.cover_ascii as cover_module

    track = tmp_path / "song.mp3"
    track.write_bytes(b"audio")
    monkeypatch.setattr(cover_module, "_extract_embedded_art_bytes", lambda path: None)
    monkeypatch.setattr(cover_module, "_extract_sidecar_art_bytes", lambda path: None)

    result = _build_ascii_payload(path=track, width=40, height=6)
    assert result.payload.art is None
    assert "No embedded/sidecar artwork" in result.payload.message

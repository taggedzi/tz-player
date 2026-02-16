"""Tree picker modal for selecting one or more local audio files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList
from textual.widgets.option_list import Option

from tz_player.media_formats import VLC_AUDIO_EXTENSIONS
from tz_player.utils.async_utils import run_blocking


@dataclass(frozen=True)
class TreeEntry:
    path: Path
    label: str
    is_dir: bool


class FileTreePickerModal(ModalScreen):
    """Modal for tree navigation and multi-file selection."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "open_or_toggle", "Open/Select"),
        ("space", "toggle_selected", "Toggle"),
        ("backspace", "up_directory", "Up"),
        ("ctrl+r", "show_roots", "Drives"),
        ("ctrl+s", "submit", "Add"),
    ]

    def __init__(self, title: str = "Add files") -> None:
        super().__init__()
        self._title = title
        self._current_dir: Path | None = None
        self._entries: list[TreeEntry] = []
        self._selected_paths: set[Path] = set()
        self._path_label = Label("", id="file-tree-current-path")
        self._hint_label = Label("", id="file-tree-hint")
        self._list = OptionList(id="file-tree-options")
        self._add_button = Button("Add selected", id="add")

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self._title),
            self._path_label,
            self._hint_label,
            self._list,
            Horizontal(
                self._add_button,
                Button("Cancel", id="cancel"),
            ),
            id="modal-body",
        )

    async def on_mount(self) -> None:
        self._list.focus()
        await self._show_roots()

    async def action_show_roots(self) -> None:
        await self._show_roots()

    async def action_up_directory(self) -> None:
        if self._current_dir is None:
            return
        parent = self._current_dir.parent
        if parent == self._current_dir:
            await self._show_roots()
            return
        await self._load_dir(parent)

    async def action_open_or_toggle(self) -> None:
        entry = self._highlighted_entry()
        if entry is None:
            return
        if entry.is_dir:
            await self._load_dir(entry.path)
            return
        self._toggle_path(entry.path)

    async def action_toggle_selected(self) -> None:
        entry = self._highlighted_entry()
        if entry is None or entry.is_dir:
            return
        self._toggle_path(entry.path)

    def action_submit(self) -> None:
        if not self._selected_paths:
            return
        self.dismiss(sorted(self._selected_paths, key=lambda path: str(path).lower()))

    def action_cancel(self) -> None:
        self.dismiss(None)

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        del event
        await self.action_open_or_toggle()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add":
            self.action_submit()
        elif event.button.id == "cancel":
            self.action_cancel()

    async def _show_roots(self) -> None:
        self._current_dir = None
        self._entries = await run_blocking(_list_roots)
        self._refresh_options()
        self._update_labels()

    async def _load_dir(self, directory: Path) -> None:
        self._current_dir = directory
        self._entries = await run_blocking(_list_directory_entries, directory)
        self._refresh_options()
        self._update_labels()

    def _refresh_options(self) -> None:
        options = [
            Option(
                _entry_prompt(entry, selected=entry.path in self._selected_paths),
                id=str(index),
            )
            for index, entry in enumerate(self._entries)
        ]
        self._list.set_options(options)
        self._add_button.disabled = not self._selected_paths

    def _update_labels(self) -> None:
        location = (
            "Drives / roots" if self._current_dir is None else str(self._current_dir)
        )
        selected = len(self._selected_paths)
        self._path_label.update(f"Location: {location}")
        self._hint_label.update(
            f"Selected: {selected} | Enter=open/toggle | Space=toggle | Ctrl+S=add | Ctrl+R=drives"
        )

    def _toggle_path(self, path: Path) -> None:
        if path in self._selected_paths:
            self._selected_paths.remove(path)
        else:
            self._selected_paths.add(path)
        self._refresh_options()
        self._update_labels()

    def _highlighted_entry(self) -> TreeEntry | None:
        index = self._list.highlighted
        if index is None:
            return None
        if not (0 <= index < len(self._entries)):
            return None
        return self._entries[index]


def _entry_prompt(entry: TreeEntry, *, selected: bool) -> str:
    if entry.is_dir:
        return f"[DIR] {entry.label}"
    marker = "[x]" if selected else "[ ]"
    return f"{marker} {entry.label}"


def _list_roots() -> list[TreeEntry]:
    roots: list[Path]
    if os.name == "nt":
        roots = [Path(f"{drive}:\\") for drive in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        roots = [root for root in roots if root.exists()]
    else:
        roots = [Path("/")]
    roots.sort(key=lambda path: str(path).lower())
    return [
        TreeEntry(path=root, label=_display_name(root, is_dir=True), is_dir=True)
        for root in roots
    ]


def _list_directory_entries(directory: Path) -> list[TreeEntry]:
    entries: list[TreeEntry] = []
    if not directory.exists() or not directory.is_dir():
        return entries
    parent = directory.parent
    if parent != directory:
        entries.append(TreeEntry(path=parent, label="..", is_dir=True))
    try:
        with os.scandir(directory) as listing:
            dirs: list[TreeEntry] = []
            files: list[TreeEntry] = []
            for item in listing:
                path = Path(item.path)
                if item.is_dir(follow_symlinks=False):
                    dirs.append(
                        TreeEntry(
                            path=path,
                            label=_display_name(path, is_dir=True),
                            is_dir=True,
                        )
                    )
                    continue
                if not item.is_file(follow_symlinks=False):
                    continue
                if path.suffix.lower() not in VLC_AUDIO_EXTENSIONS:
                    continue
                files.append(
                    TreeEntry(
                        path=path, label=_display_name(path, is_dir=False), is_dir=False
                    )
                )
    except OSError:
        return entries
    dirs.sort(key=lambda entry: entry.label.lower())
    files.sort(key=lambda entry: entry.label.lower())
    entries.extend(dirs)
    entries.extend(files)
    return entries


def _display_name(path: Path, *, is_dir: bool) -> str:
    name = path.name or str(path)
    return f"{name}/" if is_dir and name != ".." else name

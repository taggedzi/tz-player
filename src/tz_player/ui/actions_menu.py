"""Overlay actions menu for playlist header."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.geometry import Region
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option
from textual.widget import Widget
from tz_player.ui.text_button import TextButton


class ActionsMenuButton(TextButton):
    def __init__(self, **kwargs) -> None:
        super().__init__("Actions ▾", action="actions_menu", **kwargs)


class ActionsMenuSelected(Message):
    bubble = True

    def __init__(self, action: str) -> None:
        super().__init__()
        self.action = action


class ActionsMenuDismissed(Message):
    bubble = True


class ActionsMenuPopup(Widget):
    DEFAULT_CSS = """
    ActionsMenuPopup {
        position: absolute;
        layer: overlay;
        background: transparent;
    }

    #actions-menu {
        position: absolute;
        border: solid $primary;
        background: $panel;
        color: $text;
        text-wrap: nowrap;
        overflow: hidden;
    }
    """

    def __init__(self, anchor: Region, **kwargs) -> None:
        super().__init__(**kwargs)
        self._anchor = anchor
        self._menu = OptionList(
            Option("Add files...", id="add_files"),
            Option("Add folder...", id="add_folder"),
            Option("Remove selected", id="remove_selected"),
            Option("Clear playlist", id="clear_playlist"),
            Option("Refresh metadata (selected)", id="refresh_metadata_selected"),
            Option("Refresh metadata (all)", id="refresh_metadata_all"),
            id="actions-menu",
        )
        self._menu_region = Region(0, 0, 0, 0)

    @property
    def menu_region(self) -> Region:
        return self._menu_region

    def compose(self) -> ComposeResult:
        yield self._menu

    def on_mount(self) -> None:
        self._place_menu()
        self._menu.focus()

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        option_id = event.option.id
        if option_id is not None:
            self.post_message(ActionsMenuSelected(str(option_id)))
        self.dismiss()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss()
            event.stop()

    def dismiss(self) -> None:
        self.post_message(ActionsMenuDismissed())
        self.remove()

    def _place_menu(self) -> None:
        labels = [option.prompt for option in self._menu.options]
        max_label = max((len(str(label)) for label in labels), default=10)
        menu_width = min(max_label + 4, max(12, self.app.size.width - 2))
        menu_height = min(len(labels), max(4, self.app.size.height - 2))
        screen_width = self.app.size.width
        screen_height = self.app.size.height
        anchor_x = self._anchor.x
        anchor_y = self._anchor.y
        anchor_h = self._anchor.height
        x = min(max(0, anchor_x), max(0, screen_width - menu_width))
        below_y = anchor_y + anchor_h
        above_y = anchor_y - menu_height
        if below_y + menu_height <= screen_height:
            y = below_y
        elif above_y >= 0:
            y = above_y
        else:
            y = max(0, screen_height - menu_height)
        self.styles.width = menu_width
        self.styles.height = menu_height
        self.styles.offset = (x, y)
        self._menu.styles.width = "100%"
        self._menu.styles.height = "100%"
        self._menu.styles.offset = (0, 0)
        self._menu_region = Region(x, y, menu_width, menu_height)

    def contains_point(self, x: int, y: int) -> bool:
        return (
            self._menu_region.x <= x < self._menu_region.right
            and self._menu_region.y <= y < self._menu_region.bottom
        )

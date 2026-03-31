"""Message and thread action pickers for local-first mutations."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, SelectionList, Static
from textual.widgets.selection_list import Selection

from shmail.config import settings
from shmail.widgets.shortcuts import binding_choices_label, movement_pair_label


class MoveDestinationItem(ListItem):
    """List row representing one move destination."""

    def __init__(self, label_id: str, display_name: str) -> None:
        super().__init__()
        self.label_id = label_id
        self.display_name = display_name

    def compose(self) -> ComposeResult:
        yield Static(self.display_name, markup=False)


class LabelSelectionScreen(ModalScreen[list[str] | None]):
    """Multi-select picker for mailbox markers and user labels."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close", show=False),
        Binding(settings.keybindings.select, "toggle_selection", "Toggle", show=False),
        Binding("ctrl+enter", "apply", "Apply", show=False),
    ]

    def __init__(
        self,
        selected_label_ids: list[str],
        *,
        title: str = "Labels",
        warning: str = "",
    ) -> None:
        super().__init__(id="label-selection-screen")
        self.selected_label_ids = set(selected_label_ids)
        self._dialog_title = title
        self._dialog_warning = warning

    def compose(self) -> ComposeResult:
        labels = getattr(self.app, "message_mutation").list_mutable_label_choices()  # type: ignore[attr-defined]
        options = []
        for label in labels:
            label_id = str(label.get("id") or "")
            name = str(label.get("name") or label_id)
            options.append(
                Selection(
                    name.split("/")[-1],
                    label_id,
                    initial_state=label_id in self.selected_label_ids,
                )
            )

        with Vertical(id="message-action-modal"):
            yield Static(self._dialog_title, id="message-action-title")
            yield Static(
                self._dialog_warning
                or "Toggle mailbox markers and user labels locally.",
                id="message-action-body",
                markup=False,
            )
            yield SelectionList[str](*options, id="message-label-selection-list")
            with Horizontal(id="message-action-shortcuts"):
                yield Static(
                    binding_choices_label(settings.keybindings.select, "ENTER"),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Toggle", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static("Ctrl+Enter", classes="shortcut-key", markup=False)
                yield Static("Apply", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static(
                    movement_pair_label(
                        settings.keybindings.up, settings.keybindings.down
                    ),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Move", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static(
                    binding_choices_label(settings.keybindings.close, "Q/ESC"),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Close", classes="shortcut-label", markup=False)

    def on_mount(self) -> None:
        selection_list = self.query_one("#message-label-selection-list", SelectionList)
        for label_id in sorted(self.selected_label_ids):
            try:
                selection_list.select(label_id)
            except Exception:
                continue
        selection_list.focus()

    def action_toggle_selection(self) -> None:
        """Toggle the highlighted label selection."""
        selection_list = self.query_one("#message-label-selection-list", SelectionList)
        highlighted = int(selection_list.highlighted or 0)
        option = selection_list.get_option_at_index(highlighted)
        selection_list.toggle(option.value)

    def action_apply(self) -> None:
        selection_list = self.query_one("#message-label-selection-list", SelectionList)
        self.dismiss([str(item) for item in selection_list.selected])

    def action_close(self) -> None:
        self.dismiss(None)


class MoveSelectionScreen(ModalScreen[str | None]):
    """Single-destination picker for provider-agnostic move actions."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close", show=False),
        Binding(settings.keybindings.up, "cursor_up", "Previous", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next", show=False),
        Binding(
            settings.keybindings.select, "select_destination", "Select", show=False
        ),
    ]

    def __init__(self, current_view_label_id: str | None) -> None:
        super().__init__(id="move-selection-screen")
        self.current_view_label_id = str(current_view_label_id or "").upper() or None

    def compose(self) -> ComposeResult:
        destinations = getattr(self.app, "message_mutation").list_move_destinations()  # type: ignore[attr-defined]
        items = []
        for label in destinations:
            label_id = str(label.get("id") or "")
            if (
                self.current_view_label_id
                and label_id.upper() == self.current_view_label_id
            ):
                continue
            items.append(
                MoveDestinationItem(
                    label_id, str(label.get("name") or label_id).split("/")[-1]
                )
            )

        with Vertical(id="message-action-modal"):
            yield Static("Move", id="message-action-title")
            yield Static(
                "Choose one destination container to apply locally.",
                id="message-action-body",
                markup=False,
            )
            yield ListView(*items, id="move-destination-list")
            with Horizontal(id="message-action-shortcuts"):
                yield Static(
                    binding_choices_label(settings.keybindings.select, "ENTER"),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Choose", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static(
                    movement_pair_label(
                        settings.keybindings.up, settings.keybindings.down
                    ),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Move", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static(
                    binding_choices_label(settings.keybindings.close, "Q/ESC"),
                    classes="shortcut-key",
                    markup=False,
                )
                yield Static("Close", classes="shortcut-label", markup=False)

    def on_mount(self) -> None:
        destination_list = self.query_one("#move-destination-list", ListView)
        destination_list.index = 0
        destination_list.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, MoveDestinationItem):
            self.dismiss(event.item.label_id)

    def action_cursor_up(self) -> None:
        self.query_one("#move-destination-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#move-destination-list", ListView).action_cursor_down()

    def action_select_destination(self) -> None:
        self.query_one("#move-destination-list", ListView).action_select_cursor()

    def action_close(self) -> None:
        self.dismiss(None)

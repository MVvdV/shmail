from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import ListItem, ListView, Static

from shmail.config import settings


class ComposeActionItem(ListItem):
    """List row representing one thread compose action."""

    def __init__(self, action_value: str, label: str) -> None:
        super().__init__()
        self.action_value = action_value
        self.label = label

    def compose(self) -> ComposeResult:
        """Render compose action label."""
        yield Static(self.label, markup=False)


class ThreadComposeActionChooserScreen(ModalScreen[str | None]):
    """Modal chooser for selecting compose intent from thread context."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close", show=False),
        Binding(settings.keybindings.up, "cursor_up", "Previous Action", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next Action", show=False),
        Binding(
            settings.keybindings.select, "select_action", "Select Action", show=False
        ),
    ]

    def compose(self) -> ComposeResult:
        """Render chooser title, action list, and keyboard hints."""
        with Vertical(id="thread-compose-action-modal"):
            yield Static("Compose from message", id="thread-compose-action-title")
            yield ListView(
                ComposeActionItem("reply", "Reply"),
                ComposeActionItem("reply_all", "Reply all"),
                ComposeActionItem("forward", "Forward"),
                id="thread-compose-action-list",
            )
            with Horizontal(id="thread-compose-action-shortcuts"):
                yield Static("ENTER", classes="shortcut-key", markup=False)
                yield Static("Choose", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static("Q/ESC", classes="shortcut-key", markup=False)
                yield Static("Cancel", classes="shortcut-label", markup=False)

    def on_mount(self) -> None:
        """Initialize chooser focus and default index."""
        action_list = self.query_one("#thread-compose-action-list", ListView)
        action_list.index = 0
        action_list.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss chooser with selected action value."""
        if isinstance(event.item, ComposeActionItem):
            self.dismiss(event.item.action_value)

    def action_cursor_up(self) -> None:
        """Move chooser selection up."""
        self.query_one("#thread-compose-action-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move chooser selection down."""
        self.query_one("#thread-compose-action-list", ListView).action_cursor_down()

    def action_select_action(self) -> None:
        """Activate currently highlighted compose action."""
        self.query_one("#thread-compose-action-list", ListView).action_select_cursor()

    def action_close(self) -> None:
        """Dismiss chooser without selection."""
        self.dismiss(None)

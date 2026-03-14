from typing import TYPE_CHECKING, cast

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.binding import Binding
from shmail.widgets import MessageItem, ThreadFooter

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class ThreadViewerScreen(ModalScreen):
    """A modal screen that displays an entire conversation thread using MessageItem instances."""

    BINDINGS = [
        Binding("q,escape", "close", "Close Thread"),
        Binding("j,down", "next_message", "Next Message", show=False),
        Binding("k,up", "prev_message", "Previous Message", show=False),
        Binding("g", "first_message", "First Message", show=False),
        Binding("G", "last_message", "Last Message", show=False),
    ]

    def __init__(self, thread_id: str):
        super().__init__(id="viewer-screen")
        self.thread_id = thread_id

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields a container for the conversation thread and a custom footer."""
        with Vertical(id="thread-modal-container"):
            yield ScrollableContainer(id="thread-stack")
            yield ThreadFooter(id="thread-footer")

    def on_mount(self) -> None:
        """Fetches thread messages and populates the stack."""
        self.run_worker(self._load_thread, thread=True)

    def _load_thread(self) -> None:
        """Retrieves messages from the database and mounts them in the thread stack."""
        messages = self.shmail_app.db.get_thread_messages(self.thread_id)

        def _mount_messages():
            stack = self.query_one("#thread-stack")
            for i, message_data in enumerate(messages):
                is_latest = i == 0
                message_widget = MessageItem(message_data)
                stack.mount(message_widget)
                message_widget.expanded = is_latest

            if stack.children:
                stack.children[0].focus()

        self.app.call_from_thread(_mount_messages)

    def action_next_message(self) -> None:
        """Focuses the next message card in the thread stack."""
        stack = self.query_one("#thread-stack")
        if not stack.children:
            return

        current = self.focused
        # Traverse up to find the MessageItem if focus is deep inside
        while current is not None and not isinstance(current, MessageItem):
            current = current.parent

        if current is None:
            stack.children[0].focus()
            return

        idx = stack.children.index(current)
        if idx < len(stack.children) - 1:
            next_item = stack.children[idx + 1]
            next_item.focus()
            stack.scroll_to_widget(next_item)

    def action_prev_message(self) -> None:
        """Focuses the previous message card in the thread stack."""
        stack = self.query_one("#thread-stack")
        if not stack.children:
            return

        current = self.focused
        while current is not None and not isinstance(current, MessageItem):
            current = current.parent

        if current is None:
            stack.children[0].focus()
            return

        idx = stack.children.index(current)
        if idx > 0:
            prev_item = stack.children[idx - 1]
            prev_item.focus()
            stack.scroll_to_widget(prev_item)

    def action_first_message(self) -> None:
        """Jumps to the first (latest) message."""
        stack = self.query_one("#thread-stack")
        if stack.children:
            stack.children[0].focus()
            stack.scroll_to_widget(stack.children[0])

    def action_last_message(self) -> None:
        """Jumps to the last (oldest) message."""
        stack = self.query_one("#thread-stack")
        if stack.children:
            stack.children[-1].focus()
            stack.scroll_to_widget(stack.children[-1])

    def action_close(self) -> None:
        """Dismisses the modal conversation screen."""
        self.app.pop_screen()

    def watch_focused(self, focused) -> None:
        """Updates the footer shortcuts when the focused widget changes."""
        footer = self.query_one(ThreadFooter)
        if hasattr(focused, "get_shortcuts"):
            footer.update_shortcuts(focused.get_shortcuts())
        elif focused is not None:
            parent = focused.parent
            while parent is not None:
                if hasattr(parent, "get_shortcuts"):
                    footer.update_shortcuts(parent.get_shortcuts())
                    break
                parent = parent.parent

    def on_message_item_expanded_changed(self) -> None:
        """Refreshes shortcuts when a message is expanded or collapsed."""
        self.watch_focused(self.focused)

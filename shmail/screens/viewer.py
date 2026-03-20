from typing import TYPE_CHECKING, cast

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.binding import Binding
from textual.widget import Widget
from shmail.config import settings
from shmail.widgets import MessageItem, ThreadFooter

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class ThreadViewerScreen(ModalScreen):
    """A modal screen that displays an entire conversation thread using MessageItem instances."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close Thread"),
        Binding(settings.keybindings.down, "next_message", "Next Message", show=False),
        Binding(
            settings.keybindings.up, "prev_message", "Previous Message", show=False
        ),
        Binding("g", "first_message", "First Message", show=False),
        Binding("G", "last_message", "Last Message", show=False),
        Binding("tab,f", "cycle_forward", "Next Focus", show=False),
        Binding("shift+tab,F", "cycle_backward", "Previous Focus", show=False),
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

    async def on_mount(self) -> None:
        """Fetch thread data in a worker, then mount cards on UI thread."""
        worker = self.run_worker(
            lambda: self.shmail_app.db.get_thread_messages(self.thread_id),
            thread=True,
            exclusive=True,
        )
        messages = await worker.wait()
        await self._mount_thread_messages(messages)

    async def _mount_thread_messages(self, messages: list[dict]) -> None:
        """Mount all thread message cards and initialize accordion state."""
        stack = self.query_one("#thread-stack")
        mounted_items = [MessageItem(message_data) for message_data in messages]
        mounted_widgets: list[Widget] = list(mounted_items)

        for item in mounted_items:
            item.expanded = False

        if mounted_items:
            await stack.mount_all(mounted_widgets)
            self._set_active_message(mounted_items[0])

    def on_show(self) -> None:
        """Reassert single-expanded accordion state when screen becomes visible."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        target = current if isinstance(current, MessageItem) else message_items[0]
        self._set_active_message(target)

    def action_next_message(self) -> None:
        """Focuses the next message card in the thread stack."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        if current is None:
            message_items[0].focus()
            return

        idx = message_items.index(current)
        if idx < len(message_items) - 1:
            next_item = message_items[idx + 1]
            self._set_active_message(next_item)

    def action_prev_message(self) -> None:
        """Focuses the previous message card in the thread stack."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        if current is None:
            message_items[0].focus()
            return

        idx = message_items.index(current)
        if idx > 0:
            prev_item = message_items[idx - 1]
            self._set_active_message(prev_item)

    def action_first_message(self) -> None:
        """Jumps to the first (latest) message."""
        message_items = self._get_message_items()
        if message_items:
            self._set_active_message(message_items[0])

    def action_last_message(self) -> None:
        """Jumps to the last (oldest) message."""
        message_items = self._get_message_items()
        if message_items:
            self._set_active_message(message_items[-1])

    def action_cycle_forward(self) -> None:
        """Cycles focus forward across cards and inner interactive elements."""
        self._cycle_focus(direction=1)

    def action_cycle_backward(self) -> None:
        """Cycles focus backward across cards and inner interactive elements."""
        self._cycle_focus(direction=-1)

    def _cycle_focus(self, direction: int) -> None:
        """Applies hierarchical traversal for card and interactive element focus."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        if current is None:
            self._set_active_message(message_items[0], select_link_direction=direction)
            return

        if current.expanded and current.has_links():
            if current.step_link(direction):
                self.watch_focused(current)
                return

        current_idx = message_items.index(current)
        target_idx = (current_idx + direction) % len(message_items)
        target = message_items[target_idx]
        self._set_active_message(target, select_link_direction=direction)

    def action_close(self) -> None:
        """Dismisses the modal conversation screen."""
        self.app.pop_screen()

    def watch_focused(self, focused) -> None:
        """Updates the footer shortcuts when the focused widget changes."""
        footer = self.query_one(ThreadFooter)
        if isinstance(focused, MessageItem):
            shortcuts = focused.get_shortcuts()
            active = focused.get_active_link()
            if active is not None:
                href = str(active.get("href", ""))
                shortcuts = self._append_link_hint(shortcuts, href)
            footer.update_shortcuts(shortcuts)
        elif hasattr(focused, "get_shortcuts"):
            footer.update_shortcuts(focused.get_shortcuts())
        elif focused is not None:
            owner = self._resolve_widget_with_shortcuts(focused)
            if owner is not None:
                footer.update_shortcuts(owner.get_shortcuts())

    def _get_message_items(self) -> list[MessageItem]:
        """Returns all MessageItem widgets in the thread stack order."""
        stack = self.query_one("#thread-stack")
        return [child for child in stack.children if isinstance(child, MessageItem)]

    def _resolve_focused_message_item(self) -> MessageItem | None:
        """Resolves focused context to the owning message card."""
        current = self.focused
        while current is not None and not isinstance(current, MessageItem):
            current = current.parent
        return current

    def on_message_item_expanded_changed(
        self, _event: MessageItem.ExpandedChanged
    ) -> None:
        """Refreshes shortcuts when a message is expanded or collapsed."""
        sender = getattr(_event, "sender", None)
        if isinstance(sender, MessageItem):
            self._set_active_message(sender)
        self.watch_focused(self.focused)

    def _set_active_message(
        self,
        target: MessageItem,
        select_link_direction: int | None = None,
    ) -> None:
        """Apply accordion behavior and optionally enter target link context."""
        stack = self.query_one("#thread-stack")
        message_items = self._get_message_items()
        if target not in message_items:
            return

        for item in message_items:
            if item is target:
                continue
            item.expanded = False

        target.expanded = True
        target.focus()
        stack.scroll_to_widget(target)

        if select_link_direction is not None and target.has_links():
            target.active_link_index = -1
            target.step_link(select_link_direction)

    @staticmethod
    def _append_link_hint(
        shortcuts: list[tuple[str, str]], href: str
    ) -> list[tuple[str, str]]:
        """Adds a concise focused-link hint to footer shortcuts."""
        condensed_href = href.strip()
        if len(condensed_href) > 42:
            condensed_href = f"{condensed_href[:39]}..."
        return [*shortcuts, ("LINK", condensed_href)]

    @staticmethod
    def _resolve_widget_with_shortcuts(widget):
        """Finds nearest ancestor implementing shortcut provider."""
        parent = widget.parent if widget is not None else None
        while parent is not None:
            if hasattr(parent, "get_shortcuts"):
                return parent
            parent = parent.parent
        return None

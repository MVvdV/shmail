from typing import TYPE_CHECKING, cast

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.binding import Binding
from textual.widget import Widget
from textual.worker import WorkerCancelled
from shmail.config import settings
from .message_draft import MessageDraftCloseUpdate, MessageDraftScreen, MessageDraftSeed
from shmail.services.message_draft import MessageDraftService
from shmail.widgets.shortcuts import resolve_shortcut_owner
from shmail.widgets import MessageItem, ThreadFooter

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class ThreadMessagesScreen(ModalScreen):
    """A modal screen that displays thread messages using MessageItem cards."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close Thread"),
        Binding(settings.keybindings.reply, "reply", "Reply", show=False),
        Binding(settings.keybindings.reply_all, "reply_all", "Reply All", show=False),
        Binding(settings.keybindings.forward, "forward", "Forward", show=False),
        Binding(
            settings.keybindings.delete_draft,
            "delete_draft",
            "Delete Draft",
            show=False,
        ),
        Binding(settings.keybindings.down, "next_message", "Next Message", show=False),
        Binding(
            settings.keybindings.up, "prev_message", "Previous Message", show=False
        ),
        Binding(
            settings.keybindings.first, "first_message", "First Message", show=False
        ),
        Binding(settings.keybindings.last, "last_message", "Last Message", show=False),
        Binding(
            settings.keybindings.thread_cycle_forward,
            "cycle_forward",
            "Next Focus",
            show=False,
        ),
        Binding(
            settings.keybindings.thread_cycle_backward,
            "cycle_backward",
            "Previous Focus",
            show=False,
        ),
    ]

    def __init__(self, thread_id: str):
        super().__init__(id="thread-messages-screen")
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
        await self._reload_thread_messages()

    async def _reload_thread_messages(self) -> None:
        """Reload thread messages from storage and re-mount message cards."""
        worker = self.run_worker(
            lambda: self.shmail_app.thread_viewer.list_thread_messages(self.thread_id),
            thread=True,
            exclusive=False,
        )
        try:
            messages = await worker.wait()
        except WorkerCancelled:
            return
        await self._mount_thread_messages(messages)

    def _on_message_draft_closed(self, update: MessageDraftCloseUpdate | None) -> None:
        """Delegate draft-close refresh handling to the app authority."""
        apply_update = getattr(self.shmail_app, "apply_message_draft_update", None)
        if callable(apply_update):
            apply_update(update)

    def reload_thread_if_matching(self, thread_id: str) -> None:
        """Reload this thread when one draft update targets its source thread."""
        if thread_id != self.thread_id:
            return
        self.run_worker(self._reload_thread_messages(), exclusive=False)

    async def _mount_thread_messages(self, messages: list[dict]) -> None:
        """Mount all thread message cards and initialize accordion state."""
        stack = self.query_one("#thread-stack")
        await stack.remove_children()
        mounted_items = [MessageItem(message_data) for message_data in messages]
        mounted_widgets: list[Widget] = list(mounted_items)

        for item in mounted_items:
            item.expanded = False

        if mounted_items:
            await stack.mount_all(mounted_widgets)
            self.call_after_refresh(lambda: self._set_active_message(mounted_items[0]))

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

    def action_reply(self) -> None:
        """Open a reply draft from the focused thread message."""
        self._open_compose_from_focus("reply")

    def action_reply_all(self) -> None:
        """Open a reply-all draft from the focused thread message."""
        self._open_compose_from_focus("reply_all")

    def action_forward(self) -> None:
        """Open a forward draft from the focused thread message."""
        self._open_compose_from_focus("forward")

    def open_focused_draft(self) -> None:
        """Resume the focused draft card when one is selected."""
        self._open_compose_from_focus(None)

    def action_delete_draft(self) -> None:
        """Delete the focused draft card when one is selected."""
        message_item = self._resolve_focused_message_item()
        if message_item is None:
            return

        source_data = dict(message_item.message_data)
        if not source_data.get("is_draft") or not source_data.get("draft_id"):
            return

        draft_id = str(source_data.get("draft_id") or "").strip()
        if not draft_id:
            return

        MessageDraftService(self.shmail_app.repository).delete_draft(draft_id)
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify("Draft deleted.", severity="information")

        apply_update = getattr(self.shmail_app, "apply_message_draft_update", None)
        update = MessageDraftCloseUpdate(
            did_change=True,
            draft_id=draft_id,
            source_thread_id=str(source_data.get("thread_id") or "") or None,
        )
        if callable(apply_update):
            apply_update(update)
        else:
            self.reload_thread_if_matching(update.source_thread_id or "")

    def _open_compose_from_focus(self, action: str | None) -> None:
        """Open or resume compose from the currently focused thread card."""
        message_item = self._resolve_focused_message_item()
        if message_item is None:
            message_items = self._get_message_items()
            if not message_items:
                return
            message_item = message_items[0]

        source_data = dict(message_item.message_data)

        if source_data.get("is_draft") and source_data.get("draft_id"):
            self.app.push_screen(
                MessageDraftScreen(
                    seed=MessageDraftSeed(
                        mode="draft",
                        draft_id=str(source_data.get("draft_id") or ""),
                    )
                ),
                self._on_message_draft_closed,
            )
            return

        if action is None:
            return

        seed = self.shmail_app.thread_viewer.build_message_draft_seed(
            source_data,
            action,
            current_account=self.shmail_app.email or "",
        )
        self.app.push_screen(
            MessageDraftScreen(seed=seed), self._on_message_draft_closed
        )

    def watch_focused(self, focused) -> None:
        """Updates the footer shortcuts when the focused widget changes."""
        footer = self.query_one(ThreadFooter)
        if isinstance(focused, MessageItem):
            footer.update_shortcuts(focused.get_shortcuts())
            return

        owner = resolve_shortcut_owner(focused)
        if owner is not None:
            get_shortcuts = getattr(owner, "get_shortcuts", None)
            if callable(get_shortcuts):
                footer.update_shortcuts(cast(list[tuple[str, str]], get_shortcuts()))

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

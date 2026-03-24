from typing import TYPE_CHECKING, cast

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.binding import Binding
from textual.widget import Widget
from textual.worker import WorkerCancelled
from shmail.config import settings
from .message_draft import MessageDraftCloseUpdate, MessageDraftScreen, MessageDraftSeed
from .thread_compose_action import ThreadComposeActionChooserScreen
from shmail.widgets import MessageItem, ThreadFooter

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class ThreadMessagesScreen(ModalScreen):
    """A modal screen that displays thread messages using MessageItem cards."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close Thread"),
        Binding(settings.keybindings.compose, "compose_message", "Compose", show=False),
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
            lambda: self.shmail_app.db.get_thread_messages(self.thread_id),
            thread=True,
            exclusive=False,
        )
        try:
            messages = await worker.wait()
        except WorkerCancelled:
            return
        await self._mount_thread_messages(messages)

    def _on_message_draft_closed(self, update: MessageDraftCloseUpdate | None) -> None:
        """Refresh only affected thread state after compose closes."""
        if update is None or not update.did_change:
            return

        source_thread_id = (update.source_thread_id or "").strip()
        if source_thread_id == self.thread_id:
            self.run_worker(self._reload_thread_messages(), exclusive=False)

        main_screen = next(
            (
                screen
                for screen in self.app.screen_stack
                if screen.__class__.__name__ == "MainScreen"
            ),
            None,
        )
        if main_screen is not None:
            thread_list = getattr(main_screen, "query_one", None)
            if callable(thread_list):
                try:
                    labels_sidebar = main_screen.query_one("#labels-sidebar")
                    update_draft_count = getattr(
                        labels_sidebar, "update_draft_count", None
                    )
                    if callable(update_draft_count):
                        total_drafts = self.shmail_app.db.get_total_local_draft_count()
                        update_draft_count(total_drafts)

                    list_widget = main_screen.query_one("#threads-list")
                    current_label = str(
                        getattr(list_widget, "current_label_id", "") or ""
                    )
                    if current_label.upper() == "DRAFT":
                        load_threads = getattr(list_widget, "load_threads", None)
                        if callable(load_threads):
                            load_threads("DRAFT")
                    elif source_thread_id:
                        update_marker = getattr(
                            list_widget, "update_thread_draft_marker", None
                        )
                        if callable(update_marker):
                            draft_count = self.shmail_app.db.get_thread_draft_count(
                                source_thread_id
                            )
                            update_marker(source_thread_id, draft_count)
                except Exception:
                    pass

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

    def action_compose_message(self) -> None:
        """Launch thread compose chooser from focused message context."""
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

        def _after_choice(action: str | None) -> None:
            if not action:
                return
            seed = self._build_message_draft_seed(source_data, action)
            self.app.push_screen(
                MessageDraftScreen(seed=seed), self._on_message_draft_closed
            )

        self.app.push_screen(ThreadComposeActionChooserScreen(), _after_choice)

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

    def _build_message_draft_seed(
        self, message_data: dict, action: str
    ) -> MessageDraftSeed:
        """Create a draft seed payload from selected message context."""
        subject = str(message_data.get("subject") or "")
        sender_address = str(message_data.get("sender_address") or "").strip().lower()
        recipient_to = self._split_addresses(message_data.get("recipient_to_addresses"))
        recipient_cc = self._split_addresses(message_data.get("recipient_cc_addresses"))
        current_account = (self.shmail_app.email or "").strip().lower()

        body = str(message_data.get("body") or "")
        sender_text = str(
            message_data.get("sender") or sender_address or "Unknown sender"
        )
        timestamp = str(message_data.get("timestamp") or "")

        if action == "reply":
            to_recipients = self._unique_addresses([sender_address], current_account)
            return MessageDraftSeed(
                mode="reply",
                to=", ".join(to_recipients),
                subject=self._prefix_subject(subject, "Re:"),
                body=self._build_reply_body(sender_text, timestamp, body),
                source_message_id=str(message_data.get("id") or "") or None,
                source_thread_id=str(message_data.get("thread_id") or "") or None,
            )

        if action == "reply_all":
            to_recipients = self._unique_addresses(
                [sender_address, *recipient_to, *recipient_cc], current_account
            )
            return MessageDraftSeed(
                mode="reply_all",
                to=", ".join(to_recipients),
                subject=self._prefix_subject(subject, "Re:"),
                body=self._build_reply_body(sender_text, timestamp, body),
                source_message_id=str(message_data.get("id") or "") or None,
                source_thread_id=str(message_data.get("thread_id") or "") or None,
            )

        return MessageDraftSeed(
            mode="forward",
            subject=self._prefix_subject(subject, "Fwd:"),
            body=self._build_forward_body(message_data, body),
            source_message_id=str(message_data.get("id") or "") or None,
            source_thread_id=str(message_data.get("thread_id") or "") or None,
        )

    @staticmethod
    def _split_addresses(value: object) -> list[str]:
        """Split comma-separated address fields into normalized addresses."""
        if not isinstance(value, str):
            return []
        return [
            address.strip().lower() for address in value.split(",") if address.strip()
        ]

    @staticmethod
    def _unique_addresses(addresses: list[str], current_account: str) -> list[str]:
        """De-duplicate addresses and exclude current account identity."""
        unique: list[str] = []
        for address in addresses:
            normalized = address.strip().lower()
            if not normalized or normalized == current_account:
                continue
            if normalized not in unique:
                unique.append(normalized)
        return unique

    @staticmethod
    def _prefix_subject(subject: str, prefix: str) -> str:
        """Apply one canonical reply/forward prefix to subject text."""
        raw = " ".join(subject.split())
        lower = raw.lower()
        if lower.startswith(f"{prefix.lower()} ") or lower == prefix.lower():
            return raw
        if not raw:
            return prefix
        return f"{prefix} {raw}"

    @staticmethod
    def _build_reply_body(sender: str, timestamp: str, body: str) -> str:
        """Build reply body with quoted original message content."""
        heading = (
            f"On {timestamp}, {sender} wrote:" if timestamp else f"{sender} wrote:"
        )
        quoted = [f"> {line}" if line else ">" for line in body.splitlines()]
        quote_block = "\n".join(quoted)
        return f"\n\n{heading}\n{quote_block}".rstrip()

    @staticmethod
    def _build_forward_body(message_data: dict, body: str) -> str:
        """Build forward draft body with original message metadata block."""
        sender = str(message_data.get("sender") or "")
        to_line = str(message_data.get("recipient_to") or "")
        subject = str(message_data.get("subject") or "")
        timestamp = str(message_data.get("timestamp") or "")
        header_lines = [
            "---",
            "Forwarded message",
            f"From: {sender}" if sender else "",
            f"Date: {timestamp}" if timestamp else "",
            f"Subject: {subject}" if subject else "",
            f"To: {to_line}" if to_line else "",
            "---",
        ]
        normalized_header = "\n".join(line for line in header_lines if line)
        return f"\n\n{normalized_header}\n\n{body}".rstrip()

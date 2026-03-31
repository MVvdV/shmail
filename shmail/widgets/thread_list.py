from typing import TYPE_CHECKING, cast

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from shmail.config import settings
from shmail.services.time import format_compact_datetime
from shmail.widgets.shortcuts import binding_choices_label, movement_pair_label

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class ThreadList(ListView):
    """A list view specialized for displaying conversation thread snippets."""

    BINDINGS = [
        Binding(settings.keybindings.up, "cursor_up", "Previous", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next", show=False),
        Binding(settings.keybindings.first, "first_thread", "First Thread", show=False),
        Binding(settings.keybindings.last, "last_thread", "Last Thread", show=False),
        Binding(settings.keybindings.labels, "edit_labels", "Labels", show=False),
        Binding(settings.keybindings.move, "move_thread", "Move", show=False),
        Binding(settings.keybindings.trash, "trash_thread", "Trash", show=False),
        Binding(settings.keybindings.restore, "restore_thread", "Restore", show=False),
        Binding(
            settings.keybindings.retry, "retry_thread_mutations", "Retry", show=False
        ),
    ]

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return the active shortcuts for the thread list."""
        current_label = str(self.current_label_id or "").upper()
        if current_label == "OUTBOX":
            return [
                (binding_choices_label(settings.keybindings.select, "ENTER"), "Open"),
                (
                    binding_choices_label(settings.keybindings.trash, "X"),
                    "Cancel Queue",
                ),
                (
                    binding_choices_label(settings.keybindings.retry, "Ctrl+R"),
                    "Retry",
                ),
                (
                    binding_choices_label(settings.keybindings.get_mail, "Ctrl+G"),
                    "Get Mail",
                ),
                (
                    movement_pair_label(
                        settings.keybindings.up, settings.keybindings.down
                    ),
                    "Navigate",
                ),
                (
                    f"{binding_choices_label(settings.keybindings.first, 'G')}/{binding_choices_label(settings.keybindings.last, 'SHIFT+G')}",
                    "Home/End",
                ),
                (
                    binding_choices_label(settings.keybindings.pane_prev, "TAB"),
                    "Labels",
                ),
            ]
        shortcuts = [
            (binding_choices_label(settings.keybindings.select, "ENTER"), "Open"),
            (binding_choices_label(settings.keybindings.labels, "L"), "Labels"),
            (binding_choices_label(settings.keybindings.move, "M"), "Move"),
            (
                binding_choices_label(settings.keybindings.trash, "X"),
                "Cancel Queue"
                if current_label == "OUTBOX"
                else ("Delete" if current_label == "TRASH" else "Trash"),
            ),
            (
                movement_pair_label(settings.keybindings.up, settings.keybindings.down),
                "Navigate",
            ),
            (binding_choices_label(settings.keybindings.retry, "Ctrl+R"), "Retry"),
            (
                binding_choices_label(settings.keybindings.get_mail, "Ctrl+G"),
                "Get Mail",
            ),
            (
                f"{binding_choices_label(settings.keybindings.first, 'G')}/{binding_choices_label(settings.keybindings.last, 'SHIFT+G')}",
                "Home/End",
            ),
            (binding_choices_label(settings.keybindings.pane_prev, "TAB"), "Labels"),
        ]
        if current_label == "TRASH":
            shortcuts.insert(
                4,
                (binding_choices_label(settings.keybindings.restore, "U"), "Restore"),
            )
        return shortcuts

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    class ThreadSelected(Message):
        """Sent when a conversation thread is activated in the list."""

        def __init__(self, thread_id: str) -> None:
            self.thread_id = thread_id
            super().__init__()

    class ThreadMutationRequested(Message):
        """Sent when a thread-scoped mutation action is requested."""

        def __init__(
            self, thread_id: str, action: str, subject: str, thread_count: int
        ) -> None:
            self.thread_id = thread_id
            self.action = action
            self.subject = subject
            self.thread_count = thread_count
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_label_id = None

    def update_thread_draft_marker(self, thread_id: str, draft_count: int) -> None:
        """Update one visible thread row draft marker without reloading list."""
        for child in self.children:
            if not isinstance(child, ThreadRow):
                continue
            if str(child.thread_data.get("thread_id", "")) != thread_id:
                continue
            child.set_draft_count(draft_count)
            return

    def update_thread_outbox_marker(self, thread_id: str, outbox_count: int) -> None:
        """Update one visible thread row outbox indicator without reloading list."""
        for child in self.children:
            if not isinstance(child, ThreadRow):
                continue
            if str(child.thread_data.get("thread_id", "")) != thread_id:
                continue
            child.set_outbox_count(outbox_count)
            return

    def set_thread_mutation_status(
        self,
        thread_id: str,
        pending_count: int,
        failed_count: int,
        blocked_count: int = 0,
        mutation_state: str = "",
    ) -> None:
        """Update one visible thread row mutation summary without reloading list."""
        for child in self.children:
            if not isinstance(child, ThreadRow):
                continue
            if str(child.thread_data.get("thread_id", "")) != thread_id:
                continue
            child.set_mutation_status(
                pending_count, failed_count, blocked_count, mutation_state
            )
            return

    def load_threads(self, label_id: str) -> None:
        """Clears the current list and loads conversations associated with the given label."""
        self.current_label_id = label_id
        self.clear()
        self.run_worker(
            lambda: self._load_threads_worker(label_id), thread=True, exclusive=True
        )

    def _load_threads_worker(self, label_id: str) -> None:
        """Loads thread rows in a worker and applies them on UI thread."""
        threads = self.shmail_app.thread_query.list_threads(label_id=label_id)
        self.app.call_from_thread(self._populate_threads, label_id, threads)

    def _populate_threads(self, label_id: str, threads: list[dict]) -> None:
        """Renders fetched threads when they match the current label context."""
        if label_id != self.current_label_id:
            return

        self.clear()

        if not threads:
            self.append(
                ListItem(
                    Static(
                        "No conversations found in this label.", id="empty-state-msg"
                    )
                )
            )
            return

        for thread_data in threads:
            thread_data["current_label_id"] = label_id
            self.append(ThreadRow(thread_data))

        self.call_after_refresh(self._initialize_index)

    def _initialize_index(self) -> None:
        """Positions the selection cursor at the top of the list."""
        if len(self) > 0:
            self.index = 0

    def on_focus(self) -> None:
        """Ensures a valid selection exists when the list receives focus."""
        if self.index is None and len(self) > 0:
            self.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handles item activation and broadcasts the thread selection message."""
        if isinstance(event.item, ThreadRow):
            thread_id = event.item.thread_data["thread_id"]
            self.post_message(self.ThreadSelected(thread_id))

    def action_first_thread(self) -> None:
        """Jumps to the first thread."""
        if len(self) > 0:
            self.index = 0

    def action_last_thread(self) -> None:
        """Jumps to the last thread."""
        if len(self) > 0:
            self.index = len(self) - 1

    def action_edit_labels(self) -> None:
        """Request thread-scoped label editing for the highlighted row."""
        if str(self.current_label_id or "").upper() == "OUTBOX":
            return
        self._post_mutation_request("labels")

    def action_move_thread(self) -> None:
        """Request thread-scoped move for the highlighted row."""
        if str(self.current_label_id or "").upper() == "OUTBOX":
            return
        self._post_mutation_request("move")

    def action_trash_thread(self) -> None:
        """Request thread-scoped trash or delete for the highlighted row."""
        self._post_mutation_request("trash")

    def action_restore_thread(self) -> None:
        """Request thread-scoped restore for the highlighted row."""
        self._post_mutation_request("restore")

    def action_retry_thread_mutations(self) -> None:
        """Request retry for failed or blocked thread-associated mutations."""
        self._post_mutation_request("retry")

    def _post_mutation_request(self, action: str) -> None:
        """Post one thread mutation request for the highlighted row."""
        if self.index is None or self.index < 0 or self.index >= len(self.children):
            return
        child = self.children[self.index]
        if not isinstance(child, ThreadRow):
            return
        thread_id = str(child.thread_data.get("thread_id") or "")
        if not thread_id:
            return
        self.post_message(
            self.ThreadMutationRequested(
                thread_id,
                action,
                str(child.thread_data.get("subject") or "") or "(No Subject)",
                int(child.thread_data.get("thread_count") or 1),
            )
        )


class ThreadRow(ListItem):
    """A multi-line list item representing a conversation thread snippet."""

    def __init__(self, thread_data: dict):
        super().__init__()
        self.add_class("thread-list-row")
        self.thread_data = thread_data

    def compose(self):
        """Yields the structured layout for the thread row with indicators."""
        is_unread = not self.thread_data.get("is_read", False)
        thread_count = self.thread_data.get("thread_count", 1)

        with Horizontal(classes="thread-row-item"):
            with Vertical(classes="thread-indicators"):
                count_text = str(thread_count) if thread_count > 1 else ""
                has_failed = bool(
                    self.thread_data.get("mutation_failed_count")
                ) or bool(self.thread_data.get("mutation_blocked_count"))
                yield Static(count_text, classes="thread-count")
                yield Static("●" if is_unread else "", classes="unread-indicator")
                yield Static(
                    "!" if has_failed else "",
                    classes="mutation-indicator",
                )

            with Vertical(classes="thread-row-wrapper"):
                with Horizontal(classes="thread-row-header"):
                    yield Static(
                        self.thread_data.get("sender_display", ""),
                        classes="thread-sender",
                        markup=False,
                    )
                    sender_email = self.thread_data.get("sender_address", "") or ""
                    yield Static(
                        sender_email,
                        classes="thread-sender-email",
                        markup=False,
                    )
                    yield Static(self._format_date(), classes="thread-date")

                yield Static(
                    self.thread_data.get("subject", ""),
                    classes="thread-subject",
                    markup=False,
                )
                first_line, second_line = self._snippet_lines()
                yield Static(first_line, classes="thread-snippet", markup=False)
                with Horizontal(classes="thread-bottom-row"):
                    yield Static(
                        second_line, classes="thread-snippet-tail", markup=False
                    )
                    yield Static(
                        self._render_label_chips(),
                        classes="thread-label-chips",
                        markup=True,
                    )

    def _format_date(self) -> str:
        """Format the thread timestamp for compact list display."""
        return format_compact_datetime(self.thread_data.get("timestamp", ""))

    def _snippet_lines(self) -> tuple[str, str]:
        """Return the thread snippet split across two compact lines."""
        import textwrap

        snippet = str(self.thread_data.get("snippet") or "").strip()
        wrapped = textwrap.wrap(snippet, width=64) if snippet else []
        first = wrapped[0] if wrapped else ""
        second = wrapped[1] if len(wrapped) > 1 else ""
        return first, second

    def _render_label_chips(self) -> str:
        """Render a compact union of labels visible across the thread."""
        from rich.markup import escape

        labels = list(self.thread_data.get("thread_labels") or [])
        chips = []
        for label in labels:
            label_id = str(label.get("id") or "").upper()
            if label_id in {"UNREAD"}:
                continue
            name = str(label.get("name") or label.get("id") or "").strip()
            if not name:
                continue
            text = escape(name.split("/")[-1])
            background = str(label.get("background_color") or "").strip()
            foreground = str(label.get("text_color") or "").strip()
            if background and foreground:
                chips.append(f"[{foreground} on {background}] {text} [/]")
            else:
                chips.append(f"[reverse] {text} [/]")
        return " ".join(chips)

    def set_draft_count(self, draft_count: int) -> None:
        """Update draft indicator state for this row in-place."""
        current_count = int(self.thread_data.get("draft_count") or 0)
        current_has_draft = bool(self.thread_data.get("has_draft"))
        next_has_draft = draft_count > 0
        if current_count == draft_count and current_has_draft == next_has_draft:
            return

        self.thread_data["draft_count"] = draft_count
        self.thread_data["has_draft"] = int(next_has_draft)
        self._set_virtual_label_presence("DRAFT", next_has_draft)
        try:
            chips = self.query_one(".thread-label-chips", Static)
        except Exception:
            return
        chips.update(self._render_label_chips())

    def set_outbox_count(self, outbox_count: int) -> None:
        """Update outbox indicator state for this row in-place."""
        current_count = int(self.thread_data.get("outbox_count") or 0)
        current_has_outbox = bool(self.thread_data.get("has_outbox"))
        next_has_outbox = outbox_count > 0
        if current_count == outbox_count and current_has_outbox == next_has_outbox:
            return

        self.thread_data["outbox_count"] = outbox_count
        self.thread_data["has_outbox"] = int(next_has_outbox)
        self._set_virtual_label_presence("OUTBOX", next_has_outbox)
        try:
            chips = self.query_one(".thread-label-chips", Static)
        except Exception:
            return
        chips.update(self._render_label_chips())

    def set_mutation_status(
        self,
        pending_count: int,
        failed_count: int,
        blocked_count: int = 0,
        mutation_state: str = "",
    ) -> None:
        """Update pending/failed mutation indicator state for this row in-place."""
        self.thread_data["mutation_pending_count"] = pending_count
        self.thread_data["mutation_failed_count"] = failed_count
        self.thread_data["mutation_blocked_count"] = blocked_count
        self.thread_data["mutation_state"] = mutation_state
        try:
            indicator = self.query_one(".mutation-indicator", Static)
        except Exception:
            return
        indicator.update("!" if failed_count > 0 or blocked_count > 0 else "")

    def _set_virtual_label_presence(self, label_id: str, present: bool) -> None:
        """Insert or remove one virtual label from the thread chip union."""
        labels = list(self.thread_data.get("thread_labels") or [])
        existing = {str(label.get("id") or "").upper(): label for label in labels}
        if present:
            if label_id not in existing:
                names = {"DRAFT": "Drafts", "OUTBOX": "Outbox"}
                labels.append({"id": label_id, "name": names.get(label_id, label_id)})
        else:
            labels = [
                label
                for label in labels
                if str(label.get("id") or "").upper() != label_id
            ]
        self.thread_data["thread_labels"] = labels

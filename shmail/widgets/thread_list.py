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
    ]

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return the active shortcuts for the thread list."""
        return [
            (binding_choices_label(settings.keybindings.select, "ENTER"), "Open"),
            (binding_choices_label(settings.keybindings.compose, "C"), "New"),
            (
                movement_pair_label(settings.keybindings.up, settings.keybindings.down),
                "Move",
            ),
            (
                f"{binding_choices_label(settings.keybindings.first, 'G')}/{binding_choices_label(settings.keybindings.last, 'SHIFT+G')}",
                "Home/End",
            ),
            (binding_choices_label(settings.keybindings.pane_prev, "TAB"), "Labels"),
        ]

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    class ThreadSelected(Message):
        """Sent when a conversation thread is activated in the list."""

        def __init__(self, thread_id: str) -> None:
            self.thread_id = thread_id
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


class ThreadRow(ListItem):
    """A multi-line list item representing a conversation thread snippet."""

    def __init__(self, thread_data: dict):
        super().__init__()
        self.thread_data = thread_data

    def compose(self):
        """Yields the structured layout for the thread row with indicators."""
        is_unread = not self.thread_data.get("is_read", False)
        thread_count = self.thread_data.get("thread_count", 1)

        with Horizontal(classes="thread-row-item"):
            with Vertical(classes="thread-indicators"):
                count_text = str(thread_count) if thread_count > 1 else ""
                has_draft = bool(self.thread_data.get("has_draft"))
                yield Static(count_text, classes="thread-count")
                yield Static("●" if is_unread else "", classes="unread-indicator")
                yield Static("✎" if has_draft else "", classes="draft-indicator")

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
                snippet = self.thread_data.get("snippet", "")
                yield Static(snippet, classes="thread-snippet", markup=False)

    def _format_date(self) -> str:
        """Format the thread timestamp for compact list display."""
        return format_compact_datetime(self.thread_data.get("timestamp", ""))

    def set_draft_count(self, draft_count: int) -> None:
        """Update draft indicator state for this row in-place."""
        current_count = int(self.thread_data.get("draft_count") or 0)
        current_has_draft = bool(self.thread_data.get("has_draft"))
        next_has_draft = draft_count > 0
        if current_count == draft_count and current_has_draft == next_has_draft:
            return

        self.thread_data["draft_count"] = draft_count
        self.thread_data["has_draft"] = int(next_has_draft)
        try:
            indicator = self.query_one(".draft-indicator", Static)
        except Exception:
            return
        indicator.update("✎" if draft_count > 0 else "")

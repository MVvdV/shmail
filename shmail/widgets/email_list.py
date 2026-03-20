from datetime import datetime
from typing import TYPE_CHECKING, cast

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from shmail.config import settings

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class ThreadList(ListView):
    """A list view specialized for displaying conversation thread snippets."""

    BINDINGS = [
        Binding(settings.keybindings.up, "cursor_up", "Previous", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next", show=False),
        Binding("g", "first_thread", "First Thread", show=False),
        Binding("G", "last_thread", "Last Thread", show=False),
    ]

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Returns the active shortcuts for the ThreadList."""
        return [
            ("ENTER", "Read"),
            ("J/K", "Move"),
            ("G/g", "Top/End"),
            ("TAB", "Sidebar"),
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

    def load_threads(self, label_id: str) -> None:
        """Clears the current list and loads conversations associated with the given label."""
        self.current_label_id = label_id
        self.clear()
        self.run_worker(
            lambda: self._load_threads_worker(label_id), thread=True, exclusive=True
        )

    def _load_threads_worker(self, label_id: str) -> None:
        """Loads thread rows in a worker and applies them on UI thread."""
        threads = self.shmail_app.db.get_threads(label_id=label_id)
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
                yield Static(count_text, classes="thread-count")
                yield Static("●" if is_unread else "", classes="unread-indicator")

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
        """Converts database timestamps into user-friendly display strings."""
        raw = self.thread_data.get("timestamp", "")
        if not raw:
            return ""

        try:
            clean_raw = str(raw).replace("Z", "+00:00").replace(" ", "T")
            dt = datetime.fromisoformat(clean_raw)
            return dt.strftime("%b %d, %H:%M")
        except Exception:
            return str(raw)[:16].replace("T", ", ").replace(" ", ", ")

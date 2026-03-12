from datetime import datetime
from typing import TYPE_CHECKING, cast

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class EmailList(ListView):
    """A list view specialized for displaying Gmail message snippets."""

    BINDINGS = [
        Binding("k,up", "cursor_up", "Previous", show=False),
        Binding("j,down", "cursor_down", "Next", show=False),
    ]

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    class EmailSelected(Message):
        """Sent when an email is activated in the list."""

        def __init__(self, email_id: str) -> None:
            self.email_id = email_id
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_label_id = None

    def load_label(self, label_id: str) -> None:
        """Clears the current list and loads emails associated with the given label."""
        self.current_label_id = label_id
        self.clear()

        emails = self.shmail_app.db.get_emails(label_id=label_id)

        if not emails:
            self.append(
                ListItem(Static("No emails found in this label.", id="empty-state-msg"))
            )
            return

        for email in emails:
            self.append(EmailRow(email))

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
        """Handles item activation and broadcasts the selection message."""
        if isinstance(event.item, EmailRow):
            email_id = event.item.email_data["id"]
            self.post_message(self.EmailSelected(email_id))


class EmailRow(ListItem):
    """A multi-line list item representing an email snippet."""

    def __init__(self, email_data: dict):
        super().__init__()
        self.email_data = email_data

    def compose(self):
        """Yields the structured layout for the email row."""
        is_unread = not self.email_data.get("is_read", False)

        with Horizontal(classes="email-row-item"):
            yield Static("●" if is_unread else "", classes="unread-indicator")

            with Vertical(classes="email-row-wrapper"):
                with Horizontal(classes="email-row-header"):
                    yield Static(
                        self.email_data.get("sender_display", ""),
                        classes="email-sender",
                        markup=False,
                    )
                    address_text = self.email_data.get("sender_address", "") or ""
                    yield Static(
                        address_text,
                        classes="email-sender-address",
                        markup=False,
                    )
                    yield Static(self._format_date(), classes="email-date")

                yield Static(
                    self.email_data.get("subject", ""),
                    classes="email-subject",
                    markup=False,
                )
                snippet = self.email_data.get("snippet", "")
                yield Static(snippet, classes="email-snippet", markup=False)

    def _format_date(self) -> str:
        """Converts database timestamps into user-friendly display strings."""
        raw = self.email_data.get("timestamp", "")
        if not raw:
            return ""

        try:
            clean_raw = str(raw).replace("Z", "+00:00").replace(" ", "T")
            dt = datetime.fromisoformat(clean_raw)
            return dt.strftime("%b %d, %H:%M")
        except Exception:
            return str(raw)[:16].replace("T", ", ").replace(" ", ", ")

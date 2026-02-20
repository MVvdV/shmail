from typing import TYPE_CHECKING, cast

from textual.message import Message
from textual.widgets import ListItem, ListView, Static

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class EmailList(ListView):
    """A widget to display a list of email snippets."""

    @property
    def shmail_app(self) -> ShmailApp:
        return cast("ShmailApp", self.app)

    class EmailSelected(Message):
        """Sent when an email is selected in the list."""

        def __init__(self, email_id: str) -> None:
            self.email_id = email_id
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_label_id = None

    def load_label(self, label_id: str) -> None:
        """Clear the list and load emails for the specified label."""
        self.current_label_id = label_id
        self.clear()

        emails = self.shmail_app.db.get_emails(label_id=label_id)

        if not emails:
            # Production practice: Provide feedback for empty states
            self.append(
                ListItem(Static("No emails found in this label.", id="empty-state-msg"))
            )
            return

        for email in emails:
            self.append(EmailRow(email))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection of an email row."""
        # Ensure we are dealing with our custom EmailRow
        if isinstance(event.item, EmailRow):
            email_id = event.item.email_data["id"]
            self.post_message(self.EmailSelected(email_id))


class EmailRow(ListItem):
    """A single row in the email list."""

    def __init__(self, email_data: dict):
        super().__init__()
        self.email_data = email_data

    def compose(self):
        # TODO: Implement Horizontal layout with Sender, Snippet, and Time
        yield Static(
            f"{self.email_data.get('sender')} - {self.email_data.get('subject')}"
        )

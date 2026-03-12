from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Static, Markdown
from textual.reactive import reactive

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class EmailViewer(Vertical):
    """An overlay widget for viewing full email content with Markdown support."""

    can_focus = True

    BINDINGS = [
        Binding("q,escape", "close", "Close Viewer"),
        Binding("k,up", "scroll_up", "Scroll Up", show=False),
        Binding("j,down", "scroll_down", "Scroll Down", show=False),
    ]

    email_id = reactive("")
    content = reactive("")

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields layout components for the email viewer."""
        with Vertical(id="viewer-header-container"):
            yield Static("", id="viewer-subject", markup=False)
            yield Static("", id="viewer-from", markup=False)
            yield Static("", id="viewer-to", markup=False)

        with ScrollableContainer(id="viewer-body-container"):
            yield Markdown("", id="viewer-markdown")

    def watch_email_id(self, old_id: str, new_id: str) -> None:
        """Triggers a content load when the selected email ID changes."""
        if not new_id:
            return

        self.run_worker(lambda: self._load_message_content(new_id), thread=True)

    def _load_message_content(self, email_id: str) -> None:
        """Fetches email data from the database and updates the UI on the main thread."""
        email_data = self.shmail_app.db.get_email(email_id)
        if email_data:
            subject = email_data.get("subject", "(No Subject)")

            # Format sender using clean name if available
            sender_name = email_data.get("sender_name")
            sender_addr = email_data.get("sender_address")
            sender = (
                f"{sender_name} <{sender_addr}>"
                if sender_name
                else email_data.get("sender", "Unknown")
            )

            # We use the raw recipient string for now as it may contain multiple addresses
            recipient = email_data.get("recipient_to", "Unknown")

            body = email_data.get("body", "*No content*")

            def _update_ui():
                self.query_one("#viewer-subject", Static).update(subject)
                self.query_one("#viewer-from", Static).update(f"From: {sender}")
                self.query_one("#viewer-to", Static).update(f"To: {recipient}")
                self.query_one("#viewer-markdown", Markdown).update(body)

            self.app.call_from_thread(_update_ui)

    def on_mount(self) -> None:
        """Initializes the viewer in a hidden state."""
        self.display = False

    def toggle_visibility(self, visible: bool) -> None:
        """Manages the visibility and focus of the viewer overlay."""
        self.display = visible
        if visible:
            self.focus()

    def action_close(self) -> None:
        """Dismisses the viewer and returns focus to the email list."""
        self.toggle_visibility(False)
        self.screen.query_one("#email-list").focus()

    def action_scroll_down(self) -> None:
        """Scrolls the message body downward."""
        self.query_one("#viewer-body-container", ScrollableContainer).scroll_relative(
            y=2
        )

    def action_scroll_up(self) -> None:
        """Scrolls the message body upward."""
        self.query_one("#viewer-body-container", ScrollableContainer).scroll_relative(
            y=-2
        )

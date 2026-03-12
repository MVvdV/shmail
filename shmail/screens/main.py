from typing import TYPE_CHECKING, cast

from shmail.widgets import AppFooter, AppHeader, EmailList, Sidebar, EmailViewer
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class MainScreen(Screen):
    """The primary workspace for navigating labels and viewing emails."""

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields layout components for the main workspace."""
        yield AppHeader()
        with Horizontal():
            yield Sidebar(id="sidebar")
            yield EmailList(id="email-list")
        yield AppFooter()
        yield EmailViewer(id="email-viewer")

    def on_sidebar_label_selected(self, message: Sidebar.LabelSelected) -> None:
        """Handles label selection events and updates the email list."""
        email_list = self.query_one(EmailList)
        email_list.load_label(message.label_id)

    def on_email_list_email_selected(self, message: EmailList.EmailSelected) -> None:
        """Handles email selection events and displays the content in the viewer."""
        viewer = self.query_one(EmailViewer)
        viewer.email_id = message.email_id
        viewer.toggle_visibility(True)

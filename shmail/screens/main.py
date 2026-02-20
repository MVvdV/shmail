from typing import TYPE_CHECKING, cast

from shmail.widgets import AppFooter, AppHeader, EmailList, Sidebar
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class MainScreen(Screen):
    """The main workspace of the application."""

    @property
    def shmail_app(self) -> ShmailApp:
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Horizontal():
            yield Sidebar(id="sidebar")
            yield EmailList(id="email-list")
        yield AppFooter()

    def on_sidebar_label_selected(self, message: Sidebar.LabelSelected) -> None:
        """Handle label selection and refresh the email list."""
        email_list = self.query_one(EmailList)
        email_list.load_label(message.label_id)

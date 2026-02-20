from typing import TYPE_CHECKING, cast
from textual.containers import Horizontal
from textual.widgets import Static

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class AppHeader(Horizontal):
    """Custom production-grade header for Shmail."""

    @property
    def shmail_app(self) -> ShmailApp:
        return cast("ShmailApp", self.app)

    def compose(self):
        yield Static("SHMAIL", id="app-logo")
        # Access the email via our typed property
        email_text = getattr(self.shmail_app, "email", "") or "No Account"
        yield Static(email_text, id="app-account")

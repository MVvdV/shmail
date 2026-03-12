from typing import TYPE_CHECKING, cast
from textual.containers import Horizontal
from textual.widgets import Static

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class AppHeader(Horizontal):
    """The application header bar containing the logo and account information."""

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self):
        """Yields the logo and account display widgets."""
        yield Static("SHMAIL", id="app-logo")
        email_text = getattr(self.shmail_app, "email", "") or "No Account"
        yield Static(email_text, id="app-account")

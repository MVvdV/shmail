from textual.containers import Horizontal
from textual.widgets import Static

from .status_bar import StatusBar


class AppFooter(Horizontal):
    """The application footer bar hosting the version and status bar."""

    def compose(self):
        """Yields the version and status bar widgets."""
        yield Static("v0.1.0", id="app-version")
        yield StatusBar(id="app-status")

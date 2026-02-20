from textual.containers import Horizontal
from textual.widgets import Static

from .status_bar import StatusBar


class AppFooter(Horizontal):
    """Custom production-grade footer hosting the StatusBar."""

    def compose(self):
        yield Static("v0.1.0", id="app-version")
        yield StatusBar(id="app-status")

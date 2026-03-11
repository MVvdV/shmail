import asyncio
from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import ProgressBar, Static

from shmail.widgets import AppFooter, AppHeader

from .main import MainScreen

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class LoadingScreen(Screen):
    """
    [PRODUCTION GRADE]: Purely reactive status viewer.
    Responsibility: Only displays the status of 'ShmailApp.status_message' and 'ShmailApp.status_progress'.
    Constraint: Does NOT own or run the initialization task.
    """

    @property
    def shmail_app(self) -> "ShmailApp":
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Center():
            with Vertical(id="loading-container"):
                # Initial values pulled directly from ShmailApp.
                yield Static(self.shmail_app.status_message, id="loading-status")
                yield ProgressBar(total=100, id="loading-bar")
        yield AppFooter()

    # --- REACTIVE WATCHERS ---

    def watch_app_status_message(self, message: str) -> None:
        """Called when app.status_message changes."""
        self.query_one("#loading-status", Static).update(message)

    def watch_app_status_progress(self, progress: float) -> None:
        """Called when app.status_progress changes."""
        self.query_one("#loading-bar", ProgressBar).update(
            progress=progress * 100
        )  # Convert 0.0-1.0 to 0-100 for the ProgressBar

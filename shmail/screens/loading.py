from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import ProgressBar, Static

from shmail.widgets import AppFooter, AppHeader


if TYPE_CHECKING:
    from shmail.app import ShmailApp


class LoadingScreen(Screen):
    """A reactive screen that displays the progress of background initialization."""

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields layout components for the loading screen."""
        yield AppHeader()
        with Center():
            with Vertical(id="loading-container"):
                yield Static(self.shmail_app.status_message, id="loading-status")
                yield ProgressBar(total=100, id="loading-bar")
        yield AppFooter()

    def on_mount(self) -> None:
        """Registers reactive watchers for application status updates."""
        self.watch(self.app, "status_message", self._update_status, init=True)
        self.watch(self.app, "status_progress", self._update_progress, init=True)

    def _update_status(self, message: str) -> None:
        """Updates the status text widget."""
        for widget in self.query("#loading-status"):
            if isinstance(widget, Static):
                widget.update(message)

    def _update_progress(self, progress: float) -> None:
        """Updates the progress bar widget."""
        for widget in self.query("#loading-bar"):
            if isinstance(widget, ProgressBar):
                widget.update(progress=progress * 100)

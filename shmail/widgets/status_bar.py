from typing import TYPE_CHECKING, cast
from textual.widgets import Static
from textual.reactive import reactive

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class StatusBar(Static):
    """A persistent status bar widget for displaying system feedback messages."""

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    message = reactive("Ready")

    def on_mount(self) -> None:
        """Registers a watcher for the application's global status message."""
        self.watch(self.shmail_app, "status_message", self._update_message)

    def _update_message(self, new_message: str) -> None:
        """Updates the local reactive message property."""
        self.message = new_message

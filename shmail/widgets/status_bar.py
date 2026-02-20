from typing import TYPE_CHECKING, cast
from textual.widgets import Static
from textual.reactive import reactive

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class StatusBar(Static):
    """A persistent status bar for system feedback."""

    @property
    def shmail_app(self) -> ShmailApp:
        return cast("ShmailApp", self.app)

    # Textual's 'reactive' ensures the UI updates whenever this value changes.
    message = reactive("Ready")

    def on_mount(self) -> None:
        """Watch the app's status_message property for changes."""
        self.watch(self.shmail_app, "status_message", self._update_message)

    def _update_message(self, new_message: str) -> None:
        self.message = new_message

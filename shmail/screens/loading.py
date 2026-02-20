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
    """A transitional screen for database and service initialization."""

    @property
    def shmail_app(self) -> ShmailApp:
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Center():
            with Vertical(id="loading-container"):
                yield Static("Initializing Shmail...", id="loading-status")
                yield ProgressBar(total=100, id="loading-bar")
        yield AppFooter()

    async def on_mount(self) -> None:
        """Perform background initialization tasks with user feedback."""
        bar = self.query_one("#loading-bar", ProgressBar)
        status = self.query_one("#loading-status", Static)

        try:
            bar.update(progress=10)
            status.update("Opening database...")

            self.shmail_app.db.initialize()

            # Simulate work for UX
            await asyncio.sleep(0.5)

            bar.advance(40)
            status.update("Loading labels and settings...")
            await asyncio.sleep(0.3)

            bar.update(progress=100)
            status.update("Ready!")
            await asyncio.sleep(0.2)

            self.shmail_app.switch_screen(MainScreen())

        except Exception as e:
            status.update(f"Error: {e}")
            pass

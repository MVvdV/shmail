import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from textual.app import App
from textual.message import Message
from textual.reactive import reactive

from shmail.config import settings
from shmail.screens import LoadingScreen, LoginScreen, MainScreen
from shmail.services.auth import AuthService
from shmail.services.db import db
from shmail.services.sync import SyncResult, SyncService

logger = logging.getLogger(__name__)


class ShmailApp(App):
    """The main application class for Shmail."""

    status_message = reactive("Ready")
    status_progress = reactive(0.0)

    CSS_PATH = "shmail.tcss"

    class SyncComplete(Message):
        """Sent when a background sync finishes."""

        def __init__(self, result: SyncResult) -> None:
            self.result = result
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = db
        self.auth = None
        self.sync_service: Optional[SyncService] = None
        self.settings = settings

    def _setup_logging(self) -> None:
        """Configures rotating file logging for the application."""
        handler = RotatingFileHandler("shmail.log", maxBytes=1000000, backupCount=5)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    async def initialize_session(self, email: str) -> None:
        """Initializes the user session, including services and background sync."""
        self.email = email

        def update_progress(msg: str, progress: Optional[float]) -> None:
            def _apply_update():
                self.status_message = msg
                if progress is not None:
                    self.status_progress = progress

            self.call_from_thread(_apply_update)

        self.auth = AuthService(email, on_progress=update_progress)
        self.sync_service = SyncService(email, on_progress=update_progress)

        worker = self.run_worker(self._run_initial_boot, thread=True, exclusive=True)
        try:
            await worker.wait()
            self.switch_screen(MainScreen())
        except Exception as e:
            logger.error(f"Boot sequence failed: {e}")
            self.status_message = f"Error: {e}"
            self.switch_screen(LoginScreen())

        self.set_interval(self.settings.refresh_interval, self.trigger_sync)

    def _run_initial_boot(self) -> None:
        """Handles database initialization and initial synchronization."""
        self.db.initialize()
        if self.sync_service:
            if not self.db.get_metadata("history_id"):
                self.sync_service.initial_sync()
            else:
                self.status_message = "Restoring previous session..."
                self.status_progress = 1.0

    async def trigger_sync(self) -> None:
        """Spawns a background worker to perform an incremental sync."""
        if not self.sync_service:
            return
        worker = self.run_worker(
            self.sync_service.incremental_sync, thread=True, exclusive=True
        )
        sync_result = await worker.wait()
        self.post_message(self.SyncComplete(sync_result))

    async def on_mount(self) -> None:
        """Application entry point for UI initialization."""
        self._setup_logging()
        self._apply_theme()
        await self.push_screen(LoadingScreen())
        self.run_worker(self._startup())

    def _apply_theme(self) -> None:
        """Applies the default visual theme."""
        self.theme = "textual-dark"

    async def _startup(self) -> None:
        """Performs initial identity discovery and session bootstrapping."""
        self.status_message = "Discovering active identity..."
        email = AuthService().get_active_account()

        if not email:
            email = self.settings.email

        if email:
            await self.initialize_session(email)
        else:
            self.switch_screen(LoginScreen())


if __name__ == "__main__":
    app = ShmailApp()
    app.run()

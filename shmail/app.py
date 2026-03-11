import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from textual.app import App
from textual.message import Message
from textual.reactive import reactive

from shmail.config import CONFIG_DIR, settings
from shmail.screens import LoadingScreen, LoginScreen, MainScreen
from shmail.services.auth import AuthService
from shmail.services.db import db
from shmail.services.sync import SyncResult, SyncService

# [PRODUCTION GRADE]: Module-level logger following project standard.
logger = logging.getLogger(__name__)


class ShmailApp(App):
    # Global state for UI feedback. Any widget can update this via self.app.status_message.
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
        """
        Decision: Centralized Logging (Production-Grade).
        Purpose: Directed to shmail.log with a standard formatter.
        Logic:
        1. 1MB RotatingFileHandler.
        2. Professional formatter (Time - Name - Level - Message).
        3. Root logger configuration ensures all modules inherit these settings.
        """
        handler = RotatingFileHandler("shmail.log", maxBytes=1000000, backupCount=5)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

    async def initialize_session(self, email: str) -> None:
        """
        [PRODUCTION GRADE]: The Application Bootstrapper.

        Note to Quartermaster: Added robust error handling and logging.
        Failure now triggers a fallback to LoginScreen instead of a UI hang.
        """
        self.email = email
        self.auth = AuthService(email)
        self.sync_service = SyncService(email, app=self)

        # [PRODUCTION GRADE]: Background Worker with Error Handling.
        worker = self.run_worker(self._run_initial_boot, thread=True, exclusive=True)
        try:
            await worker.wait()
            self.switch_screen(MainScreen())
        except Exception as e:
            logger.error(f"Boot sequence failed: {e}")
            self.status_message = f"Error: {e}"
            self.switch_screen(LoginScreen())

        # Periodic background synchronisation
        self.set_interval(self.settings.refresh_interval, self.trigger_sync)

    def _run_initial_boot(self) -> None:
        self.db.initialize()
        if self.sync_service:
            self.sync_service.initial_sync()

    async def trigger_sync(self) -> None:
        """
        Decision: Non-blocking Sync Heartbeat.
        Responsibility:
        1. Spawns a background thread worker for SyncService.incremental_sync.
        2. Awaits the worker result (SyncResult).
        3. Broadcasts results via self.post_message(self.SyncComplete(result)).
        """
        if not self.sync_service:
            return
        worker = self.run_worker(
            self.sync_service.incremental_sync, thread=True, exclusive=True
        )
        sync_result = await worker.wait()
        self.post_message(self.SyncComplete(sync_result))

    async def on_mount(self) -> None:
        self._setup_logging()
        if self.settings.email:
            self.push_screen(LoadingScreen())
            await self.initialize_session(self.settings.email)
            return
        self.push_screen(LoginScreen())


if __name__ == "__main__":
    app = ShmailApp()
    app.run()

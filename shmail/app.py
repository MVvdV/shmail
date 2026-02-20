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
        Decision: Centralized Logging.
        Purpose: Directed to CONFIG_DIR/shmail.log to avoid TUI interference.
        Logic: 1MB RotatingFileHandler (using CONFIG_DIR), root level INFO.
        """
        handler = RotatingFileHandler("shmail.log", maxBytes=1000000, backupCount=5)
        logger = logging.getLogger("ShmailLogger")
        logger.addHandler(handler)

    def initialize_session(self, email: str) -> None:
        self.email = email
        self.auth = AuthService(email)
        self.sync_service = SyncService(email, app=self)

        # Periodic background synchronisation
        self.set_interval(self.settings.refresh_interval, self.trigger_sync)

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

    def on_mount(self) -> None:
        """
        Decision: Boot Sequence.
        Flow: Logging -> Identity Check -> Screen Routing.
        Logic:
        1. Setup logging.
        2. If self.settings.email is present: initialize_session() -> LoadingScreen.
        3. If not: LoginScreen.
        """
        self._setup_logging()
        if self.settings.email:
            self.initialize_session(self.settings.email)
            self.push_screen(LoadingScreen())
            return
        self.push_screen(LoginScreen())


if __name__ == "__main__":
    app = ShmailApp()
    app.run()

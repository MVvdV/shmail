import logging
import threading
from logging.handlers import RotatingFileHandler
from typing import Optional

from textual.app import App
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive

from shmail.config import settings
from shmail.screens.message_draft import MessageDraftCloseUpdate
from shmail.screens import LoadingScreen, LoginScreen, MainScreen
from shmail.widgets import AppHeader
from shmail.services.auth import AuthService
from shmail.services.db import db
from shmail.services.label_query import LabelQueryService
from shmail.services.label_state import LabelStateService
from shmail.services.sync import SyncResult, SyncService
from shmail.services.theme import build_textual_theme_with_fallback
from shmail.services.thread_query import ThreadQueryService
from shmail.services.thread_viewer import ThreadViewerService

logger = logging.getLogger(__name__)


class ShmailApp(App):
    """The main application class for Shmail."""

    BINDINGS = [
        Binding(
            settings.keybindings.account, "toggle_account_menu", "Account", show=False
        )
    ]

    email = reactive("")
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
        self.repository = db
        self.auth = None
        self.sync_service: Optional[SyncService] = None
        self.label_query = LabelQueryService(self.repository)
        self.label_state = LabelStateService(self.label_query)
        self.thread_query = ThreadQueryService(self.repository)
        self.thread_viewer = ThreadViewerService(self.repository)
        self.settings = settings
        self._sync_timer = None

    def _setup_logging(self) -> None:
        """Configures rotating file logging for the application."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, RotatingFileHandler) and str(
                getattr(handler, "baseFilename", "")
            ).endswith("shmail.log"):
                return

        handler = RotatingFileHandler("shmail.log", maxBytes=1000000, backupCount=5)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)

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

            if self._thread_id == threading.get_ident():
                _apply_update()
                return
            self.call_from_thread(_apply_update)

        self.auth = AuthService(email, on_progress=update_progress)
        self.sync_service = SyncService(
            email, repository=self.repository, on_progress=update_progress
        )

        worker = self.run_worker(self._run_initial_boot, thread=True, exclusive=True)
        try:
            await worker.wait()
            self.switch_screen(MainScreen())
            if self._sync_timer is not None:
                self._sync_timer.stop()
            self._sync_timer = self.set_interval(
                self.settings.refresh_interval, self.trigger_sync
            )
        except Exception as e:
            logger.error(f"Boot sequence failed: {e}")
            self.status_message = f"Error: {e}"
            self.switch_screen(LoginScreen())

    def _run_initial_boot(self) -> None:
        """Handles database initialization and initial synchronization."""
        self.repository.initialize()
        if self.sync_service:
            if not self.repository.get_metadata("history_id"):
                self.sync_service.run_full_sync()
            else:
                self.call_from_thread(
                    self._set_status, "Restoring previous session...", 1.0
                )

    def _set_status(self, message: str, progress: Optional[float] = None) -> None:
        """Updates global status fields on the UI thread."""
        self.status_message = message
        if progress is not None:
            self.status_progress = progress

    def apply_message_draft_update(
        self, update: MessageDraftCloseUpdate | None
    ) -> None:
        """Apply one compose-close update through the app's refresh authority."""
        if update is None or not update.did_change:
            return

        source_thread_id = (update.source_thread_id or "").strip()
        for screen in self.screen_stack:
            screen_name = screen.__class__.__name__
            if screen_name == "MainScreen":
                self._refresh_main_screen_drafts(screen, source_thread_id)
            elif screen_name == "ThreadMessagesScreen" and source_thread_id:
                reload_thread = getattr(screen, "reload_thread_if_matching", None)
                if callable(reload_thread):
                    reload_thread(source_thread_id)

    def _refresh_main_screen_drafts(self, screen, source_thread_id: str) -> None:
        """Refresh draft-related main-screen surfaces after compose changes."""
        query_one = getattr(screen, "query_one", None)
        if not callable(query_one):
            return

        try:
            labels_sidebar = screen.query_one("#labels-sidebar")
            total_drafts = self.repository.get_total_local_draft_count()
            patch_label = getattr(self.label_state, "patch_label", None)
            apply_label_patch = getattr(labels_sidebar, "apply_label_patch", None)
            if callable(patch_label) and callable(apply_label_patch):
                patch = patch_label("DRAFT", unread_count=total_drafts)
                if patch is not None:
                    apply_label_patch(patch)
                else:
                    refresh_labels = getattr(labels_sidebar, "refresh_labels", None)
                    if callable(refresh_labels):
                        refresh_labels()

            thread_list = screen.query_one("#threads-list")
            current_label = str(getattr(thread_list, "current_label_id", "") or "")
            if current_label.upper() == "DRAFT":
                load_threads = getattr(thread_list, "load_threads", None)
                if callable(load_threads):
                    load_threads("DRAFT")
                return

            if source_thread_id:
                update_marker = getattr(thread_list, "update_thread_draft_marker", None)
                if callable(update_marker):
                    draft_count = self.repository.get_thread_draft_count(
                        source_thread_id
                    )
                    update_marker(source_thread_id, draft_count)
        except NoMatches:
            return

    def sign_in_another_account(self) -> None:
        """Route user to login flow for adding another account."""
        self.status_message = "Sign in with another account..."
        self.status_progress = 0.0
        self.switch_screen(LoginScreen())

    def sign_out_current_account(self) -> None:
        """Sign out current account and route user to login screen."""
        target = (self.email or "").strip()
        if target:
            AuthService().remove_account(target)
        self.email = ""
        self.auth = None
        self.sync_service = None
        if self._sync_timer is not None:
            self._sync_timer.stop()
            self._sync_timer = None
        self.status_progress = 0.0
        self.status_message = "Signed out of current account."
        self.switch_screen(LoginScreen())

    def action_toggle_account_menu(self) -> None:
        """Focus and open the account selector when available."""
        try:
            header = self.screen.query_one(AppHeader)
        except NoMatches:
            return
        header.activate_account_menu()

    async def trigger_sync(self) -> None:
        """Spawns a background worker to perform an incremental sync."""
        if not self.sync_service:
            return
        worker = self.run_worker(
            self.sync_service.incremental_sync, thread=True, exclusive=True
        )
        try:
            sync_result = await worker.wait()
            self.post_message(self.SyncComplete(sync_result))
        except Exception as exc:
            logger.exception("Incremental sync failed")
            self._set_status(f"Sync error: {exc}")

    async def on_mount(self) -> None:
        """Application entry point for UI initialization."""
        self._setup_logging()
        self._apply_theme()
        await self.push_screen(LoadingScreen())
        self.run_worker(self._startup())

    def _apply_theme(self) -> None:
        """Register and apply the configured runtime theme."""
        resolved_theme, warning = build_textual_theme_with_fallback(self.settings.theme)
        self.register_theme(resolved_theme)
        self.theme = resolved_theme.name
        if warning:
            self.status_message = warning

    async def _startup(self) -> None:
        """Performs initial identity discovery and session bootstrapping."""
        self.status_message = "Discovering active identity..."
        email = AuthService().get_active_account()

        if not email:
            email = self.settings.email

        if email:
            self.email = email
            await self.initialize_session(email)
        else:
            self.switch_screen(LoginScreen())


if __name__ == "__main__":
    app = ShmailApp()
    app.run()

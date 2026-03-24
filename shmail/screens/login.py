from typing import TYPE_CHECKING, Optional, cast

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from shmail.services.auth import AuthService
from shmail.widgets import AppFooter, AppHeader

if TYPE_CHECKING:
    from shmail.app import ShmailApp

from .loading import LoadingScreen


class LoginScreen(Screen):
    """A screen to handle Google OAuth authentication."""

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Initiates the OAuth authentication flow."""
        if event.button.id == "login-btn":
            self.shmail_app.status_message = "Waiting for browser authorization..."
            event.button.disabled = True

            def update_progress(msg: str, progress: Optional[float] = None) -> None:
                def _apply_update():
                    self.shmail_app.status_message = msg
                    if progress is not None:
                        self.shmail_app.status_progress = progress

                self.shmail_app.call_from_thread(_apply_update)

            worker = self.run_worker(
                AuthService(on_progress=update_progress).discover_and_authenticate,
                thread=True,
            )
            try:
                email = await worker.wait()
                self.shmail_app.status_message = f"Success! Logged in as {email}"
                self.shmail_app.email = email

                self.shmail_app.switch_screen(LoadingScreen())
                await self.shmail_app.initialize_session(email)
            except Exception as e:
                self.shmail_app.status_message = f"Authentication Error: {e}"
                event.button.disabled = False

    def compose(self) -> ComposeResult:
        """Yields layout components for the login screen."""
        yield AppHeader()
        with Center():
            with Vertical(id="login-container"):
                yield Static("Welcome to Shmail", id="welcome-text")
                yield Button("Login with Google", variant="primary", id="login-btn")
        yield AppFooter()

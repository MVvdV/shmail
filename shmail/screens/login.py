from __future__ import annotations
from typing import TYPE_CHECKING, cast

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
    """A screen to handle Google OAuth login."""

    @property
    def shmail_app(self) -> ShmailApp:
        return cast("ShmailApp", self.app)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Trigger the discovery-first login flow."""
        if event.button.id == "login-btn":
            self.shmail_app.status_message = "Waiting for browser authorization..."
            event.button.disabled = True

            worker = self.run_worker(
                AuthService().discover_and_authenticate, thread=True
            )
            try:
                email = await worker.wait()
                self.shmail_app.status_message = f"Success! Logged in as {email}"
                self.shmail_app.initialize_session(email)
                self.shmail_app.switch_screen(LoadingScreen())
            except Exception as e:
                self.shmail_app.status_message = f"Authentication Error: {e}"
                event.button.disabled = False

    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Center():
            with Vertical(id="login-container"):
                yield Static("Welcome to Shmail", id="welcome-text")
                yield Button("Login with Google", variant="primary", id="login-btn")
        yield AppFooter()

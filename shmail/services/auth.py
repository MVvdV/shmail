import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from shmail.config import CONFIG_DIR
from shmail.services.gmail import GmailService

if TYPE_CHECKING:
    from shmail.app import ShmailApp

# Module-level logger following the project standard
logger = logging.getLogger(__name__)

# The 'modify' scope allows read, send, and archive email.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class AuthService:
    def __init__(self, email: Optional[str] = None, app: Optional["ShmailApp"] = None):
        self.email = email
        self.app = app
        self.service_name = "shmail"
        # Meta service tracks the 'active_account' pointer in the keychain
        self.meta_service = "shmail_meta"

    def get_active_account(self) -> Optional[str]:
        # Registry Check: Query the meta-service for the active user email.
        active_email = keyring.get_password(self.meta_service, "active_account")
        return active_email if active_email else None

    def _update_status(self, message: str, progress: Optional[float] = None) -> None:
        """
        Internal bridge to the Global Progress Bus.
        Updates the TUI status bar and the persistent diagnostic logs.
        """
        # Every user-facing status update is also a diagnostic log entry.
        logger.info(message)
        if self.app:
            self.app.status_message = message
            if progress is not None:
                self.app.status_progress = progress

    def _get_client_info(self):
        """Reads client_id and client_secret from the credentials.json file."""
        path = CONFIG_DIR / "credentials.json"

        if not path.exists():
            raise FileNotFoundError(
                f"Google credentials not found at {path}. "
                "Please download 'credentials.json' from Google Cloud Console."
            )

        with open(path, "r") as f:
            data = json.load(f)

        config = data.get("installed") or data.get("web")
        if not config:
            raise ValueError(
                "Invalid credentials.json format. Expected 'installed' or 'web' key."
            )

        client_id = config.get("client_id")
        client_secret = config.get("client_secret")

        if not client_id or not client_secret:
            raise ValueError("credentials.json is missing client_id or client_secret.")

        return client_id, client_secret

    def _run_oauth_flow(self) -> Credentials:
        # Internal engine to trigger the browser-based OAuth flow.
        path = CONFIG_DIR / "credentials.json"
        flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
        creds = flow.run_local_server(port=0)
        return creds

    def _save_to_keyring(self, email: str, creds: Credentials) -> None:
        # Centralized persistence for both tokens and the active account registry.
        if creds.refresh_token:
            keyring.set_password(self.service_name, email, creds.refresh_token)
            keyring.set_password(self.meta_service, "active_account", email)
        else:
            # Refresh token is mandatory for production-grade persistence.
            raise ValueError("No refresh token returned from Google.")

    def get_credentials(self) -> Credentials:
        """Main method to get valid Google API credentials for current self.email."""
        if not self.email:
            raise ValueError("AuthService requires an email to retrieve credentials.")

        creds = None
        refresh_token = keyring.get_password(self.service_name, self.email)
        client_id, client_secret = self._get_client_info()

        if refresh_token:
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self._update_status(f"Refreshing credentials for {self.email}...", 0.5)
                creds.refresh(Request())
            else:
                self._update_status(
                    f"Opening browser for {self.email} authorization...", 0.2
                )
                creds = self._run_oauth_flow()

            # Ensure the registry is updated with the latest valid credentials.
            self._save_to_keyring(self.email, creds)
            self._update_status(f"Credentials ready for {self.email}", 1.0)

        return creds

    def discover_and_authenticate(self) -> str:
        """
        Discovery flow: Browser -> Discover Email -> Keyring.
        Used for first-time login to identify who authorized the app.
        """
        try:
            self._update_status("Opening browser for Google Auth...", 0.2)
            creds = self._run_oauth_flow()

            self._update_status("Discovering authorized email address...", 0.8)
            # Use a one-off service instance to identify the user.
            profile = GmailService(creds).get_profile()
            discovered_email = profile["emailAddress"]

            # Registration
            self.email = discovered_email
            self._save_to_keyring(discovered_email, creds)

            self._update_status(f"Discovery success: {discovered_email}", 1.0)
            return discovered_email
        except Exception:
            # Capture the technical details for developer diagnostics.
            logger.exception("Discovery authentication failed")
            raise

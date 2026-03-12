import json
import logging
from typing import TYPE_CHECKING, Callable, Optional, cast

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from shmail.config import CONFIG_DIR
from shmail.services.gmail import GmailService

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class AuthService:
    """Manages Google OAuth authentication, token refreshing, and secure credential storage."""

    def __init__(
        self, email: Optional[str] = None, on_progress: Optional[Callable] = None
    ):
        self.email = email
        self.on_progress = on_progress
        self.service_name = "shmail"
        self.meta_service = "shmail_meta"

    def get_active_account(self) -> Optional[str]:
        """Retrieves the email of the currently active account from the OS keyring."""
        active_email = keyring.get_password(self.meta_service, "active_account")
        return active_email if active_email else None

    def _update_status(self, message: str, progress: Optional[float] = None) -> None:
        """Reports progress updates via the provided callback and logs the message."""
        logger.info(message)
        if self.on_progress:
            self.on_progress(message, progress)

    def _get_client_info(self):
        """Reads client ID and secret from the local credentials configuration."""
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
        """Executes the local server OAuth flow to obtain user authorization."""
        path = CONFIG_DIR / "credentials.json"
        flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        return cast(Credentials, creds)

    def _save_to_keyring(self, email: str, creds: Credentials) -> None:
        """Securely stores the refresh token and active account pointer in the OS keyring."""
        if creds.refresh_token:
            keyring.set_password(self.service_name, email, creds.refresh_token)
            keyring.set_password(self.meta_service, "active_account", email)
        else:
            raise ValueError("No refresh token returned from Google.")

    def get_credentials(self) -> Credentials:
        """Retrieves or refreshes valid Google API credentials for the current user."""
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
            if creds and creds.refresh_token:
                self._update_status(f"Refreshing credentials for {self.email}...", 0.5)
                creds.refresh(Request())
            else:
                self._update_status(
                    f"Opening browser for {self.email} authorization...", 0.2
                )
                creds = self._run_oauth_flow()

            self._save_to_keyring(self.email, creds)
            self._update_status(f"Credentials ready for {self.email}", 1.0)

        return creds

    def discover_and_authenticate(self) -> str:
        """Performs first-time authentication and registers the authorized email address."""
        try:
            self._update_status("Opening browser for Google Auth...", 0.2)
            creds = self._run_oauth_flow()

            self._update_status("Discovering authorized email address...", 0.8)
            profile = GmailService(creds).get_profile()
            discovered_email = profile["emailAddress"]

            self.email = discovered_email
            self._save_to_keyring(discovered_email, creds)

            self._update_status(f"Discovery success: {discovered_email}", 1.0)
            return discovered_email
        except Exception:
            logger.exception("Discovery authentication failed")
            raise

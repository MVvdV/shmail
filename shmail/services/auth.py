import json
from pathlib import Path

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from shmail.config import CONFIG_DIR

# The 'modify' scope allows us to read, send, and archive email.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class AuthService:
    def __init__(self, email: str):
        self.email = email
        self.service_name = "shmail"

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

    def get_credentials(self) -> Credentials:
        """Main method to get valid Google API credentials."""
        # 1. Fetch existing token and client info
        refresh_token = keyring.get_password(self.service_name, self.email)
        client_id, client_secret = self._get_client_info()

        creds = None
        if refresh_token:
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )

        # 2. Check if we need to refresh or login
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                path = CONFIG_DIR / "credentials.json"
                flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
                creds = flow.run_local_server(port=0)

            # 3. Securely store the new refresh token
            keyring.set_password(self.service_name, self.email, creds.refresh_token)

        return creds

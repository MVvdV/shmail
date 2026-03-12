import logging
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GmailService:
    """A wrapper for the Google Gmail API providing high-level email operations."""

    def __init__(self, credentials: Credentials):
        """Initializes the Gmail API service using the provided credentials."""
        self.service: Any = build("gmail", "v1", credentials=credentials)

    def list_messages(
        self, query: str = "", max_results: int = 500
    ) -> List[Dict[str, Any]]:
        """Retrieves a list of messages matching the specified query."""
        try:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
            return results.get("messages", [])
        except Exception:
            logger.exception(f"Failed to list messages with query: {query}")
            raise

    def get_message(self, message_id: str, format: str = "raw") -> Dict[str, Any]:
        """Fetches the full details of a specific message by its ID."""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format=format)
                .execute()
            )
            return message
        except Exception:
            logger.exception(f"Failed to get message: {message_id}")
            raise

    def list_labels(self) -> List[Dict[str, Any]]:
        """Retrieves all Gmail labels associated with the user account."""
        try:
            results = self.service.users().labels().list(userId="me").execute()
            return results.get("labels", [])
        except Exception:
            logger.exception("Failed to list labels")
            raise

    def get_profile(self) -> Dict[str, Any]:
        """Retrieves the user's Gmail profile information."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile
        except Exception:
            logger.exception("Failed to fetch user profile")
            raise

    def list_history(
        self, start_history_id: str, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieves incremental history records since a specific history ID."""
        try:
            history_records = (
                self.service.users()
                .history()
                .list(
                    userId="me", startHistoryId=start_history_id, pageToken=page_token
                )
                .execute()
            )
            return history_records
        except Exception:
            logger.exception(f"Failed to fetch history since: {start_history_id}")
            raise

    def trash_message(self, message_id: str):
        """Moves the specified message to the trash."""
        try:
            self.service.users().messages().trash(userId="me", id=message_id).execute()
        except Exception:
            logger.exception(f"Failed to trash message: {message_id}")
            raise

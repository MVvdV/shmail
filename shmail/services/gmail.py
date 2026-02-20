import logging
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

# Module-level logger following the project standard
logger = logging.getLogger(__name__)


class GmailService:
    """Wrapper for the Google Gmail API."""

    def __init__(self, credentials: Credentials):
        # The 'build' function creates a service object that lets us call Gmail API methods.
        self.service: Resource = build("gmail", "v1", credentials=credentials)

    def list_messages(
        self, query: str = "", max_results: int = 500
    ) -> List[Dict[str, Any]]:
        """Lists message summaries matching the query."""
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
        """Gets a specific message by ID."""
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
        """Lists all labels for the user."""
        try:
            results = self.service.users().labels().list(userId="me").execute()
            return results.get("labels", [])
        except Exception:
            logger.exception("Failed to list labels")
            raise

    def get_profile(self) -> Dict[str, Any]:
        """Gets the user's Gmail profile (includes current historyId)."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile
        except Exception:
            logger.exception("Failed to fetch user profile")
            raise

    def list_history(
        self, start_history_id: str, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Lists history records since start_history_id.
        Returns a dict containing 'history' (list of records) and 'historyId' (newest).
        """
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
        """Moves a message to the trash."""
        try:
            self.service.users().messages().trash(userId="me", id=message_id).execute()
        except Exception:
            logger.exception(f"Failed to trash message: {message_id}")
            raise

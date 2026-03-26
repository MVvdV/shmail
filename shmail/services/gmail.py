"""Thin Gmail API wrapper used by sync and auth services."""

import logging
from typing import Any, Dict, List, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GmailService:
    """Provide high-level Gmail API operations."""

    def __init__(self, credentials: Credentials):
        """Initialize the Gmail API client with credentials."""
        self.service: Any = build("gmail", "v1", credentials=credentials)

    def list_messages(
        self, query: str = "", max_results: int = 500
    ) -> List[Dict[str, Any]]:
        """Return messages that match the query."""
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
        """Return message details for the given ID."""
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
        """Return labels for the authenticated account."""
        try:
            results = self.service.users().labels().list(userId="me").execute()
            return results.get("labels", [])
        except Exception:
            logger.exception("Failed to list labels")
            raise

    def create_label(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Create one user label and return the provider response."""
        try:
            return (
                self.service.users().labels().create(userId="me", body=body).execute()
            )
        except Exception:
            logger.exception("Failed to create label")
            raise

    def patch_label(self, label_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Patch one label and return the provider response."""
        try:
            return (
                self.service.users()
                .labels()
                .patch(userId="me", id=label_id, body=body)
                .execute()
            )
        except Exception:
            logger.exception("Failed to patch label: %s", label_id)
            raise

    def delete_label(self, label_id: str) -> None:
        """Delete one label from the provider."""
        try:
            self.service.users().labels().delete(userId="me", id=label_id).execute()
        except Exception:
            logger.exception("Failed to delete label: %s", label_id)
            raise

    def get_profile(self) -> Dict[str, Any]:
        """Return Gmail profile metadata for the current account."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile
        except Exception:
            logger.exception("Failed to fetch user profile")
            raise

    def list_history(
        self, start_history_id: str, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return incremental history since a starting history ID."""
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

    def trash_message(self, message_id: str) -> None:
        """Move the specified message to trash."""
        try:
            self.service.users().messages().trash(userId="me", id=message_id).execute()
        except Exception:
            logger.exception(f"Failed to trash message: {message_id}")
            raise

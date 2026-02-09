from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build


class GmailService:
    """Wrapper for the Google Gmail API."""

    def __init__(self, credentials: Credentials):
        # The 'build' function creates a service object that lets us call Gmail API methods.
        self.service: Resource = build("gmail", "v1", credentials=credentials)

    def list_messages(
        self, query: str = "", max_results: int = 500
    ) -> List[Dict[str, Any]]:
        """Lists message summaries matching the query."""
        results = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        return results.get("messages", [])

    def get_message(self, message_id: str, format: str = "raw") -> Dict[str, Any]:
        """Gets a specific message by ID."""
        message = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format=format)
            .execute()
        )
        return message

    def list_labels(self) -> List[Dict[str, Any]]:
        """Lists all labels for the user."""
        results = self.service.users().labels().list(userId="me").execute()
        return results.get("labels", [])

    def trash_message(self, message_id: str):
        """Moves a message to the trash."""
        self.service.users().messages().trash(userId="me", id=message_id).execute()

import base64
import email.utils
from datetime import datetime
from email import message_from_bytes
from typing import Any, Dict, List

from shmail.models import Email
from shmail.services.auth import AuthService
from shmail.services.db import db
from shmail.services.gmail import GmailService


class SyncService:
    def __init__(self, email: str):
        self.email = email
        self.auth = AuthService(email)
        self.gmail = GmailService(self.auth.get_credentials())

    def initial_sync(self):
        """Fetches the last 500 messages and syncs them to the local DB."""
        # 1. First sync labels so we have the master list
        self.sync_labels()

        # 2. Sync messages
        messages = self.gmail.list_messages()
        for m in messages:
            message_data = self.gmail.get_message(m["id"])
            email_obj = self._parse_gmail_message(
                message_id=m["id"], thread_id=m["threadId"], message_data=message_data
            )
            db.upsert_email(email_obj)

    def sync_labels(self):
        """
        Orchestrates fetching labels from Gmail and saving them to the DB.
        """
        labels = self.gmail.list_labels()
        for label in labels:
            db.upsert_label(label["id"], label["name"], label["type"])

    def _parse_gmail_message(
        self, message_id: str, thread_id: str, message_data: Dict[str, Any]
    ) -> Email:
        """Converts raw Gmail API response into our Email model."""
        raw_b64 = message_data["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64)
        mime_msg = message_from_bytes(raw_bytes)

        # Body extraction logic
        body = ""
        if mime_msg.is_multipart():
            for part in mime_msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="replace")
                    break
        else:
            payload = mime_msg.get_payload(decode=True)
            if payload:
                body = payload.decode(errors="replace")

        # Parsing the date header to a datetime object
        date_str = mime_msg.get("date")
        try:
            timestamp = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            # Fallback to Gmail's internal timestamp (milliseconds to seconds)
            ms_val = int(message_data.get("internalDate", 0))
            timestamp = datetime.fromtimestamp(ms_val / 1000.0)

        return Email(
            id=message_id,
            thread_id=thread_id,
            subject=mime_msg.get("subject", "(No Subject)"),
            sender=mime_msg.get("from", "(Unknown Sender)"),
            snippet=message_data.get("snippet", ""),
            body=body,
            timestamp=timestamp,
            is_read="UNREAD" not in message_data.get("labelIds", []),
            has_attachments=any(part.get_filename() for part in mime_msg.walk())
            if mime_msg.is_multipart()
            else False,
        )

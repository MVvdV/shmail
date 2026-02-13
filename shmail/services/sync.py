import base64
import email.utils
from datetime import datetime
from email import message_from_bytes
from typing import Any, Dict, List

from googleapiclient.errors import HttpError

from shmail.models import Email, GmailHistoryResponse, Label
from shmail.services.auth import AuthService
from shmail.services.db import db
from shmail.services.gmail import GmailService


class SyncService:
    def __init__(self, email: str, database=None):
        self.email = email
        self.auth = AuthService(email)
        self.gmail = GmailService(self.auth.get_credentials())
        self.db = database or db

    def initial_sync(self):
        """Fetches the last 500 messages and syncs them to the local DB."""
        # 1. First sync labels so we have the master list
        self.sync_labels()

        # 2. Sync messages
        messages = self.gmail.list_messages()
        for m in messages:
            message_data = self.gmail.get_message(m["id"])
            email_obj = self._parse_gmail_message(
                message_id=m["id"],
                thread_id=m["threadId"],
                message_data=message_data,
                label_ids=message_data.get("labelIds", []),
            )
            self.db.upsert_email(email_obj)

        # 3. Get profile and save initial history_id to metadata
        profile = self.gmail.get_profile()
        self.db.set_metadata("history_id", profile["historyId"])

    def incremental_sync(self):
        history_id = self.db.get_metadata("history_id")
        if history_id is None:
            self.initial_sync()
            return

        page_token = None

        try:
            while True:
                history_records = self.gmail.list_history(
                    history_id, page_token=page_token
                )
                data = GmailHistoryResponse(**history_records)

                if not data.history:
                    break

                for record in data.history:
                    for added in record.messagesAdded:
                        try:
                            message_data = self.gmail.get_message(added.message.id)
                            email_obj = self._parse_gmail_message(
                                message_id=added.message.id,
                                thread_id=added.message.threadId or "",
                                message_data=message_data,
                                label_ids=added.message.labelIds,
                            )
                            self.db.upsert_email(email_obj)
                        except HttpError as e:
                            if e.resp.status == 404:
                                continue  # Message already gone
                            raise e

                    for label_change in record.labelsAdded:
                        self.db.update_labels(
                            label_change.message.id,
                            added_label_ids=label_change.labelIds,
                        )

                    for label_change in record.labelsRemoved:
                        self.db.update_labels(
                            label_change.message.id,
                            removed_label_ids=label_change.labelIds,
                        )

                    for deleted in record.messagesDeleted:
                        self.db.remove_email(deleted.message.id)

                # Update current history_id to the most recent one
                self.db.set_metadata("history_id", data.historyId)

                # Check if there's more data to fetch
                page_token = data.nextPageToken
                if not page_token:
                    break

        except HttpError as error:
            if error.resp.status in [404, 410]:
                print("History ID expired. Performing full sync...")
                self.initial_sync()
            else:
                raise error

    def sync_labels(self):
        """
        Orchestrates fetching labels from Gmail and saving them to the DB.
        """
        labels = self.gmail.list_labels()
        for label in labels:
            self.db.upsert_label(label["id"], label["name"], label["type"])

    def _parse_gmail_message(
        self,
        message_id: str,
        thread_id: str,
        message_data: Dict[str, Any],
        label_ids: List[str],
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
            is_read="UNREAD" not in label_ids,
            has_attachments=any(part.get_filename() for part in mime_msg.walk())
            if mime_msg.is_multipart()
            else False,
            labels=[Label(id=label_id, name="", type="") for label_id in label_ids],
        )

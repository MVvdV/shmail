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
from shmail.services.parser import MessageParser


class SyncService:
    def __init__(self, email: str, database=None):
        self.email = email
        self.auth = AuthService(email)
        self.gmail = GmailService(self.auth.get_credentials())
        self.db = database or db
        self.parser = MessageParser()

    def initial_sync(self):
        # Fetches the last 500 messages and syncs them to the local DB.
        # 1. First sync labels so we have the master list
        self.sync_labels()

        # 2. Sync messages
        messages = self.gmail.list_messages()

        with self.db.transaction() as conn:
            for m in messages:
                message_data = self.gmail.get_message(m["id"])
                parsed = self.parser.parse_gmail_response(
                    message_id=m["id"],
                    thread_id=m["threadId"],
                    message_data=message_data,
                    label_ids=message_data.get("labelIds", []),
                )
                self.db.upsert_email(conn, parsed.email)
                for contact in parsed.contacts:
                    self.db.upsert_contact(
                        conn, contact.email, contact.name, contact.timestamp.isoformat()
                    )

            # 3. Get profile and save initial history_id to metadata
            profile = self.gmail.get_profile()
            self.db.set_metadata(conn, "history_id", profile["historyId"])

    def incremental_sync(self):
        # Synchronizes changes (new messages, label updates, deletions) since the last sync.
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

                with self.db.transaction() as conn:
                    for record in data.history:
                        self._process_history_record(conn, record)

                    # Update current history_id to the most recent one
                    self.db.set_metadata(conn, "history_id", data.historyId)

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
        # Fetches labels from Gmail and saves them to the DB.
        labels = self.gmail.list_labels()
        with self.db.transaction() as conn:
            for label in labels:
                self.db.upsert_label(conn, label["id"], label["name"], label["type"])

    def _process_history_record(self, conn, record):
        # Processes individual history events (added, removed, deleted) within a transaction.
        for added in record.messagesAdded:
            try:
                message_data = self.gmail.get_message(added.message.id)
                parsed = self.parser.parse_gmail_response(
                    message_id=added.message.id,
                    thread_id=added.message.threadId or "",
                    message_data=message_data,
                    label_ids=added.message.labelIds,
                )
                self.db.upsert_email(conn, parsed.email)
                for contact in parsed.contacts:
                    self.db.upsert_contact(
                        conn,
                        contact.email,
                        contact.name,
                        contact.timestamp.isoformat(),
                    )
            except HttpError as e:
                if e.resp.status == 404:
                    continue  # Message already gone
                raise e

        for label_change in record.labelsAdded:
            self.db.update_labels(
                conn,
                label_change.message.id,
                added_label_ids=label_change.labelIds,
                removed_label_ids=[],
            )
        for label_change in record.labelsRemoved:
            self.db.update_labels(
                conn,
                label_change.message.id,
                added_label_ids=[],
                removed_label_ids=label_change.labelIds,
            )
        for deleted in record.messagesDeleted:
            self.db.remove_email(conn, deleted.message.id)

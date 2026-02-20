import base64
import email.utils
import logging
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from googleapiclient.errors import HttpError

from shmail.models import Email, GmailHistoryResponse, Label
from shmail.services.auth import AuthService
from shmail.services.db import db
from shmail.services.gmail import GmailService
from shmail.services.parser import MessageParser

if TYPE_CHECKING:
    from shmail.app import ShmailApp

# Module-level logger following the project standard
logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Feedback on what changed during a sync cycle."""

    added: int = 0
    removed: int = 0
    labels_changed: int = 0

    @property
    def any_changes(self) -> bool:
        """Determines if anything actually happened during the sync."""
        return any([self.added, self.removed, self.labels_changed])


class SyncService:
    def __init__(self, email: str, database=None, app: Optional["ShmailApp"] = None):
        self.email = email
        self.auth = AuthService(email)
        self.gmail = GmailService(self.auth.get_credentials())
        self.db = database or db
        self.app = app
        self.parser = MessageParser()

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

    def initial_sync(self):
        """
        Fetches the last 500 messages and syncs them to the local DB.
        Decision: Progress is reported directly via self.app (Progress Bus).
        """
        self._update_status("Syncing labels...", 0.05)

        self.sync_labels()

        self._update_status("Fetching message list...", 0.1)
        messages = self.gmail.list_messages()
        total = len(messages)

        with self.db.transaction() as conn:
            for i, m in enumerate(messages):
                progress = 0.1 + ((i + 1) / total) * 0.85
                self._update_status(f"Syncing email {i + 1} of {total}...", progress)

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

            self._update_status("Initial sync complete.", 1.0)
            profile = self.gmail.get_profile()
            self.db.set_metadata(conn, "history_id", profile["historyId"])

    def incremental_sync(self) -> SyncResult:
        """
        Synchronizes changes since the last sync.
        Returns a SyncResult summary for the UI to react to.
        """
        self._update_status("Checking for changes...", 0.05)
        result = SyncResult()
        history_id = self.db.get_metadata("history_id")

        if history_id is None:
            self._update_status("No history_id found. Performing initial sync.", 1.0)
            self.initial_sync()
            # We return a dummy result with one change to trigger a UI refresh
            return SyncResult(added=1)

        self._update_status(f"Starting sync from history_id: {history_id}", 0.1)
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
                        self._process_history_record(conn, record, result)

                    # Update current history_id to the most recent one
                    self.db.set_metadata(conn, "history_id", data.historyId)

                # Check if there's more data to fetch
                page_token = data.nextPageToken
                if not page_token:
                    break

            self._update_status(
                f"Sync complete. Added: {result.added}, Removed: {result.removed}", 1.0
            )
            return result

        except HttpError as error:
            if error.resp.status in [404, 410]:
                logger.warning("History ID expired. Performing full sync...")
                self.initial_sync()
                return SyncResult(added=1)
            else:
                logger.error(f"Sync failed with HTTP error: {error}")
                raise error

    def sync_labels(self):
        # Fetches labels from Gmail and saves them to the DB.
        labels = self.gmail.list_labels()
        with self.db.transaction() as conn:
            for label in labels:
                self.db.upsert_label(conn, label["id"], label["name"], label["type"])

    def _process_history_record(self, conn, record, result: SyncResult):
        # Processes individual history events (added, removed, deleted) within a transaction.
        for added in record.messagesAdded:
            result.added += 1
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
            result.labels_changed += 1
            self.db.update_labels(
                conn,
                label_change.message.id,
                added_label_ids=label_change.labelIds,
                removed_label_ids=[],
            )
        for label_change in record.labelsRemoved:
            result.labels_changed += 1
            self.db.update_labels(
                conn,
                label_change.message.id,
                added_label_ids=[],
                removed_label_ids=label_change.labelIds,
            )
        for deleted in record.messagesDeleted:
            result.removed += 1
            self.db.remove_email(conn, deleted.message.id)

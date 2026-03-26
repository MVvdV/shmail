"""Synchronization orchestration for Gmail-to-local state updates."""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from googleapiclient.errors import HttpError

from shmail.models import GmailHistoryResponse
from shmail.config import settings
from shmail.services.auth import AuthService
from shmail.services.db import DatabaseRepository, db
from shmail.services.gmail import GmailService
from shmail.services.parser import MessageParser

HistoryOperation = dict[str, Any]

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Store counts for changes applied during one sync cycle."""

    added: int = 0
    removed: int = 0
    labels_changed: int = 0

    @property
    def any_changes(self) -> bool:
        """Return True when the sync applied any changes."""
        return any([self.added, self.removed, self.labels_changed])


class SyncService:
    """Synchronize local storage with Gmail state."""

    def __init__(
        self,
        email: str,
        repository: DatabaseRepository | None = None,
        on_progress: Optional[Callable[[str, Optional[float]], None]] = None,
    ):
        self.email = email
        self.on_progress = on_progress
        self.auth = AuthService(email, on_progress=on_progress)
        self.repository: DatabaseRepository = repository or db
        self.parser = MessageParser()
        self._gmail: Optional[GmailService] = None

    @property
    def gmail(self) -> GmailService:
        """Return a lazily initialized Gmail service client."""
        if self._gmail is None:
            creds = self.auth.get_credentials()
            self._gmail = GmailService(creds)
        return self._gmail

    def _update_status(self, message: str, progress: Optional[float] = None) -> None:
        """Log and publish sync progress updates."""
        logger.info(message)
        if self.on_progress:
            self.on_progress(message, progress)

    def run_full_sync(self, *, reset_local_messages: bool = False) -> SyncResult:
        """Fetch a full provider snapshot and reconcile local cache state."""
        self._update_status("Syncing labels...", 0.05)
        self.sync_labels()

        self._update_status("Connecting to Gmail API...", 0.08)
        self._update_status("Fetching message list...", 0.1)
        messages = self.gmail.list_messages(max_results=settings.max_messages_cached)
        total = len(messages)
        parsed_messages = []
        contacts = []

        for i, m in enumerate(messages):
            progress = 0.1 + ((i + 1) / max(total, 1)) * 0.85
            self._update_status(f"Syncing message {i + 1} of {total}...", progress)

            message_data = self.gmail.get_message(m["id"])
            parsed = self.parser.parse_gmail_response(
                message_id=m["id"],
                thread_id=m["threadId"],
                message_data=message_data,
                label_ids=message_data.get("labelIds", []),
            )
            parsed_messages.append(parsed.message)
            contacts.extend(parsed.contacts)

        profile = self.gmail.get_profile()
        removed = self.repository.count_messages() if reset_local_messages else 0
        with self.repository.transaction() as conn:
            if reset_local_messages:
                self.repository.reset_message_cache(conn)
            for message in parsed_messages:
                self.repository.upsert_message(conn, message)
            for contact in contacts:
                self.repository.upsert_contact(
                    conn, contact.email, contact.name, contact.timestamp.isoformat()
                )
            self.repository.set_metadata(conn, "history_id", profile["historyId"])

        self._update_status("Initial sync complete.", 1.0)
        return SyncResult(added=len(parsed_messages), removed=removed)

    def incremental_sync(self) -> SyncResult:
        """Apply Gmail history deltas since the last successful sync."""
        self._update_status("Checking for changes...", 0.05)
        result = SyncResult()
        history_id = self.repository.get_metadata("history_id")

        if history_id is None:
            self._update_status("No history_id found. Performing initial sync.", 1.0)
            return self.run_full_sync(reset_local_messages=False)

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

                operations = [
                    self._collect_history_operations(record) for record in data.history
                ]

                with self.repository.transaction() as conn:
                    for operation in operations:
                        self._apply_history_operations(conn, operation, result)

                    self.repository.set_metadata(conn, "history_id", data.historyId)

                page_token = data.nextPageToken
                if not page_token:
                    break

            self._update_status(
                f"Sync complete. Added: {result.added}, Removed: {result.removed}", 1.0
            )
            return result

        except HttpError as error:
            if error.resp.status in [404, 410]:
                logger.warning(
                    "History ID expired. Performing full cache reconciliation."
                )
                return self.run_full_sync(reset_local_messages=True)
            else:
                logger.error(f"Sync failed with HTTP error: {error}")
                raise error

    def sync_labels(self) -> None:
        """Refresh the local label registry from Gmail."""
        labels = self.gmail.list_labels()
        valid_label_ids = [str(label["id"]) for label in labels if label.get("id")]
        with self.repository.transaction() as conn:
            for label in labels:
                self.repository.upsert_label(
                    conn,
                    label["id"],
                    label["name"],
                    label["type"],
                    label_list_visibility=label.get("labelListVisibility"),
                    message_list_visibility=label.get("messageListVisibility"),
                    background_color=(label.get("color") or {}).get("backgroundColor"),
                    text_color=(label.get("color") or {}).get("textColor"),
                )
            self.repository.prune_labels(conn, valid_label_ids)

    def _collect_history_operations(self, record) -> HistoryOperation:
        """Collect network-backed record operations before opening a transaction."""
        added_messages = []
        for added in record.messagesAdded:
            try:
                message_data = self.gmail.get_message(added.message.id)
                parsed = self.parser.parse_gmail_response(
                    message_id=added.message.id,
                    thread_id=added.message.threadId or "",
                    message_data=message_data,
                    label_ids=added.message.labelIds,
                )
                added_messages.append(parsed)
            except HttpError as e:
                if e.resp.status == 404:
                    continue
                raise e

        return {
            "added_messages": added_messages,
            "added_count": len(added_messages),
            "labels_added": list(record.labelsAdded),
            "labels_removed": list(record.labelsRemoved),
            "messages_deleted": list(record.messagesDeleted),
        }

    def _apply_history_operations(
        self, conn, operation: HistoryOperation, result: SyncResult
    ) -> None:
        """Apply prepared history operations in a single transaction."""
        result.added += int(operation.get("added_count", 0))

        for parsed in operation.get("added_messages", []):
            self.repository.upsert_message(conn, parsed.message)
            for contact in parsed.contacts:
                self.repository.upsert_contact(
                    conn,
                    contact.email,
                    contact.name,
                    contact.timestamp.isoformat(),
                )

        for label_change in operation.get("labels_added", []):
            result.labels_changed += 1
            self.repository.update_labels(
                conn,
                label_change.message.id,
                added_label_ids=label_change.labelIds,
                removed_label_ids=[],
            )

        for label_change in operation.get("labels_removed", []):
            result.labels_changed += 1
            self.repository.update_labels(
                conn,
                label_change.message.id,
                added_label_ids=[],
                removed_label_ids=label_change.labelIds,
            )

        for deleted in operation.get("messages_deleted", []):
            result.removed += 1
            self.repository.remove_message(conn, deleted.message.id)

"""Local draft-message lifecycle service for compose workflows."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from shmail.models import MessageDraft
from shmail.services.db import db


class MessageDraftService:
    """Manage local message draft creation, retrieval, and persistence."""

    def __init__(self, database=None):
        self.db = database or db

    def resolve_or_create_draft(
        self,
        mode: str,
        to_addresses: str,
        cc_addresses: str,
        bcc_addresses: str,
        subject: str,
        body: str,
        source_message_id: str | None,
        source_thread_id: str | None,
    ) -> MessageDraft:
        """Load existing seed draft when present, else create and persist one."""
        existing = None
        if source_message_id or source_thread_id:
            existing = self.db.get_message_draft_by_source(
                mode=mode,
                source_message_id=source_message_id,
                source_thread_id=source_thread_id,
            )
        if existing:
            return self._row_to_message_draft(existing)

        now = datetime.now()
        draft = MessageDraft(
            id=str(uuid4()),
            mode=mode,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            bcc_addresses=bcc_addresses,
            subject=subject,
            body=body,
            source_message_id=source_message_id,
            source_thread_id=source_thread_id,
            created_at=now,
            updated_at=now,
        )
        self.save_draft(draft)
        return draft

    def get_draft(self, draft_id: str) -> MessageDraft | None:
        """Load one draft by identifier from local storage."""
        row = self.db.get_message_draft(draft_id)
        if row is None:
            return None
        return self._row_to_message_draft(row)

    def save_draft(self, draft: MessageDraft) -> MessageDraft:
        """Persist draft updates and refresh updated timestamp."""
        refreshed = draft.model_copy(update={"updated_at": datetime.now()})
        with self.db.transaction() as conn:
            self.db.upsert_message_draft(conn, refreshed)
        return refreshed

    def delete_draft(self, draft_id: str) -> None:
        """Delete one persisted message draft."""
        with self.db.transaction() as conn:
            self.db.remove_message_draft(conn, draft_id)

    @staticmethod
    def _row_to_message_draft(row: dict) -> MessageDraft:
        """Convert a DB row into a MessageDraft model instance."""
        created_raw = str(row.get("created_at") or "")
        updated_raw = str(row.get("updated_at") or "")
        now = datetime.now()
        try:
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except Exception:
            created_at = now
        try:
            updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
        except Exception:
            updated_at = created_at

        return MessageDraft(
            id=str(row.get("id") or ""),
            mode=str(row.get("mode") or "new"),
            to_addresses=str(row.get("to_addresses") or ""),
            cc_addresses=str(row.get("cc_addresses") or ""),
            bcc_addresses=str(row.get("bcc_addresses") or ""),
            subject=str(row.get("subject") or ""),
            body=str(row.get("body") or ""),
            source_message_id=(
                str(row.get("source_message_id"))
                if row.get("source_message_id") is not None
                else None
            ),
            source_thread_id=(
                str(row.get("source_thread_id"))
                if row.get("source_thread_id") is not None
                else None
            ),
            created_at=created_at,
            updated_at=updated_at,
        )

"""Local-first outbound send queue service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from email.message import EmailMessage
from uuid import uuid4

from shmail.models import MessageDraft
from shmail.services.db import DatabaseRepository, db
from shmail.services.message_draft import MessageDraftService
from shmail.services.time import now_utc


@dataclass
class QueuedSendResult:
    """Summarize one locally queued outbound send."""

    draft_id: str
    source_thread_id: str | None


class OutboundMessageService:
    """Queue local sends without replaying them to a provider yet."""

    def __init__(self, repository: DatabaseRepository | None = None) -> None:
        self.repository = repository or db
        self.drafts = MessageDraftService(self.repository)

    def queue_send(
        self, *, account_id: str, provider_key: str, draft: MessageDraft
    ) -> QueuedSendResult:
        """Freeze one draft as a queued outbound send and log the intent."""
        queued = self.drafts.queue_draft_for_send(draft)
        payload = {
            "draft_id": queued.id,
            "source_message_id": queued.source_message_id,
            "source_thread_id": queued.source_thread_id,
            "rfc822": self._build_rfc822_preview(queued),
        }
        now = now_utc().isoformat()
        with self.repository.transaction() as conn:
            self.repository.append_mutation(
                conn,
                mutation_id=str(uuid4()),
                account_id=account_id,
                provider_key=provider_key,
                target_kind="draft",
                target_id=queued.id,
                action_type="draft_send",
                payload_json=json.dumps(payload, sort_keys=True),
                state="ready_for_sync",
                created_at=now,
                updated_at=now,
            )
        return QueuedSendResult(
            draft_id=queued.id,
            source_thread_id=queued.source_thread_id,
        )

    @staticmethod
    def _build_rfc822_preview(draft: MessageDraft) -> str:
        """Build one minimal RFC 2822 preview string for later provider replay."""
        message = EmailMessage()
        if draft.to_addresses.strip():
            message["To"] = draft.to_addresses.strip()
        if draft.cc_addresses.strip():
            message["Cc"] = draft.cc_addresses.strip()
        if draft.bcc_addresses.strip():
            message["Bcc"] = draft.bcc_addresses.strip()
        message["Subject"] = draft.subject.strip()
        message.set_content(draft.body or "")
        return message.as_string()

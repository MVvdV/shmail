"""Read-model service for thread viewer message card data."""

from __future__ import annotations

from shmail.screens.message_draft import MessageDraftSeed
from shmail.services.db import DatabaseRepository, db


class ThreadViewerService:
    """Provide viewer-oriented thread message reads."""

    def __init__(self, repository: DatabaseRepository | None = None) -> None:
        self.repository = repository or db

    def list_thread_messages(self, thread_id: str) -> list[dict]:
        """Return ordered message and draft cards for one thread."""
        return self.repository.get_thread_messages(thread_id)

    def build_message_draft_seed(
        self, message_data: dict, action: str, current_account: str
    ) -> MessageDraftSeed:
        """Create one compose seed from thread message context."""
        subject = str(message_data.get("subject") or "")
        sender_address = str(message_data.get("sender_address") or "").strip().lower()
        recipient_to = self._split_addresses(message_data.get("recipient_to_addresses"))
        recipient_cc = self._split_addresses(message_data.get("recipient_cc_addresses"))
        current_account = current_account.strip().lower()

        body = str(message_data.get("body") or "")
        sender_text = str(
            message_data.get("sender") or sender_address or "Unknown sender"
        )
        timestamp = str(message_data.get("timestamp") or "")

        if action == "reply":
            to_recipients = self._unique_addresses([sender_address], current_account)
            return MessageDraftSeed(
                mode="reply",
                to=", ".join(to_recipients),
                subject=self._prefix_subject(subject, "Re:"),
                body=self._build_reply_body(sender_text, timestamp, body),
                source_message_id=str(message_data.get("id") or "") or None,
                source_thread_id=str(message_data.get("thread_id") or "") or None,
            )

        if action == "reply_all":
            to_seed = [*recipient_to]
            if sender_address and sender_address != current_account:
                to_seed.insert(0, sender_address)
            to_recipients = self._unique_addresses(to_seed, current_account)
            cc_recipients = self._unique_addresses(
                recipient_cc, current_account, excluded=to_recipients
            )
            return MessageDraftSeed(
                mode="reply_all",
                to=", ".join(to_recipients),
                cc=", ".join(cc_recipients),
                subject=self._prefix_subject(subject, "Re:"),
                body=self._build_reply_body(sender_text, timestamp, body),
                source_message_id=str(message_data.get("id") or "") or None,
                source_thread_id=str(message_data.get("thread_id") or "") or None,
            )

        return MessageDraftSeed(
            mode="forward",
            subject=self._prefix_subject(subject, "Fwd:"),
            body=self._build_forward_body(message_data, body),
            source_message_id=str(message_data.get("id") or "") or None,
            source_thread_id=str(message_data.get("thread_id") or "") or None,
        )

    @staticmethod
    def _split_addresses(value: object) -> list[str]:
        """Split comma-separated address fields into normalized addresses."""
        if not isinstance(value, str):
            return []
        return [
            address.strip().lower() for address in value.split(",") if address.strip()
        ]

    @staticmethod
    def _unique_addresses(
        addresses: list[str], current_account: str, excluded: list[str] | None = None
    ) -> list[str]:
        """De-duplicate addresses and exclude current account identity."""
        excluded_set = {
            address.strip().lower() for address in (excluded or []) if address.strip()
        }
        unique: list[str] = []
        for address in addresses:
            normalized = address.strip().lower()
            if (
                not normalized
                or normalized == current_account
                or normalized in excluded_set
            ):
                continue
            if normalized not in unique:
                unique.append(normalized)
        return unique

    @staticmethod
    def _prefix_subject(subject: str, prefix: str) -> str:
        """Apply one canonical reply or forward prefix to subject text."""
        raw = " ".join(subject.split())
        lower = raw.lower()
        if lower.startswith(f"{prefix.lower()} ") or lower == prefix.lower():
            return raw
        if not raw:
            return prefix
        return f"{prefix} {raw}"

    @staticmethod
    def _build_reply_body(sender: str, timestamp: str, body: str) -> str:
        """Build one reply body with quoted original content."""
        heading = (
            f"On {timestamp}, {sender} wrote:" if timestamp else f"{sender} wrote:"
        )
        quoted = [f"> {line}" if line else ">" for line in body.splitlines()]
        quote_block = "\n".join(quoted)
        return f"\n\n{heading}\n{quote_block}".rstrip()

    @staticmethod
    def _build_forward_body(message_data: dict, body: str) -> str:
        """Build one forward body with original message metadata block."""
        sender = str(message_data.get("sender") or "")
        to_line = str(message_data.get("recipient_to") or "")
        subject = str(message_data.get("subject") or "")
        timestamp = str(message_data.get("timestamp") or "")
        header_lines = [
            "---",
            "Forwarded message",
            f"From: {sender}" if sender else "",
            f"Date: {timestamp}" if timestamp else "",
            f"Subject: {subject}" if subject else "",
            f"To: {to_line}" if to_line else "",
            "---",
        ]
        normalized_header = "\n".join(line for line in header_lines if line)
        return f"\n\n{normalized_header}\n\n{body}".rstrip()

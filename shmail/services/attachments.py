"""Attachment download helpers for metadata-backed message attachments."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from shmail.config import settings
from shmail.services.db import DatabaseRepository, db
from shmail.services.parser import MessageParser


@dataclass
class AttachmentDownloadResult:
    """Summarize one completed attachment download."""

    attachment_id: str
    path: Path


class AttachmentService:
    """Download persisted message attachments directly to the configured folder."""

    def __init__(self, repository: DatabaseRepository | None = None) -> None:
        self.repository = repository or db

    def download_attachment(
        self,
        *,
        message_id: str,
        attachment_id: str,
        gmail_service,
    ) -> AttachmentDownloadResult:
        """Download one attachment by persisted metadata identifier."""
        attachment = self.repository.get_message_attachment(message_id, attachment_id)
        if attachment is None:
            raise ValueError("Attachment not found.")
        if gmail_service is None:
            raise ValueError("Gmail is not connected.")
        message_data = gmail_service.get_message(message_id)
        raw_b64 = str(message_data.get("raw") or "").strip()
        if not raw_b64:
            raise ValueError("Attachment source payload is unavailable.")
        payload, resolved_name = MessageParser.decode_attachment_payload(
            raw_b64, int(attachment.get("attachment_index") or 0)
        )
        target = self._allocate_download_path(
            str(attachment.get("filename") or resolved_name or attachment_id)
        )
        target.write_bytes(payload)
        return AttachmentDownloadResult(attachment_id=attachment_id, path=target)

    def download_all_attachments(
        self, *, message_id: str, gmail_service
    ) -> list[AttachmentDownloadResult]:
        """Download all persisted attachments for one message."""
        attachments = self.repository.list_message_attachments(message_id)
        return [
            self.download_attachment(
                message_id=message_id,
                attachment_id=str(attachment.get("id") or ""),
                gmail_service=gmail_service,
            )
            for attachment in attachments
        ]

    def resolve_download_directory(self) -> Path:
        """Return the configured attachment download directory."""
        raw = str(settings.attachments.download_directory or "").strip()
        target = Path(raw).expanduser() if raw else Path.home() / "Downloads"
        target.mkdir(parents=True, exist_ok=True)
        return target.resolve()

    def _allocate_download_path(self, filename: str) -> Path:
        """Return a collision-safe path inside the configured download directory."""
        directory = self.resolve_download_directory()
        safe_name = self._sanitize_filename(filename)
        candidate = directory / safe_name
        stem = candidate.stem or "attachment"
        suffix = candidate.suffix
        counter = 1
        while candidate.exists():
            candidate = directory / f"{stem}-{counter}{suffix}"
            counter += 1
        return candidate

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Return a filesystem-safe attachment filename."""
        candidate = re.sub(r"[\\/:*?\"<>|]+", "_", filename.strip())
        candidate = candidate.replace("..", ".")
        return candidate or "attachment"

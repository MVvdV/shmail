import base64
import email.utils
import html
import logging
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import getaddresses
from typing import Any, Dict, List, Optional

from shmail.models import Contact, Email, Label, ParsedMessage

logger = logging.getLogger(__name__)


class MessageParser:
    """Unified parser that transforms raw Gmail API responses into domain models."""

    @staticmethod
    def parse_gmail_response(
        message_id: str,
        thread_id: str,
        message_data: Dict[str, Any],
        label_ids: List[str],
    ) -> ParsedMessage:
        """Converts raw Gmail API response into a ParsedMessage model."""
        raw_b64 = message_data["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64)
        mime_msg = message_from_bytes(raw_bytes)

        subject = mime_msg.get("subject", "(No Subject)")
        if isinstance(subject, str):
            subject = " ".join(subject.split())

        sender = mime_msg.get("from", "(Unknown Sender)")
        sender_address = None
        if isinstance(sender, str):
            display_name, sender_address = email.utils.parseaddr(sender)
            # If the parser found a display name, use it as the clean sender string.
            # Otherwise, use the normalized raw string.
            sender = display_name if display_name else " ".join(sender.split())

        recipient_to = mime_msg.get("To")
        recipient_to_addresses = None
        if isinstance(recipient_to, str):
            addrs = email.utils.getaddresses([recipient_to])
            recipient_to_addresses = ",".join(
                addr[1].lower() for _, addr in enumerate(addrs) if addr[1].strip()
            )
            recipient_to = " ".join(recipient_to.split())

        recipient_cc = mime_msg.get("Cc")
        recipient_cc_addresses = None
        if isinstance(recipient_cc, str):
            addrs = email.utils.getaddresses([recipient_cc])
            recipient_cc_addresses = ",".join(
                addr[1].lower() for _, addr in enumerate(addrs) if addr[1].strip()
            )
            recipient_cc = " ".join(recipient_cc.split())

        recipient_bcc = mime_msg.get("Bcc")
        recipient_bcc_addresses = None
        if isinstance(recipient_bcc, str):
            addrs = email.utils.getaddresses([recipient_bcc])
            recipient_bcc_addresses = ",".join(
                addr[1].lower() for _, addr in enumerate(addrs) if addr[1].strip()
            )
            recipient_bcc = " ".join(recipient_bcc.split())

        snippet = message_data.get("snippet", "")
        if isinstance(snippet, str):
            snippet = html.unescape(" ".join(snippet.split()))

        date_str = mime_msg.get("date")
        timestamp: datetime
        dt: Optional[datetime] = None
        try:
            if date_str:
                dt = email.utils.parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            dt = None

        if dt:
            if dt.tzinfo is None:
                timestamp = dt.replace(tzinfo=timezone.utc)
            else:
                timestamp = dt.astimezone(timezone.utc)
        else:
            ms_val = int(message_data.get("internalDate", 0))
            timestamp = datetime.fromtimestamp(ms_val / 1000.0, tz=timezone.utc)

        body = MessageParser._extract_body(mime_msg)
        is_read = "UNREAD" not in label_ids
        has_attachments = MessageParser._check_attachments(mime_msg)
        labels = MessageParser._extract_labels(label_ids)
        contacts = MessageParser._extract_contacts(mime_msg, timestamp)

        return ParsedMessage(
            email=Email(
                id=message_id,
                thread_id=thread_id,
                subject=subject,
                sender=sender,
                sender_address=sender_address,
                recipient_to=recipient_to,
                recipient_to_addresses=recipient_to_addresses,
                recipient_cc=recipient_cc,
                recipient_cc_addresses=recipient_cc_addresses,
                recipient_bcc=recipient_bcc,
                recipient_bcc_addresses=recipient_bcc_addresses,
                snippet=snippet,
                body=body,
                timestamp=timestamp,
                is_read=is_read,
                has_attachments=has_attachments,
                labels=labels,
            ),
            contacts=contacts,
        )

    @staticmethod
    def _extract_body(mime_msg) -> str:
        """Extracts the plain text body from MIME parts."""
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
        return body

    @staticmethod
    def _extract_contacts(mime_msg, timestamp: datetime) -> List[Contact]:
        """Extracts contact information from message headers."""
        raw_contacts = []

        headers = ["From", "To", "Cc", "Bcc"]
        for header in headers:
            vals = mime_msg.get_all(header, [])
            if vals:
                raw_contacts.extend(getaddresses(vals))

        contacts = []
        for name, addr in raw_contacts:
            if addr.strip():
                contacts.append(
                    Contact(
                        email=addr.strip().lower(),
                        name=name.strip(),
                        timestamp=timestamp,
                    )
                )
        return contacts

    @staticmethod
    def _extract_labels(label_ids: List[str]) -> List[Label]:
        """Maps Gmail label IDs to Label models."""
        return [Label(id=label_id, name="", type="") for label_id in label_ids]

    @staticmethod
    def _check_attachments(mime_msg) -> bool:
        """Checks if the message contains file attachments."""
        return (
            any(part.get_filename() for part in mime_msg.walk())
            if mime_msg.is_multipart()
            else False
        )

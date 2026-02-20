import base64
import email.utils
import logging
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import getaddresses
from typing import Any, Dict, List, Optional

from shmail.models import Contact, Email, Label, ParsedMessage

# Module-level logger following the project standard
logger = logging.getLogger(__name__)


class MessageParser:
    # Unified parser that transforms raw Gmail API responses into domain models.
    # Walking the MIME tree once to extract Email, Contacts, and Attachments.

    @staticmethod
    def parse_gmail_response(
        message_id: str,
        thread_id: str,
        message_data: Dict[str, Any],
        label_ids: List[str],
    ) -> ParsedMessage:
        # Converts raw Gmail API response into our Email model.
        raw_b64 = message_data["raw"]
        raw_bytes = base64.urlsafe_b64decode(raw_b64)
        mime_msg = message_from_bytes(raw_bytes)

        subject = mime_msg.get("subject", "(No Subject)")
        sender = mime_msg.get("from", "(Unknown Sender)")
        recipient_to = mime_msg.get("To")
        recipient_cc = mime_msg.get("Cc")
        recipient_bcc = mime_msg.get("Bcc")
        snippet = message_data.get("snippet", "")

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
            # Fallback to Gmail's internal timestamp
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
                recipient_to=recipient_to,
                recipient_cc=recipient_cc,
                recipient_bcc=recipient_bcc,
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
        # Extract text/plain body from MIME parts.
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
        # Extract list of Contact objects from headers.
        raw_contacts = []

        from_header = mime_msg.get_all("From", [])
        if from_header:
            raw_contacts.extend(getaddresses(from_header))

        to_header = mime_msg.get_all("To", [])
        if to_header:
            raw_contacts.extend(getaddresses(to_header))

        cc_header = mime_msg.get_all("Cc", [])
        if cc_header:
            raw_contacts.extend(getaddresses(cc_header))

        bcc_header = mime_msg.get_all("Bcc", [])
        if bcc_header:
            raw_contacts.extend(getaddresses(bcc_header))

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
        # Maps Gmail label IDs to our Label model.
        return [Label(id=label_id, name="", type="") for label_id in label_ids]

    @staticmethod
    def _check_attachments(mime_msg) -> bool:
        # Determines if the message has attachments by walking the MIME parts.
        return (
            any(part.get_filename() for part in mime_msg.walk())
            if mime_msg.is_multipart()
            else False
        )

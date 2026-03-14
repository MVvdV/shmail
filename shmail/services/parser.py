import base64
import email.utils
import html
import logging
import re
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import getaddresses
from typing import Any, Dict, List, Optional

import html2text

from shmail.models import Contact, Message, Label, ParsedMessage

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
        except ValueError, TypeError:
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
            message=Message(
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
        """Extracts and converts the best available MIME part to Markdown."""
        html_part = None
        text_part = None

        if mime_msg.is_multipart():
            for part in mime_msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/html" and html_part is None:
                    html_part = part
                elif ctype == "text/plain" and text_part is None:
                    text_part = part
        else:
            ctype = mime_msg.get_content_type()
            if ctype == "text/html":
                html_part = mime_msg
            elif ctype == "text/plain":
                text_part = mime_msg

        if html_part:
            payload = html_part.get_payload(decode=True)
            if payload:
                return MessageParser._to_markdown(
                    payload.decode(errors="replace"), is_html=True
                )

        if text_part:
            payload = text_part.get_payload(decode=True)
            if payload:
                return MessageParser._to_markdown(
                    payload.decode(errors="replace"), is_html=False
                )

        return ""

    @staticmethod
    def _to_markdown(content: str, is_html: bool) -> str:
        """Modular converter that transforms HTML or plain text into clean Markdown."""
        if is_html:
            h2t = html2text.HTML2Text()
            h2t.body_width = 0
            h2t.ignore_links = False
            h2t.ignore_emphasis = False
            h2t.ignore_images = True
            h2t.protect_links = True
            h2t.unicode_snob = True
            h2t.wrap_links = False
            h2t.inline_links = True
            text = h2t.handle(content)
            return re.sub(r"\n{3,}", "\n\n", text).strip()

        url_pattern = r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"

        def linkify(match):
            val = match.group(0)
            if "@" in val and "." in val:
                return f"[{val}](mailto:{val})"
            prefix = "https://" if val.startswith("www.") else ""
            return f"[{val}]({prefix}{val})"

        return re.sub(url_pattern, linkify, content)

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

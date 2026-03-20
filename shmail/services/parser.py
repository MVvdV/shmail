"""Message parsing and body/link normalization for viewer consumption."""

import base64
import email.utils
import html
import json
import logging
import re
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

import html2text

from shmail.models import Contact, Label, Message, ParsedMessage, ParseMetadata
from shmail.services.link_policy import is_executable_href

logger = logging.getLogger(__name__)


class _HTMLLinkExtractor(HTMLParser):
    """Extract anchor label/href pairs from HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = (dict(attrs).get("href") or "").strip()
        self._active_href = href or None
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href is None:
            return
        self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._active_href is None:
            return
        label = " ".join("".join(self._active_text).replace("\u00a0", " ").split())
        self.links.append({"label": label, "href": self._active_href})
        self._active_href = None
        self._active_text = []


class MessageParser:
    """Transform Gmail payloads into app message models."""

    LINK_PATTERN = re.compile(
        r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
    )
    NOISY_PIPE_ROW_PATTERN = re.compile(r"^\s*\|(?:\s*\|\s*)+\s*$")
    TABLE_SEPARATOR_PATTERN = re.compile(
        r"^\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$"
    )

    @staticmethod
    def parse_gmail_response(
        message_id: str,
        thread_id: str,
        message_data: Dict[str, Any],
        label_ids: List[str],
    ) -> ParsedMessage:
        """Convert a raw Gmail API response into a ParsedMessage."""
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

        recipient_to, recipient_to_addresses = MessageParser._extract_header_addresses(
            mime_msg.get("To")
        )
        recipient_cc, recipient_cc_addresses = MessageParser._extract_header_addresses(
            mime_msg.get("Cc")
        )
        recipient_bcc, recipient_bcc_addresses = (
            MessageParser._extract_header_addresses(mime_msg.get("Bcc"))
        )

        snippet = message_data.get("snippet", "")
        if isinstance(snippet, str):
            snippet = html.unescape(" ".join(snippet.split()))

        date_str = mime_msg.get("date")
        dt: Optional[datetime] = None
        try:
            if date_str:
                dt = email.utils.parsedate_to_datetime(date_str)
        except ValueError, TypeError:
            dt = None

        if dt:
            timestamp = (
                dt.replace(tzinfo=timezone.utc)
                if dt.tzinfo is None
                else dt.astimezone(timezone.utc)
            )
        else:
            try:
                ms_val = int(message_data.get("internalDate", 0))
            except TypeError, ValueError:
                logger.warning(
                    "Invalid internalDate for message %s; falling back to epoch.",
                    message_id,
                )
                ms_val = 0
            timestamp = datetime.fromtimestamp(ms_val / 1000.0, tz=timezone.utc)

        body_text, body_links, parse_metadata = MessageParser._extract_body(mime_msg)
        is_read = "UNREAD" not in label_ids
        has_attachments = MessageParser._check_attachments(mime_msg)
        labels = MessageParser._extract_labels(label_ids)
        contacts = MessageParser._extract_contacts(mime_msg, timestamp)

        logger.debug(
            "Parsed body metadata for message %s: source=%s ctype=%s charset=%s links=%d warnings=%d",
            message_id,
            parse_metadata.body_source,
            parse_metadata.selected_content_type,
            parse_metadata.selected_charset,
            parse_metadata.link_count,
            len(parse_metadata.conversion_warnings),
        )

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
                body=body_text,
                body_links=json.dumps(body_links),
                body_source=parse_metadata.body_source,
                body_content_type=parse_metadata.selected_content_type,
                body_charset=parse_metadata.selected_charset,
                body_link_count=parse_metadata.link_count,
                body_conversion_warnings=json.dumps(parse_metadata.conversion_warnings),
                timestamp=timestamp,
                is_read=is_read,
                has_attachments=has_attachments,
                labels=labels,
            ),
            contacts=contacts,
            parse_metadata=parse_metadata,
        )

    @staticmethod
    def _extract_body(mime_msg) -> tuple[str, list[dict], ParseMetadata]:
        """Extract body text and return markdown plus link index metadata."""
        html_part = None
        text_part = None

        parts = mime_msg.walk() if mime_msg.is_multipart() else [mime_msg]
        for part in parts:
            if part.is_multipart() or part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type().lower()
            if ctype == "text/html" and html_part is None:
                html_part = part
            elif ctype == "text/plain" and text_part is None:
                text_part = part

        selected_part = html_part or text_part
        if selected_part is None:
            metadata = ParseMetadata(
                body_source="none",
                conversion_warnings=[
                    "No eligible text/html or text/plain MIME part found."
                ],
            )
            return "", [], metadata

        decoded_text, selected_charset, warnings = MessageParser._decode_part(
            selected_part
        )
        selected_content_type = selected_part.get_content_type().lower()
        is_html = selected_content_type == "text/html"

        if is_html:
            body_text = MessageParser._to_markdown(decoded_text, is_html=True)
            body_links = MessageParser._extract_links_from_html(decoded_text)
            if not body_text.strip() and text_part is not None:
                warnings.append(
                    "HTML body produced no readable text; using plain-text fallback."
                )
                plain_text, plain_charset, plain_warnings = MessageParser._decode_part(
                    text_part
                )
                plain_normalized = MessageParser._normalize_plain_text(plain_text)
                body_text = MessageParser._to_markdown(plain_normalized, is_html=False)
                body_links = MessageParser._extract_links_from_plain(plain_normalized)
                warnings.extend(plain_warnings)
                is_html = False
                selected_content_type = "text/plain"
                selected_charset = plain_charset
        else:
            normalized = MessageParser._normalize_plain_text(decoded_text)
            body_text = MessageParser._to_markdown(normalized, is_html=False)
            body_links = MessageParser._extract_links_from_plain(normalized)

        body_links = MessageParser._dedupe_and_rank_links(body_links)

        metadata = ParseMetadata(
            body_source="html" if is_html else "plain",
            selected_content_type=selected_content_type,
            selected_charset=selected_charset,
            link_count=len(body_links),
            conversion_warnings=warnings,
        )
        return body_text, body_links, metadata

    @staticmethod
    def _decode_part(part) -> tuple[str, Optional[str], List[str]]:
        """Decode MIME payload using charset fallbacks."""
        warnings: List[str] = []
        payload = part.get_payload(decode=True)
        declared_charset = part.get_content_charset()

        if payload is None:
            warnings.append("MIME part payload was empty.")
            return "", declared_charset, warnings

        for charset in [declared_charset, "utf-8", "latin-1"]:
            if not charset:
                continue
            try:
                return payload.decode(charset), charset, warnings
            except LookupError, UnicodeDecodeError:
                continue

        warnings.append(
            "Unable to decode payload with strict charset fallbacks; replacement used."
        )
        return payload.decode("utf-8", errors="replace"), declared_charset, warnings

    @staticmethod
    def _extract_header_addresses(
        raw_header: str | None,
    ) -> tuple[str | None, str | None]:
        """Normalize recipient headers and extract canonical email lists."""
        if not isinstance(raw_header, str):
            return raw_header, None
        addresses = email.utils.getaddresses([raw_header])
        canonical = ",".join(addr[1].lower() for addr in addresses if addr[1].strip())
        return " ".join(raw_header.split()), canonical or None

    @staticmethod
    def _normalize_plain_text(content: str) -> str:
        """Strip noisy pseudo-table artifacts from plain-text content."""
        lines = content.replace("\r\n", "\n").split("\n")
        output: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if MessageParser.NOISY_PIPE_ROW_PATTERN.match(stripped) and i + 1 < len(
                lines
            ):
                if MessageParser.TABLE_SEPARATOR_PATTERN.match(lines[i + 1].strip()):
                    i += 2
                    continue
            if (
                MessageParser.TABLE_SEPARATOR_PATTERN.match(stripped)
                and "|" in stripped
                and not any(ch.isalnum() for ch in stripped)
            ):
                i += 1
                continue
            output.append(line)
            i += 1
        return "\n".join(output)

    @staticmethod
    def _to_markdown(content: str, is_html: bool) -> str:
        """Convert HTML or plain text content to markdown-like display text."""
        if is_html:
            converter = html2text.HTML2Text()
            converter.ignore_images = True
            converter.ignore_emphasis = False
            converter.ignore_links = False
            converter.single_line_break = False
            converter.body_width = 0
            converter.inline_links = True
            converter.wrap_links = False
            rendered = converter.handle(content)
            return re.sub(r"\n{3,}", "\n\n", rendered).strip()

        def linkify(match: re.Match[str]) -> str:
            token = match.group(0)
            trimmed = token.rstrip('.,;:!?)"]}')
            trailing = token[len(trimmed) :]
            if not trimmed:
                return token
            if "@" in trimmed and "." in trimmed:
                return f"[{trimmed}](mailto:{trimmed}){trailing}"
            href = f"https://{trimmed}" if trimmed.startswith("www.") else trimmed
            return f"[{trimmed}]({href}){trailing}"

        return re.sub(MessageParser.LINK_PATTERN, linkify, content)

    @staticmethod
    def _extract_links_from_html(content: str) -> list[dict]:
        """Extract link candidates from HTML anchor tags."""
        extractor = _HTMLLinkExtractor()
        extractor.feed(content)
        extractor.close()

        links: list[dict] = []
        for link in extractor.links:
            href = str(link.get("href") or "").strip()
            if not href:
                continue
            label = str(link.get("label") or "").strip()
            if not label:
                label = (
                    href.replace("mailto:", "", 1)
                    if href.startswith("mailto:")
                    else href
                )
            links.append(
                {
                    "label": label,
                    "href": href,
                    "executable": is_executable_href(href),
                }
            )
        return links

    @staticmethod
    def _extract_links_from_plain(content: str) -> list[dict]:
        """Extract link candidates from plain text."""
        links: list[dict] = []
        for match in MessageParser.LINK_PATTERN.finditer(content):
            raw = match.group(0)
            trimmed = raw.rstrip('.,;:!?)"]}')
            if not trimmed:
                continue
            href = (
                f"mailto:{trimmed}"
                if "@" in trimmed and "." in trimmed
                else (f"https://{trimmed}" if trimmed.startswith("www.") else trimmed)
            )
            links.append(
                {
                    "label": trimmed,
                    "href": href,
                    "executable": is_executable_href(href),
                }
            )
        return links

    @staticmethod
    def _dedupe_and_rank_links(links: list[dict]) -> list[dict]:
        """Deduplicate links and prefer CTA labels over raw URL labels."""
        deduped: list[dict] = []
        by_href: dict[str, dict] = {}
        by_label: dict[str, dict] = {}

        for link in links:
            href = str(link.get("href") or "").strip()
            label = " ".join(str(link.get("label") or "").split())
            if not href or not label:
                continue

            label_key = label.lower()
            raw_label = label_key == href.lower() or label_key.startswith("http")

            existing_href = by_href.get(href)
            if existing_href is None:
                payload = {
                    "label": label,
                    "href": href,
                    "executable": bool(link.get("executable", False)),
                }
                by_href[href] = payload
                deduped.append(payload)
            else:
                existing_raw = existing_href[
                    "label"
                ].lower() == href.lower() or existing_href["label"].lower().startswith(
                    "http"
                )
                if existing_raw and not raw_label:
                    existing_href["label"] = label
                    existing_href["executable"] = bool(link.get("executable", False))

            if not raw_label and label_key in by_label:
                previous = by_label[label_key]
                if previous["href"] != href:
                    if previous in deduped:
                        deduped.remove(previous)
                    by_href.pop(previous["href"], None)
            if not raw_label:
                by_label[label_key] = by_href[href]

        return deduped

    @staticmethod
    def _extract_contacts(mime_msg, timestamp: datetime) -> List[Contact]:
        """Extract contact entries from message headers."""
        raw_contacts = []
        for header in ["From", "To", "Cc", "Bcc"]:
            vals = mime_msg.get_all(header, [])
            if vals:
                raw_contacts.extend(getaddresses(vals))

        contacts: list[Contact] = []
        seen: dict[str, Contact] = {}
        for name, addr in raw_contacts:
            email = addr.strip().lower()
            if not email:
                continue
            parsed_name = name.strip()
            existing = seen.get(email)
            if existing is None:
                contact = Contact(email=email, name=parsed_name, timestamp=timestamp)
                seen[email] = contact
                contacts.append(contact)
            elif not existing.name and parsed_name:
                existing.name = parsed_name
        return contacts

    @staticmethod
    def _extract_labels(label_ids: List[str]) -> List[Label]:
        """Map Gmail label IDs to Label models."""
        return [Label(id=label_id, name="", type="") for label_id in label_ids]

    @staticmethod
    def _check_attachments(mime_msg) -> bool:
        """Return whether a message contains attachments."""
        return (
            any(part.get_filename() for part in mime_msg.walk())
            if mime_msg.is_multipart()
            else False
        )

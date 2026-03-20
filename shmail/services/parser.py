"""Message parsing and body/link normalization for viewer consumption."""

import base64
import email.utils
import html
import json
import logging
import textwrap
from datetime import datetime, timezone
from email import message_from_bytes
from email.utils import getaddresses
from typing import Any, Dict, List, Optional

from inscriptis import get_text
from inscriptis.model.config import ParserConfig
from markdown_it import MarkdownIt
from markdown_it.token import Token

from shmail.models import Contact, Label, Message, ParsedMessage, ParseMetadata
from shmail.services.link_policy import is_executable_href

logger = logging.getLogger(__name__)


class MessageParser:
    """Transform Gmail payloads into app message models."""

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
            body_links = MessageParser._extract_links_from_markdown(body_text)
            if not body_text.strip() and text_part is not None:
                warnings.append(
                    "HTML body produced no readable text; using plain-text fallback."
                )
                plain_text, plain_charset, plain_warnings = MessageParser._decode_part(
                    text_part
                )
                body_text = MessageParser._to_markdown(plain_text, is_html=False)
                body_links = MessageParser._extract_links_from_markdown(body_text)
                warnings.extend(plain_warnings)
                is_html = False
                selected_content_type = "text/plain"
                selected_charset = plain_charset
        else:
            body_text = MessageParser._to_markdown(decoded_text, is_html=False)
            body_links = MessageParser._extract_links_from_markdown(body_text)

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
    def _cleanup_markdown_artifacts(content: str, is_html: bool) -> str:
        """Normalize output for stable markdown rendering."""
        cleaned = content.replace("\r\n", "\n").replace("\u200b", "")
        cleaned = textwrap.dedent(cleaned)
        output: list[str] = []
        previous_blank = False

        for line in cleaned.split("\n"):
            normalized_line = line.rstrip()
            if (
                is_html
                and (len(normalized_line) - len(normalized_line.lstrip(" "))) >= 4
            ):
                normalized_line = normalized_line.lstrip()

            is_blank = not normalized_line.strip()
            if is_blank and previous_blank:
                continue
            output.append(normalized_line)
            previous_blank = is_blank

        return "\n".join(output).strip()

    @staticmethod
    def _to_markdown(content: str, is_html: bool) -> str:
        """Convert HTML or plain text content to markdown-like display text."""
        if is_html:
            rendered = get_text(
                content,
                ParserConfig(
                    display_links=True,
                    display_images=True,
                    deduplicate_captions=True,
                ),
            )
            return MessageParser._cleanup_markdown_artifacts(rendered, is_html=True)
        return MessageParser._cleanup_markdown_artifacts(content, is_html=False)

    @staticmethod
    def _extract_links_from_markdown(content: str) -> list[dict]:
        """Extract link candidates from rendered markdown-like body text."""
        links: list[dict] = []
        parser = MessageParser.new_markdown_parser()
        for token in parser.parse(content):
            children = token.children or []
            line_start = token.map[0] if token.map else None
            i = 0
            while i < len(children):
                child = children[i]
                if child.type != "link_open":
                    i += 1
                    continue

                raw_href = child.attrGet("href")
                href = " ".join(str(raw_href or "").split())
                label_parts: list[str] = []
                has_image = False
                i += 1
                while i < len(children) and children[i].type != "link_close":
                    if children[i].type == "image":
                        has_image = True
                    if children[i].content:
                        label_parts.append(children[i].content)
                    i += 1

                if href:
                    label = " ".join(
                        " ".join(label_parts).replace("\u00a0", " ").split()
                    )
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
                            "kind": MessageParser._classify_link_kind(href, has_image),
                            "line_start": line_start,
                        }
                    )
                i += 1

        return links

    @staticmethod
    def _classify_link_kind(href: str, has_image: bool) -> str:
        """Classify links for lightweight interaction styling hints."""
        if has_image:
            return "image_link"
        lower = href.lower()
        if lower.startswith("mailto:"):
            return "mailto"
        if href == "#":
            return "placeholder"
        return "web"

    @staticmethod
    def new_markdown_parser(
        active_link_index: int | None = None,
        active_marker_prefix: str = "↗ ",
        active_marker_suffix: str = "",
    ) -> MarkdownIt:
        """Return the shared markdown parser used by viewer and extraction."""
        parser = MarkdownIt("gfm-like")
        parser.validateLink = lambda url: True

        if (
            active_link_index is not None
            and active_link_index >= 0
            and isinstance(active_marker_prefix, str)
            and isinstance(active_marker_suffix, str)
            and (active_marker_prefix or active_marker_suffix)
        ):

            def inject_active_link_marker(state) -> None:
                """Insert marker tokens around the selected inline link text."""
                link_count = 0
                for token in state.tokens:
                    children = token.children
                    if not children:
                        continue

                    updated_children = []
                    active_link_open = False
                    for child in children:
                        if child.type == "link_open":
                            if link_count == active_link_index:
                                active_link_open = True
                            link_count += 1
                            updated_children.append(child)
                            if active_link_open and active_marker_prefix:
                                marker_prefix = Token("text", "", 0)
                                marker_prefix.content = active_marker_prefix
                                updated_children.append(marker_prefix)
                            continue

                        if child.type == "link_close" and active_link_open:
                            if active_marker_suffix:
                                marker_suffix = Token("text", "", 0)
                                marker_suffix.content = active_marker_suffix
                                updated_children.append(marker_suffix)
                            active_link_open = False
                            updated_children.append(child)
                            continue

                        updated_children.append(child)
                    token.children = updated_children

            parser.core.ruler.push(
                "shmail_active_link_marker", inject_active_link_marker
            )

        return parser

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

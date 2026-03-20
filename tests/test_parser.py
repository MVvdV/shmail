import base64
import json
from datetime import timezone

import pytest

from shmail.services.parser import MessageParser


@pytest.fixture
def raw_gmail_message():
    """
    A sample raw email structure as returned by the Gmail API.
    """
    mime_content = (
        "From: Alice <alice@example.com>\r\n"
        "To: Bob <bob@example.com>, Charlie <charlie@example.com>\r\n"
        "Cc: Dana <dana@example.com>\r\n"
        "Subject: Hello World\r\n"
        "Date: Mon, 16 Feb 2026 10:00:00 +0000\r\n"
        'Content-Type: multipart/mixed; boundary="boundary"\r\n'
        "\r\n"
        "--boundary\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "\r\n"
        "This is the body.\r\n"
        "--boundary\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="test.pdf"\r\n'
        "\r\n"
        "dummy-pdf-content\r\n"
        "--boundary--"
    )

    raw_b64 = base64.urlsafe_b64encode(mime_content.encode()).decode()

    return {
        "id": "msg123",
        "threadId": "thread123",
        "raw": raw_b64,
        "snippet": "This is the body.",
        "internalDate": "1739699800000",
    }


def test_parse_gmail_response_basic(raw_gmail_message):
    """
    Verify the high-level parse_gmail_response result.
    """
    result = MessageParser.parse_gmail_response(
        message_id="msg123",
        thread_id="thread123",
        message_data=raw_gmail_message,
        label_ids=["INBOX", "UNREAD"],
    )
    message = result.message
    assert message.id == "msg123"
    assert message.thread_id == "thread123"
    assert message.subject == "Hello World"
    assert message.sender == "Alice"
    assert message.sender_address == "alice@example.com"
    assert (
        message.recipient_to == "Bob <bob@example.com>, Charlie <charlie@example.com>"
    )
    assert message.recipient_cc == "Dana <dana@example.com>"
    assert message.body == "This is the body."
    assert message.body_links is not None
    assert message.body_links == "[]"
    assert message.body_source == "plain"
    assert message.body_content_type == "text/plain"
    assert message.body_charset == "utf-8"
    assert message.body_link_count == 0
    assert message.body_conversion_warnings == "[]"
    assert message.is_read is False
    assert message.has_attachments is True
    assert len(message.labels) == 2
    assert message.labels[0].id == "INBOX"
    assert result.parse_metadata is not None
    assert result.parse_metadata.body_source == "plain"


def test_extract_contacts_logic(raw_gmail_message):
    """
    Verify that all unique contacts are extracted.
    """
    result = MessageParser.parse_gmail_response(
        message_id="msg123",
        thread_id="thread123",
        message_data=raw_gmail_message,
        label_ids=["INBOX", "UNREAD"],
    )
    assert len(result.contacts) == 4

    contact_emails = [c.email for c in result.contacts]
    assert "alice@example.com" in contact_emails
    assert "bob@example.com" in contact_emails
    assert "charlie@example.com" in contact_emails
    assert "dana@example.com" in contact_emails

    alice = next(c for c in result.contacts if c.email == "alice@example.com")
    assert alice.name == "Alice"
    assert alice.timestamp.tzinfo == timezone.utc


def test_timestamp_normalization():
    """
    Verify that offset-aware and naive dates are handled correctly.
    """
    data = {
        "raw": base64.urlsafe_b64encode(
            b"Date: Mon, 16 Feb 2026 10:00:00 -0500\r\n\r\n"
        ).decode(),
        "internalDate": "0",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.hour == 15
    assert result.message.timestamp.tzinfo == timezone.utc

    data = {
        "raw": base64.urlsafe_b64encode(b"Date: 16 Feb 2026 10:00:00\r\n\r\n").decode(),
        "internalDate": "0",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.hour == 10
    assert result.message.timestamp.tzinfo == timezone.utc

    data = {
        "raw": base64.urlsafe_b64encode(b"Date: Invalid Date\r\n\r\n").decode(),
        "internalDate": "1739700000000",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.hour == 10
    assert result.message.timestamp.tzinfo == timezone.utc


def test_plain_text_linkify_trailing_punctuation():
    """Ensure plain text linkification excludes trailing punctuation."""
    source = "Open https://example.com, mail admin@example.com."
    links = MessageParser._extract_links_from_plain(source)
    assert links[0]["label"] == "https://example.com"
    assert links[0]["href"] == "https://example.com"
    assert links[1]["label"] == "admin@example.com"
    assert links[1]["href"] == "mailto:admin@example.com"


def test_extract_body_prefers_html_when_available():
    """Ensure HTML body is preferred over plain text in multipart content."""
    mime_content = (
        'Content-Type: multipart/alternative; boundary="b"\r\n'
        "\r\n"
        "--b\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "\r\n"
        "Plain body\r\n"
        "--b\r\n"
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        "<p>HTML <a href='https://example.com'>link</a></p>\r\n"
        "--b--"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.body_source == "html"
    assert result.message.body_content_type == "text/html"
    assert result.message.body_link_count >= 1
    assert result.message.body is not None
    assert "[link](https://example.com)" in result.message.body
    assert result.message.body_links is not None


def test_html_disallowed_link_scheme_remains_visible_but_non_executable():
    """Ensure non-allowlisted hrefs remain visible but are flagged non-executable."""
    mime_content = (
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        "<p>Click <a href='javascript:alert(1)'>here</a></p>"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.body_links is not None
    links = json.loads(result.message.body_links)
    assert links
    assert links[0]["href"] == "javascript:alert(1)"
    assert links[0]["executable"] is False


def test_invalid_internal_date_falls_back_without_crash():
    """Ensure malformed internalDate does not crash parsing."""
    data = {
        "raw": base64.urlsafe_b64encode(b"Date: Invalid Date\r\n\r\n").decode(),
        "internalDate": "not-a-number",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.tzinfo == timezone.utc


def test_extract_contacts_deduplicates_addresses_across_headers():
    """Ensure duplicate addresses are emitted only once."""
    mime_content = (
        "From: Alice <alice@example.com>\r\n"
        "To: Alice <alice@example.com>, Bob <bob@example.com>\r\n"
        "Cc: bob@example.com\r\n"
        "Date: Mon, 16 Feb 2026 10:00:00 +0000\r\n"
        "\r\n"
        "Body"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    emails = sorted(contact.email for contact in result.contacts)
    assert emails == ["alice@example.com", "bob@example.com"]


def test_html_uppercase_scheme_is_marked_executable():
    """Ensure allowlist checks are case-insensitive."""
    mime_content = (
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        "<p><a href='HTTPS://example.com'>Example</a></p>"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    links = json.loads(result.message.body_links or "[]")
    assert links
    assert links[0]["executable"] is True

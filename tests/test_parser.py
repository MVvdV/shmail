import base64
from datetime import datetime, timezone

import pytest

from shmail.models import Contact
from shmail.services.parser import MessageParser


@pytest.fixture
def raw_gmail_message():
    """
    A sample raw email structure as returned by the Gmail API.
    """
    # Simple multipart MIME message
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
    email = result.email
    assert email.id == "msg123"
    assert email.thread_id == "thread123"
    assert email.subject == "Hello World"
    assert email.sender == "Alice <alice@example.com>"
    assert email.recipient_to == "Bob <bob@example.com>, Charlie <charlie@example.com>"
    assert email.recipient_cc == "Dana <dana@example.com>"
    assert email.body == "This is the body."
    assert email.is_read is False  # UNREAD is in label_ids
    assert email.has_attachments is True
    assert len(email.labels) == 2
    assert email.labels[0].id == "INBOX"


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
    # Check that we have 4 contacts
    assert len(result.contacts) == 4

    # Check normalization and mapping
    emails = [c.email for c in result.contacts]
    assert "alice@example.com" in emails
    assert "bob@example.com" in emails
    assert "charlie@example.com" in emails
    assert "dana@example.com" in emails

    # Check a specific contact's name and aware timestamp
    alice = next(c for c in result.contacts if c.email == "alice@example.com")
    assert alice.name == "Alice"
    assert alice.timestamp.tzinfo == timezone.utc


def test_timestamp_normalization():
    """
    Verify that offset-aware and naive dates are handled correctly.
    """
    # 1. Aware date (EST -0500)
    data = {
        "raw": base64.urlsafe_b64encode(
            b"Date: Mon, 16 Feb 2026 10:00:00 -0500\r\n\r\n"
        ).decode(),
        "internalDate": "0",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    # 10:00 -0500 should be 15:00 UTC
    assert result.email.timestamp.hour == 15
    assert result.email.timestamp.tzinfo == timezone.utc

    # 2. Naive date (treated as UTC)
    data = {
        "raw": base64.urlsafe_b64encode(b"Date: 16 Feb 2026 10:00:00\r\n\r\n").decode(),
        "internalDate": "0",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.email.timestamp.hour == 10
    assert result.email.timestamp.tzinfo == timezone.utc

    # 3. Fallback to internalDate
    data = {
        "raw": base64.urlsafe_b64encode(b"Date: Invalid Date\r\n\r\n").decode(),
        "internalDate": "1739700000000",  # Feb 16 2026 10:00:00 UTC
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.email.timestamp.hour == 10
    assert result.email.timestamp.tzinfo == timezone.utc

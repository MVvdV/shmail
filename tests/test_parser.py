import base64
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
    assert message.is_read is False
    assert message.has_attachments is True
    assert len(message.labels) == 2
    assert message.labels[0].id == "INBOX"


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

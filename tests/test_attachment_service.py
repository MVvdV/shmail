import base64
from datetime import datetime

import pytest

from shmail.models import Attachment, Message
from shmail.services.attachments import AttachmentService
from shmail.services.db import DatabaseRepository
from shmail.services.thread_viewer import ThreadViewerService
from shmail.config import settings


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "attachment_service.db"
    repository = DatabaseRepository(db_path=db_file)
    repository.initialize()
    return repository


class FakeGmailService:
    def __init__(self, raw_message: str) -> None:
        self.raw_message = raw_message

    def get_message(self, message_id: str):
        return {"id": message_id, "raw": self.raw_message}


def _seed_message_with_attachment(test_db: DatabaseRepository) -> str:
    mime_content = (
        "From: Alice <alice@example.com>\r\n"
        "Subject: Attachment\r\n"
        'Content-Type: multipart/mixed; boundary="boundary"\r\n'
        "\r\n"
        "--boundary\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "\r\n"
        "Body\r\n"
        "--boundary\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="report.pdf"\r\n'
        "\r\n"
        "pdf-content\r\n"
        "--boundary--"
    )
    raw_b64 = base64.urlsafe_b64encode(mime_content.encode()).decode()
    message_id = "msg-attachment"
    with test_db.transaction() as conn:
        test_db.upsert_message(
            conn,
            Message(
                id=message_id,
                thread_id="thread-attachment",
                subject="Attachment",
                sender="Alice",
                snippet="Body",
                timestamp=datetime.now(),
                has_attachments=True,
                attachments=[
                    Attachment(
                        id=f"{message_id}:1",
                        message_id=message_id,
                        attachment_index=1,
                        filename="report.pdf",
                        mime_type="application/pdf",
                        size_bytes=11,
                        content_disposition="attachment",
                    )
                ],
            ),
        )
    return raw_b64


def test_thread_viewer_exposes_attachment_metadata(test_db):
    """Thread viewer should include attachment lists on provider messages."""
    _seed_message_with_attachment(test_db)

    messages = ThreadViewerService(test_db).list_thread_messages("thread-attachment")

    assert len(messages) == 1
    assert messages[0]["attachments"][0]["filename"] == "report.pdf"


def test_attachment_service_downloads_to_configured_directory(test_db, tmp_path):
    """Attachment downloads should write files into the configured directory."""
    raw_b64 = _seed_message_with_attachment(test_db)
    service = AttachmentService(test_db)
    gmail = FakeGmailService(raw_b64)
    original_directory = settings.attachments.download_directory
    settings.attachments.download_directory = str(tmp_path)
    try:
        result = service.download_attachment(
            message_id="msg-attachment",
            attachment_id="msg-attachment:1",
            gmail_service=gmail,
        )
    finally:
        settings.attachments.download_directory = original_directory

    assert result.path.parent == tmp_path.resolve()
    assert result.path.name == "report.pdf"
    assert result.path.read_bytes() == b"pdf-content"


def test_attachment_service_avoids_filename_collisions(test_db, tmp_path):
    """Repeated attachment downloads should not overwrite existing files."""
    raw_b64 = _seed_message_with_attachment(test_db)
    service = AttachmentService(test_db)
    gmail = FakeGmailService(raw_b64)
    original_directory = settings.attachments.download_directory
    settings.attachments.download_directory = str(tmp_path)
    try:
        first = service.download_attachment(
            message_id="msg-attachment",
            attachment_id="msg-attachment:1",
            gmail_service=gmail,
        )
        second = service.download_attachment(
            message_id="msg-attachment",
            attachment_id="msg-attachment:1",
            gmail_service=gmail,
        )
    finally:
        settings.attachments.download_directory = original_directory

    assert first.path.name == "report.pdf"
    assert second.path.name == "report-1.pdf"

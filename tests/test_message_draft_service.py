from datetime import datetime

import pytest

from shmail.services.db import DatabaseService
from shmail.services.message_draft import MessageDraftService


@pytest.fixture
def test_db(tmp_path):
    """Provides isolated DB for message-draft service tests."""
    db_file = tmp_path / "draft_service.db"
    db_service = DatabaseService(db_path=db_file)
    db_service.initialize()
    return db_service


def test_resolve_or_create_draft_reuses_seeded_reply_draft(test_db):
    """Ensure seed-based draft lookup returns existing reply draft."""
    service = MessageDraftService(database=test_db)
    first = service.resolve_or_create_draft(
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Subject",
        body="Hello",
        source_message_id="msg_1",
        source_thread_id="thread_1",
    )

    second = service.resolve_or_create_draft(
        mode="reply",
        to_addresses="ignored@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Subject",
        body="Different",
        source_message_id="msg_1",
        source_thread_id="thread_1",
    )

    assert second.id == first.id
    assert second.to_addresses == "alice@example.com"


def test_save_draft_updates_timestamp_and_body(test_db):
    """Ensure save_draft updates content and refreshed updated_at."""
    service = MessageDraftService(database=test_db)
    draft = service.resolve_or_create_draft(
        mode="new",
        to_addresses="",
        cc_addresses="",
        bcc_addresses="",
        subject="",
        body="alpha",
        source_message_id=None,
        source_thread_id=None,
    )

    refreshed = draft.model_copy(update={"body": "beta", "updated_at": datetime.now()})
    saved = service.save_draft(refreshed)

    assert saved.body == "beta"
    loaded = service.get_draft(saved.id)
    assert loaded is not None
    assert loaded.body == "beta"

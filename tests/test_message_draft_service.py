from datetime import timezone

import pytest

from shmail.services.db import DatabaseRepository
from shmail.services.message_draft import MessageDraftService
from shmail.services.time import now_utc


@pytest.fixture
def test_db(tmp_path):
    """Provides isolated DB for message-draft service tests."""
    db_file = tmp_path / "draft_service.db"
    repository = DatabaseRepository(db_path=db_file)
    repository.initialize()
    return repository


def test_resolve_or_create_draft_reuses_seeded_reply_draft(test_db):
    """Ensure seed-based draft lookup returns existing reply draft."""
    service = MessageDraftService(repository=test_db)
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
    service = MessageDraftService(repository=test_db)
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

    refreshed = draft.model_copy(update={"body": "beta", "updated_at": now_utc()})
    saved = service.save_draft(refreshed)

    assert saved.body == "beta"
    assert saved.created_at.tzinfo == timezone.utc
    assert saved.updated_at.tzinfo == timezone.utc
    loaded = service.get_draft(saved.id)
    assert loaded is not None
    assert loaded.body == "beta"
    assert loaded.created_at.tzinfo == timezone.utc
    assert loaded.updated_at.tzinfo == timezone.utc


def test_cancel_queued_send_restores_editable_draft(test_db):
    """Ensure queued drafts can be restored back into editable state."""
    service = MessageDraftService(repository=test_db)
    draft = service.resolve_or_create_draft(
        mode="new",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Hello",
        body="queued",
        source_message_id=None,
        source_thread_id="thread-queued",
    )

    queued = service.queue_draft_for_send(draft)
    restored = service.cancel_queued_send(queued.id)

    assert restored is not None
    assert restored.state == "editing"
    assert restored.queued_at is None
    assert test_db.get_total_local_draft_count() == 1
    assert test_db.get_total_outbox_count() == 0


def test_cancel_queued_sends_in_thread_restores_all_thread_drafts(test_db):
    """Ensure thread-level outbox cancel restores every queued draft in the thread."""
    service = MessageDraftService(repository=test_db)
    first = service.resolve_or_create_draft(
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="One",
        body="one",
        source_message_id="m-one",
        source_thread_id="thread-bulk",
    )
    second = service.resolve_or_create_draft(
        mode="forward",
        to_addresses="bob@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Two",
        body="two",
        source_message_id="m-two",
        source_thread_id="thread-bulk",
    )
    service.queue_draft_for_send(first)
    service.queue_draft_for_send(second)

    restored_ids = service.cancel_queued_sends_in_thread("thread-bulk")

    assert sorted(restored_ids) == sorted([first.id, second.id])
    assert test_db.get_total_local_draft_count() == 2
    assert test_db.get_total_outbox_count() == 0

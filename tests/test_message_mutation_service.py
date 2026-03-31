from datetime import timezone

import pytest

from shmail.models import Label, Message
from shmail.services.db import DatabaseRepository
from shmail.services.message_draft import MessageDraftService
from shmail.services.message_mutation import MessageMutationService
from shmail.services.outbound_message import OutboundMessageService
from shmail.services.time import now_utc


@pytest.fixture
def test_db(tmp_path):
    """Provide an isolated repository for local-first mutation tests."""
    db_file = tmp_path / "message_mutation.db"
    repository = DatabaseRepository(db_path=db_file)
    repository.initialize()
    return repository


def _store_message(
    repository: DatabaseRepository,
    *,
    message_id: str,
    thread_id: str,
    label_ids: list[str],
) -> None:
    now = now_utc()
    labels = [
        Label(id=label_id, name=label_id, type="system") for label_id in label_ids
    ]
    message = Message(
        id=message_id,
        thread_id=thread_id,
        subject="Hello",
        sender="Alice",
        sender_address="alice@example.com",
        recipient_to="bob@example.com",
        recipient_to_addresses="bob@example.com",
        recipient_cc="",
        recipient_cc_addresses="",
        recipient_bcc="",
        recipient_bcc_addresses="",
        snippet="preview",
        body="Body",
        timestamp=now,
        is_read="UNREAD" not in label_ids,
        labels=labels,
    )
    with repository.transaction() as conn:
        repository.upsert_message(conn, message)


def test_trash_message_hides_from_inbox_and_moves_to_trash_view(test_db):
    """Trash should disappear from Inbox immediately and show in Trash."""
    _store_message(test_db, message_id="m-1", thread_id="t-1", label_ids=["INBOX"])
    service = MessageMutationService(test_db)

    service.trash_message(
        account_id="user@example.com",
        provider_key="gmail",
        message_id="m-1",
        current_view_label_id="INBOX",
    )

    assert test_db.get_threads("INBOX") == []
    trash_threads = test_db.get_threads("TRASH")
    assert len(trash_threads) == 1
    assert trash_threads[0]["thread_id"] == "t-1"


def test_move_message_removes_current_container_and_adds_destination(test_db):
    """Move should swap visible containers while preserving provider-agnostic intent."""
    _store_message(test_db, message_id="m-2", thread_id="t-2", label_ids=["INBOX"])
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "projects", "Projects", "user")
    service = MessageMutationService(test_db)

    service.move_message(
        account_id="user@example.com",
        provider_key="gmail",
        message_id="m-2",
        destination_label_id="projects",
        current_view_label_id="INBOX",
    )

    assert test_db.get_threads("INBOX") == []
    project_threads = test_db.get_threads("projects")
    assert len(project_threads) == 1
    assert project_threads[0]["thread_id"] == "t-2"


def test_restore_message_moves_thread_out_of_trash(test_db):
    """Restore should remove local trash visibility and re-add Inbox."""
    _store_message(
        test_db, message_id="m-restore", thread_id="t-restore", label_ids=["TRASH"]
    )
    service = MessageMutationService(test_db)

    service.restore_message(
        account_id="user@example.com",
        provider_key="gmail",
        message_id="m-restore",
        current_view_label_id="TRASH",
    )

    assert test_db.get_threads("TRASH") == []
    inbox_threads = test_db.get_threads("INBOX")
    assert len(inbox_threads) == 1
    assert inbox_threads[0]["thread_id"] == "t-restore"


def test_queue_send_moves_draft_from_drafts_to_outbox(test_db):
    """Queued send should freeze the draft locally and expose it in Outbox."""
    drafts = MessageDraftService(test_db)
    outbound = OutboundMessageService(test_db)
    draft = drafts.resolve_or_create_draft(
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Hello",
        body="Queued body",
        source_message_id="m-3",
        source_thread_id="t-3",
    )

    result = outbound.queue_send(
        account_id="user@example.com",
        provider_key="gmail",
        draft=draft,
    )

    queued = drafts.get_draft(result.draft_id)
    assert queued is not None
    assert queued.state == "queued_to_send"
    assert queued.queued_at is not None
    assert queued.queued_at.tzinfo == timezone.utc
    assert test_db.get_total_local_draft_count() == 0
    assert test_db.get_total_outbox_count() == 1
    outbox_threads = test_db.get_threads("OUTBOX")
    assert len(outbox_threads) == 1
    assert outbox_threads[0]["thread_id"] == "t-3"

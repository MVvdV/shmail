from datetime import datetime

import pytest

from shmail.models import Message, MessageDraft
from shmail.services.db import DatabaseRepository


@pytest.fixture
def test_db(tmp_path):
    """Provides a temporary database for testing."""
    db_file = tmp_path / "test.db"
    repository = DatabaseRepository(db_path=db_file)
    repository.initialize()
    return repository


def test_upsert_label(test_db):
    """Tests saving and updating a label."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "SYSTEM")

    labels = test_db.get_labels()
    assert len(labels) == 1
    assert labels[0]["id"] == "INBOX"
    assert labels[0]["name"] == "Inbox"
    assert labels[0]["type"] == "SYSTEM"

    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Incoming", "SYSTEM")
    labels = test_db.get_labels()
    assert len(labels) == 1
    assert labels[0]["name"] == "Incoming"


def test_get_labels_ordering(test_db):
    """Tests that labels are returned in the correct order (System first)."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "USER_1", "Z-Label", "user")
        test_db.upsert_label(conn, "INBOX", "Inbox", "SYSTEM")
        test_db.upsert_label(conn, "USER_2", "A-Label", "user")

    labels = test_db.get_labels()

    assert labels[0]["id"] == "INBOX"
    assert labels[1]["name"] == "A-Label"
    assert labels[2]["name"] == "Z-Label"


def test_metadata_storage(test_db):
    """Test saving and retrieving metadata"""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "last_history_id", "12345")
    assert test_db.get_metadata("last_history_id") == "12345"

    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "last_history_id", "67890")
    assert test_db.get_metadata("last_history_id") == "67890"
    assert test_db.get_metadata("non_existent") is None


def test_message_body_metadata_schema_and_persistence(test_db):
    """Ensure message body metadata columns are created and persisted."""
    with test_db.get_connection() as conn:
        columns = {
            row["name"]: row
            for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }

    assert "body_source" in columns
    assert "body_links" in columns
    assert "body_content_type" in columns
    assert "body_charset" in columns
    assert "body_link_count" in columns
    assert "body_conversion_warnings" in columns

    message = Message(
        id="msg_1",
        thread_id="thread_1",
        subject="Subject",
        sender="sender@example.com",
        snippet="snippet",
        body="example",
        body_links='[{"label":"example","href":"https://example.com","executable":true}]',
        body_source="html",
        body_content_type="text/html",
        body_charset="utf-8",
        body_link_count=1,
        body_conversion_warnings="[]",
        timestamp=datetime.now(),
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message)

    with test_db.get_connection() as conn:
        row = conn.execute(
            "SELECT body_links, body_source, body_content_type, body_charset, body_link_count, body_conversion_warnings FROM messages WHERE id = ?",
            ("msg_1",),
        ).fetchone()

    assert row is not None
    assert row["body_links"] is not None
    assert row["body_source"] == "html"
    assert row["body_content_type"] == "text/html"
    assert row["body_charset"] == "utf-8"
    assert row["body_link_count"] == 1
    assert row["body_conversion_warnings"] == "[]"


def test_foreign_key_cascade_removes_message_labels_on_delete(test_db):
    """Ensure deleting a message cascades to message_labels rows."""
    message = Message(
        id="msg_fk_1",
        thread_id="thread_fk",
        subject="Subject",
        sender="sender@example.com",
        snippet="snippet",
        timestamp=datetime.now(),
    )

    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "SYSTEM")
        test_db.upsert_message(conn, message)
        conn.execute(
            "INSERT OR IGNORE INTO message_labels (message_id, label_id) VALUES (?, ?)",
            ("msg_fk_1", "INBOX"),
        )

    with test_db.transaction() as conn:
        test_db.remove_message(conn, "msg_fk_1")

    with test_db.get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM message_labels WHERE message_id = ?",
            ("msg_fk_1",),
        ).fetchone()
    assert row is not None
    assert row["count"] == 0


def test_upsert_message_replace_refreshes_label_associations(test_db):
    """Ensure message replace does not retain stale label associations."""
    first = Message(
        id="msg_fk_2",
        thread_id="thread_fk",
        subject="One",
        sender="sender@example.com",
        snippet="snippet",
        timestamp=datetime.now(),
    )
    second = Message(
        id="msg_fk_2",
        thread_id="thread_fk",
        subject="Two",
        sender="sender@example.com",
        snippet="snippet",
        timestamp=datetime.now(),
    )

    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "SYSTEM")
        test_db.upsert_label(conn, "SENT", "Sent", "SYSTEM")
        test_db.upsert_message(conn, first)
        conn.execute(
            "INSERT OR IGNORE INTO message_labels (message_id, label_id) VALUES (?, ?)",
            ("msg_fk_2", "INBOX"),
        )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, second)
        conn.execute(
            "INSERT OR IGNORE INTO message_labels (message_id, label_id) VALUES (?, ?)",
            ("msg_fk_2", "SENT"),
        )

    with test_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT label_id FROM message_labels WHERE message_id = ? ORDER BY label_id",
            ("msg_fk_2",),
        ).fetchall()

    assert [row["label_id"] for row in rows] == ["SENT"]


def test_message_draft_schema_and_persistence(test_db):
    """Ensure message_drafts schema exists and supports upsert/get/delete."""
    with test_db.get_connection() as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='message_drafts'"
        ).fetchone()
    assert table is not None

    now = datetime.now()
    draft = MessageDraft(
        id="draft_1",
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Subject",
        body="Draft body",
        source_message_id="msg_123",
        source_thread_id="thread_123",
        created_at=now,
        updated_at=now,
    )

    with test_db.transaction() as conn:
        test_db.upsert_message_draft(conn, draft)

    loaded = test_db.get_message_draft("draft_1")
    assert loaded is not None
    assert loaded["subject"] == "Re: Subject"

    by_source = test_db.get_message_draft_by_source(
        mode="reply",
        source_message_id="msg_123",
        source_thread_id="thread_123",
    )
    assert by_source is not None
    assert by_source["id"] == "draft_1"

    with test_db.transaction() as conn:
        test_db.remove_message_draft(conn, "draft_1")

    assert test_db.get_message_draft("draft_1") is None


def test_get_threads_for_draft_label_returns_draft_backed_threads(test_db):
    """Ensure DRAFT label query surfaces local message draft threads."""
    now = datetime.now()
    draft = MessageDraft(
        id="draft_thread_1",
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Draft Subject",
        body="Draft body",
        source_message_id="msg_1",
        source_thread_id="thread_abc",
        created_at=now,
        updated_at=now,
    )

    with test_db.transaction() as conn:
        test_db.upsert_message_draft(conn, draft)

    rows = test_db.get_threads("DRAFT")
    assert rows
    assert rows[0]["thread_id"] == "thread_abc"
    assert rows[0]["has_draft"] == 1
    assert rows[0]["draft_count"] == 1


def test_get_thread_messages_includes_local_draft_rows(test_db):
    """Ensure thread message query merges persisted draft rows."""
    now = datetime.now()
    message = Message(
        id="msg_real",
        thread_id="thread_merge",
        subject="Subject",
        sender="sender@example.com",
        snippet="snippet",
        timestamp=now,
    )
    draft = MessageDraft(
        id="draft_merge",
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Subject",
        body="Draft update",
        source_message_id="msg_real",
        source_thread_id="thread_merge",
        created_at=now,
        updated_at=now,
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message)
        test_db.upsert_message_draft(conn, draft)

    rows = test_db.get_thread_messages("thread_merge")
    assert len(rows) == 2
    assert any(row.get("is_draft") == 1 for row in rows)
    assert any(row.get("draft_id") == "draft_merge" for row in rows)


def test_get_thread_messages_sorts_mixed_timezone_timestamps_without_crash(test_db):
    """Ensure mixed aware/naive timestamp rows sort safely with draft rows."""
    aware = datetime.fromisoformat("2026-03-24T12:00:00+00:00")
    draft_time = datetime.fromisoformat("2026-03-24T12:30:00")

    message = Message(
        id="msg_tz",
        thread_id="thread_tz",
        subject="TZ",
        sender="sender@example.com",
        snippet="snippet",
        timestamp=aware,
    )
    draft = MessageDraft(
        id="draft_tz",
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: TZ",
        body="Body",
        source_message_id="msg_tz",
        source_thread_id="thread_tz",
        created_at=draft_time,
        updated_at=draft_time,
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message)
        test_db.upsert_message_draft(conn, draft)

    rows = test_db.get_thread_messages("thread_tz")
    assert len(rows) == 2


def test_get_thread_messages_places_drafts_above_their_source_messages(test_db):
    """Ensure thread drafts render immediately above their seeded source message."""
    newer = datetime.fromisoformat("2026-03-24T12:00:00+00:00")
    older = datetime.fromisoformat("2026-03-24T11:00:00+00:00")

    message_new = Message(
        id="msg_new",
        thread_id="thread_ordered",
        subject="Newer",
        sender="sender@example.com",
        snippet="new",
        timestamp=newer,
    )
    message_old = Message(
        id="msg_old",
        thread_id="thread_ordered",
        subject="Older",
        sender="sender@example.com",
        snippet="old",
        timestamp=older,
    )
    draft_new = MessageDraft(
        id="draft_new",
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Newer",
        body="draft newer",
        source_message_id="msg_new",
        source_thread_id="thread_ordered",
        created_at=newer,
        updated_at=newer,
    )
    draft_old = MessageDraft(
        id="draft_old",
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Older",
        body="draft older",
        source_message_id="msg_old",
        source_thread_id="thread_ordered",
        created_at=older,
        updated_at=older,
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message_new)
        test_db.upsert_message(conn, message_old)
        test_db.upsert_message_draft(conn, draft_new)
        test_db.upsert_message_draft(conn, draft_old)

    rows = test_db.get_thread_messages("thread_ordered")

    assert [row["id"] for row in rows] == [
        "draft:draft_new",
        "msg_new",
        "draft:draft_old",
        "msg_old",
    ]


def test_get_labels_with_counts_uses_total_local_drafts_for_draft_label(test_db):
    """Ensure DRAFT label count reflects local draft total, not unread mail."""
    now = datetime.now()
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "DRAFT", "Draft", "system")
        test_db.upsert_message_draft(
            conn,
            MessageDraft(
                id="draft_count_1",
                mode="new",
                to_addresses="a@example.com",
                cc_addresses="",
                bcc_addresses="",
                subject="Draft 1",
                body="Body 1",
                source_message_id=None,
                source_thread_id=None,
                created_at=now,
                updated_at=now,
            ),
        )
        test_db.upsert_message_draft(
            conn,
            MessageDraft(
                id="draft_count_2",
                mode="new",
                to_addresses="b@example.com",
                cc_addresses="",
                bcc_addresses="",
                subject="Draft 2",
                body="Body 2",
                source_message_id=None,
                source_thread_id=None,
                created_at=now,
                updated_at=now,
            ),
        )

    labels = test_db.get_labels_with_counts()
    draft_label = next((label for label in labels if label["id"] == "DRAFT"), None)
    assert draft_label is not None
    assert draft_label["unread_count"] == 2

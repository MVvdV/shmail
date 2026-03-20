from datetime import datetime

import pytest

from shmail.models import Message
from shmail.services.db import DatabaseService


@pytest.fixture
def test_db(tmp_path):
    """Provides a temporary database for testing."""
    db_file = tmp_path / "test.db"
    db_service = DatabaseService(db_path=db_file)
    db_service.initialize()
    return db_service


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

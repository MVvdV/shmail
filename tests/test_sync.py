from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from googleapiclient.errors import HttpError

from shmail.models import Message, Label
from shmail.services.db import DatabaseService
from shmail.services.sync import SyncService, SyncResult


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_shmail.db"
    db_service = DatabaseService(db_path=db_file)
    db_service.initialize()
    return db_service


@pytest.fixture
def sync_service(test_db):
    with patch("shmail.services.sync.AuthService"):
        service = SyncService("test@example.com", database=test_db)
        with patch.object(
            SyncService, "gmail", new_callable=PropertyMock
        ) as mock_gmail:
            mock_gmail.return_value = MagicMock()
            yield service


def test_incremental_sync_returns_result(sync_service, test_db):
    """Verify incremental_sync returns a populated SyncResult."""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "1000")

    sync_service.gmail.list_history.return_value = {
        "history": [
            {
                "id": "1001",
                "messagesAdded": [
                    {"message": {"id": "new_msg", "threadId": "t1", "labelIds": []}}
                ],
                "messagesDeleted": [{"message": {"id": "old_msg", "threadId": "t1"}}],
            }
        ],
        "historyId": "1001",
    }

    sync_service.gmail.get_message.return_value = {
        "id": "new_msg",
        "threadId": "t1",
        "labelIds": [],
        "raw": "Ym9keQ==",
    }

    result = sync_service.incremental_sync()

    assert isinstance(result, SyncResult)
    assert result.added == 1
    assert result.removed == 1
    assert result.any_changes is True


def test_incremental_sync_deleted_messages(sync_service, test_db):
    """Test handling of deleted messages and check result."""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "1000")
        message = Message(
            id="msg_to_delete",
            thread_id="t1",
            subject="Bye",
            sender="x@y.com",
            snippet="...",
            timestamp=datetime.now(),
            labels=[Label(id="INBOX", name="Inbox", type="system")],
        )
        test_db.upsert_message(conn, message)

    sync_service.gmail.list_history.return_value = {
        "history": [
            {
                "id": "1001",
                "messagesDeleted": [
                    {"message": {"id": "msg_to_delete", "threadId": "t1"}}
                ],
            }
        ],
        "historyId": "1001",
    }

    result = sync_service.incremental_sync()

    assert result.removed == 1
    with test_db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM messages WHERE id = ?", ("msg_to_delete",)
        ).fetchone()
    assert row is None
    assert test_db.get_metadata("history_id") == "1001"


def test_incremental_sync_expired_id(sync_service, test_db):
    """Test fallback to initial_sync when historyId is expired (404/410)."""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "expired_id")

    resp = MagicMock()
    resp.status = 404
    sync_service.gmail.list_history.side_effect = HttpError(resp=resp, content=b"")

    sync_service.initial_sync = MagicMock()

    result = sync_service.incremental_sync()

    assert sync_service.initial_sync.called
    assert result.any_changes is True


def test_incremental_sync_label_changes(sync_service, test_db):
    """Test handling of added and removed labels and check result."""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "1000")
        message_id = "msg_1"

        message = Message(
            id=message_id,
            thread_id="t1",
            subject="Hello",
            sender="x@y.com",
            snippet="...",
            timestamp=datetime.now(),
            labels=[Label(id="UNREAD", name="Unread", type="system")],
        )
        test_db.upsert_message(conn, message)

    sync_service.gmail.list_history.return_value = {
        "history": [
            {
                "id": "1001",
                "labelsRemoved": [
                    {"message": {"id": message_id}, "labelIds": ["UNREAD"]}
                ],
                "labelsAdded": [{"message": {"id": message_id}, "labelIds": ["INBOX"]}],
            }
        ],
        "historyId": "1001",
    }

    result = sync_service.incremental_sync()

    assert result.labels_changed == 2
    with test_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT label_id FROM message_labels WHERE message_id = ?", (message_id,)
        ).fetchall()
        label_ids = [row["label_id"] for row in rows]

    assert "UNREAD" not in label_ids
    assert "INBOX" in label_ids

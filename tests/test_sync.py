from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from shmail.models import Email, Label
from shmail.services.db import DatabaseService
from shmail.services.sync import SyncService, SyncResult


# Fixture to create a temporary, fresh database for every test
@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_shmail.db"
    db_service = DatabaseService(db_path=db_file)
    db_service.initialize()
    return db_service


# Fixture to setup the SyncService with mocked Gmail and DB
@pytest.fixture
def sync_service(test_db):
    with patch("shmail.services.sync.AuthService"):
        service = SyncService("test@example.com", database=test_db)
        service.gmail = MagicMock()
        return service


def test_incremental_sync_returns_result(sync_service, test_db):
    """Verify incremental_sync returns a populated SyncResult."""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "1000")

    # Mock history API with 1 message added and 1 deleted
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

    # Mock get_message for the added message
    sync_service.gmail.get_message.return_value = {
        "id": "new_msg",
        "threadId": "t1",
        "labelIds": [],
        "raw": "Ym9keQ==",  # Base64 for 'body'
    }

    result = sync_service.incremental_sync()

    assert isinstance(result, SyncResult)
    assert result.added == 1
    assert result.removed == 1
    assert result.any_changes is True


def test_incremental_sync_deleted_messages(sync_service, test_db):
    """Test handling of deleted messages and check result."""
    # 1. Setup: Add a message to the DB manually
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "1000")
        email = Email(
            id="msg_to_delete",
            thread_id="t1",
            subject="Bye",
            sender="x@y.com",
            snippet="...",
            timestamp=datetime.now(),
            labels=[Label(id="INBOX", name="Inbox", type="system")],
        )
        test_db.upsert_email(conn, email)

    # 2. Mock: History API returns a deleted event
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

    # 3. Execute
    result = sync_service.incremental_sync()

    # 4. Verify
    assert result.removed == 1
    with test_db.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM emails WHERE id = ?", ("msg_to_delete",)
        ).fetchone()
    assert row is None
    assert test_db.get_metadata("history_id") == "1001"


def test_incremental_sync_expired_id(sync_service, test_db):
    """Test fallback to initial_sync when historyId is expired (404/410)."""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "expired_id")

    # 1. Mock: list_history raises a 404 HttpError
    resp = MagicMock()
    resp.status = 404
    sync_service.gmail.list_history.side_effect = HttpError(resp=resp, content=b"")

    # 2. Mock initial_sync to track calls
    sync_service.initial_sync = MagicMock()

    # 3. Execute
    result = sync_service.incremental_sync()

    # 4. Verify initial_sync was called and result reflects changes
    assert sync_service.initial_sync.called
    assert result.any_changes is True


def test_incremental_sync_label_changes(sync_service, test_db):
    """Test handling of added and removed labels and check result."""
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "history_id", "1000")
        email_id = "msg_1"

        # Setup initial state
        email = Email(
            id=email_id,
            thread_id="t1",
            subject="Hello",
            sender="x@y.com",
            snippet="...",
            timestamp=datetime.now(),
            labels=[Label(id="UNREAD", name="Unread", type="system")],
        )
        test_db.upsert_email(conn, email)

    # Mock history: Remove UNREAD, Add INBOX
    sync_service.gmail.list_history.return_value = {
        "history": [
            {
                "id": "1001",
                "labelsRemoved": [
                    {"message": {"id": email_id}, "labelIds": ["UNREAD"]}
                ],
                "labelsAdded": [{"message": {"id": email_id}, "labelIds": ["INBOX"]}],
            }
        ],
        "historyId": "1001",
    }

    # 3. Execute
    result = sync_service.incremental_sync()

    # 4. Check results
    assert result.labels_changed == 2  # 1 removed, 1 added
    with test_db.get_connection() as conn:
        rows = conn.execute(
            "SELECT label_id FROM email_labels WHERE email_id = ?", (email_id,)
        ).fetchall()
        label_ids = [row["label_id"] for row in rows]

    assert "UNREAD" not in label_ids
    assert "INBOX" in label_ids

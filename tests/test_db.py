import sqlite3
from pathlib import Path

import pytest

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
    # 1. Insert a new label
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "SYSTEM")

    labels = test_db.get_labels()
    assert len(labels) == 1
    assert labels[0]["id"] == "INBOX"
    assert labels[0]["name"] == "Inbox"
    assert labels[0]["type"] == "SYSTEM"

    # 2. Update existing label (name change)
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

    # SYSTEM should be first
    assert labels[0]["id"] == "INBOX"
    # Then user labels alphabetically
    assert labels[1]["name"] == "A-Label"
    assert labels[2]["name"] == "Z-Label"


def test_metadata_storage(test_db):
    """Test saving and retrieving metadata"""
    # Insert a new history_id
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "last_history_id", "12345")
    assert test_db.get_metadata("last_history_id") == "12345"

    # Overwrite an existing history_id
    with test_db.transaction() as conn:
        test_db.set_metadata(conn, "last_history_id", "67890")
    assert test_db.get_metadata("last_history_id") == "67890"
    assert test_db.get_metadata("non_existent") is None

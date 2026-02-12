import sqlite3
from pathlib import Path

import pytest

from shmail.services.db import DatabaseService


@pytest.fixture
def temp_db(tmp_path):
    """Provides a temporary database for testing."""
    db_file = tmp_path / "test.db"
    db_service = DatabaseService(db_path=db_file)
    db_service.initialize()
    return db_service


def test_upsert_label(temp_db):
    """Tests saving and updating a label."""
    # 1. Insert a new label
    temp_db.upsert_label("INBOX", "Inbox", "SYSTEM")

    labels = temp_db.get_labels()
    assert len(labels) == 1
    assert labels[0]["id"] == "INBOX"
    assert labels[0]["name"] == "Inbox"
    assert labels[0]["type"] == "SYSTEM"

    # 2. Update existing label (name change)
    temp_db.upsert_label("INBOX", "Incoming", "SYSTEM")
    labels = temp_db.get_labels()
    assert len(labels) == 1
    assert labels[0]["name"] == "Incoming"


def test_get_labels_ordering(temp_db):
    """Tests that labels are returned in the correct order (System first)."""
    temp_db.upsert_label("USER_1", "Z-Label", "user")
    temp_db.upsert_label("INBOX", "Inbox", "SYSTEM")
    temp_db.upsert_label("USER_2", "A-Label", "user")

    labels = temp_db.get_labels()

    # SYSTEM should be first
    assert labels[0]["id"] == "INBOX"
    # Then user labels alphabetically
    assert labels[1]["name"] == "A-Label"
    assert labels[2]["name"] == "Z-Label"


def test_metadata_storage(temp_db):
    """Test saving and retrieving metadata"""
    # Insert a new history_id
    temp_db.set_metadata("last_history_id", "12345")
    assert temp_db.get_metadata("last_history_id") == "12345"
    # Overwrite an existing history_id
    temp_db.set_metadata("last_history_id", "67890")
    assert temp_db.get_metadata("last_history_id") == "67890"
    assert temp_db.get_metadata("non_existent") is None

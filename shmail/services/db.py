import contextlib
import sqlite3
from pathlib import Path
from typing import Generator, List, Optional

from shmail.config import CONFIG_DIR

DB_PATH = CONFIG_DIR / "shmail.db"


class DatabaseService:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provides a safe way to connect to the database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = (
            sqlite3.Row
        )  # This lets us access columns by name like row['subject']
        try:
            yield conn
        finally:
            conn.close()

    def initialize(self):
        """Creates the tables if they don't exist."""
        with self.get_connection() as conn:
            # Enable WAL mode for concurrency
            conn.execute("PRAGMA journal_mode=WAL")

            # 1. The main email data
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    subject TEXT,
                    sender TEXT,
                    snippet TEXT,
                    body TEXT,
                    timestamp DATETIME,
                    is_read BOOLEAN DEFAULT 0,
                    has_attachments BOOLEAN DEFAULT 0
                )
            """)

            # 2. The list of labels
            conn.execute("""
                CREATE TABLE IF NOT EXISTS labels (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE,
                    type TEXT
                )
            """)

            # 3. The mapping between them (Many-to-Many)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS email_labels (
                    email_id TEXT,
                    label_id TEXT,
                    PRIMARY KEY (email_id, label_id),
                    FOREIGN KEY (email_id) REFERENCES emails (id) ON DELETE CASCADE,
                    FOREIGN KEY (label_id) REFERENCES labels (id) ON DELETE CASCADE
                )
            """)

            # 4. Global metadata/sync state
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            conn.commit()

    def set_metadata(self, key: str, value: str):
        """
        Sets a metadata value in the database.
        """
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()

    def get_metadata(self, key: str):
        """
        Retrieves a metadata value by key.
        """
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def upsert_email(self, email):
        """Saves or updates an email and its label associations."""
        with self.get_connection() as conn:
            # 1. Save the email (Insert or Replace if ID exists)
            conn.execute(
                """
                INSERT OR REPLACE INTO emails
                (id, thread_id, subject, sender, snippet, body, timestamp, is_read, has_attachments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    email.id,
                    email.thread_id,
                    email.subject,
                    email.sender,
                    email.snippet,
                    email.body,
                    email.timestamp.isoformat(),
                    int(email.is_read),
                    int(email.has_attachments),
                ),
            )

            # 2. Handle labels
            for label in email.labels:
                # Ensure the label exists in our master labels table
                conn.execute(
                    "INSERT OR IGNORE INTO labels (id, name, type) VALUES (?, ?, ?)",
                    (label.id, label.name, label.type),
                )
                # Link the email to that label
                conn.execute(
                    "INSERT OR IGNORE INTO email_labels (email_id, label_id) VALUES (?, ?)",
                    (email.id, label.id),
                )

            conn.commit()

    def upsert_label(self, label_id: str, label_name: str, label_type: str):
        """
        Saves or updates a label in the master labels table.
        """
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO labels (id, name, type) VALUES (?, ?, ?)",
                (label_id, label_name, label_type),
            )
            conn.commit()

    def get_labels(self):
        """
        Returns all labels from the DB.
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, type FROM labels ORDER BY type ASC, name ASC"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def remove_email(self, email_id: str):
        """Removes an email and its label associations from the DB."""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
            conn.commit()

    def update_labels(
        self,
        email_id: str,
        added_label_ids: Optional[List[str]] = None,
        removed_label_ids: Optional[List[str]] = None,
    ):
        """Updates labels, defaulting to empty lists if none are provided."""
        # Convert None to empty list
        added = added_label_ids or []
        removed = removed_label_ids or []

        with self.get_connection() as conn:
            if removed:
                placeholders = ", ".join(["?"] * len(removed))
                delete_sql = f"DELETE FROM email_labels WHERE email_id = ? AND label_id IN ({placeholders})"
                conn.execute(delete_sql, [email_id] + removed)

            if added:
                insert_sql = "INSERT OR IGNORE INTO email_labels (email_id, label_id) VALUES (?, ?)"
                insert_params = [(email_id, list_id) for list_id in added]
                conn.executemany(insert_sql, insert_params)

            conn.commit()


# Global instance for easy access
db = DatabaseService()

import sqlite3
import contextlib
from pathlib import Path
from typing import Generator
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
                    name TEXT UNIQUE
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
                    "INSERT OR IGNORE INTO labels (id, name) VALUES (?, ?)",
                    (label.id, label.name),
                )
                # Link the email to that label
                conn.execute(
                    "INSERT OR IGNORE INTO email_labels (email_id, label_id) VALUES (?, ?)",
                    (email.id, label.id),
                )

            conn.commit()


# Global instance for easy access
db = DatabaseService()

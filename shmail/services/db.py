import contextlib
import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Generator, List, Optional

if TYPE_CHECKING:
    from shmail.models import Email

from shmail.config import CONFIG_DIR

DB_PATH = CONFIG_DIR / "shmail.db"

logger = logging.getLogger(__name__)


class DatabaseService:
    """Provides local SQLite persistence for emails, labels, and contacts."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for obtaining a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for executing database operations within a transaction."""
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("Database transaction failed")
                raise

    def initialize(self):
        """Creates the database schema if it does not already exist."""
        try:
            with self.get_connection() as conn:
                conn.execute("PRAGMA journal_mode=WAL")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS emails (
                        id TEXT PRIMARY KEY,
                        thread_id TEXT,
                        subject TEXT,
                        sender TEXT,
                        sender_address TEXT,
                        recipient_to TEXT,
                        recipient_to_addresses TEXT,
                        recipient_cc TEXT,
                        recipient_cc_addresses TEXT,
                        recipient_bcc TEXT,
                        recipient_bcc_addresses TEXT,
                        snippet TEXT,
                        body TEXT,
                        timestamp DATETIME,
                        is_read BOOLEAN DEFAULT 0,
                        has_attachments BOOLEAN DEFAULT 0
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS labels (
                        id TEXT PRIMARY KEY,
                        name TEXT UNIQUE,
                        type TEXT
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS email_labels (
                        email_id TEXT,
                        label_id TEXT,
                        PRIMARY KEY (email_id, label_id),
                        FOREIGN KEY (email_id) REFERENCES emails (id) ON DELETE CASCADE,
                        FOREIGN KEY (label_id) REFERENCES labels (id) ON DELETE CASCADE
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS contacts (
                        email TEXT PRIMARY KEY,
                        name TEXT,
                        interaction_count INTEGER DEFAULT 1,
                        last_interaction DATETIME
                    )
                """)
                conn.commit()
        except Exception:
            logger.exception("Failed to initialize database schema")
            raise

    def get_metadata(self, key: str) -> Optional[str]:
        """Retrieves a single metadata value by key."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def get_email(self, email_id: str) -> Optional[dict]:
        """Returns a single email by its ID, joined with contact names."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT e.*, c_sender.name as sender_name
                FROM emails e
                LEFT JOIN contacts c_sender ON e.sender_address = c_sender.email
                WHERE e.id = ?
                """,
                (email_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_emails(self, label_id: str, limit: int = 50, offset: int = 0) -> List[dict]:
        """Returns emails for a specific label, joined with contact names, ordered by recency."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT e.*, COALESCE(NULLIF(c.name, ''), e.sender) as sender_display
                FROM emails e
                JOIN email_labels el ON e.id = el.email_id
                LEFT JOIN contacts c ON e.sender_address = c.email
                WHERE el.label_id = ?
                ORDER BY e.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (label_id, limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_labels(self) -> List[dict]:
        """Retrieves all synchronization labels from the database."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, type FROM labels ORDER BY type ASC, name ASC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_labels_with_counts(self) -> List[dict]:
        """Returns labels along with their unread email counts."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT l.id, l.name, l.type, COUNT(e.id) as unread_count
                FROM labels l
                LEFT JOIN email_labels el ON l.id = el.label_id
                LEFT JOIN emails e ON el.email_id = e.id AND e.is_read = 0
                GROUP BY l.id
                ORDER BY l.type ASC, l.name ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_top_contacts(self, limit: int = 50) -> List[dict]:
        """Retrieves frequently contacted addresses ordered by interaction volume."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT email, name, interaction_count, last_interaction FROM contacts ORDER BY interaction_count DESC, last_interaction DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def set_metadata(self, conn: sqlite3.Connection, key: str, value: str):
        """Persists a metadata key-value pair."""
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value),
        )

    def upsert_email(self, conn: sqlite3.Connection, email: "Email"):
        """Inserts or updates an email record in the database."""
        conn.execute(
            """
            INSERT OR REPLACE INTO emails
            (id, thread_id, subject, sender, sender_address, recipient_to, recipient_to_addresses, recipient_cc, recipient_cc_addresses, recipient_bcc, recipient_bcc_addresses, snippet, body, timestamp, is_read, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email.id,
                email.thread_id,
                email.subject,
                email.sender,
                email.sender_address,
                email.recipient_to,
                email.recipient_to_addresses,
                email.recipient_cc,
                email.recipient_cc_addresses,
                email.recipient_bcc,
                email.recipient_bcc_addresses,
                email.snippet,
                email.body,
                email.timestamp.isoformat(),
                int(email.is_read),
                int(email.has_attachments),
            ),
        )

        for label in email.labels:
            conn.execute(
                "INSERT OR IGNORE INTO labels (id, name, type) VALUES (?, ?, ?)",
                (label.id, label.name, label.type),
            )
            conn.execute(
                "INSERT OR IGNORE INTO email_labels (email_id, label_id) VALUES (?, ?)",
                (email.id, label.id),
            )

    def upsert_contact(
        self, conn: sqlite3.Connection, email: str, name: Optional[str], timestamp: str
    ):
        """Registers or updates a contact entry, incrementing interaction volume."""
        conn.execute(
            """
            INSERT INTO contacts (email, name, last_interaction)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                name = COALESCE(excluded.name, contacts.name),
                interaction_count = contacts.interaction_count + 1,
                last_interaction = MAX(contacts.last_interaction, excluded.last_interaction)
            """,
            (email, name, timestamp),
        )

    def update_labels(
        self,
        conn: sqlite3.Connection,
        email_id: str,
        added_label_ids: List[str],
        removed_label_ids: List[str],
    ):
        """Updates the association between an email and its labels."""
        added = added_label_ids or []
        removed = removed_label_ids or []

        if removed:
            placeholders = ", ".join(["?"] * len(removed))
            delete_sql = f"DELETE FROM email_labels WHERE email_id = ? AND label_id IN ({placeholders})"
            conn.execute(delete_sql, [email_id] + removed)

        if added:
            insert_sql = (
                "INSERT OR IGNORE INTO email_labels (email_id, label_id) VALUES (?, ?)"
            )
            insert_params = [(email_id, label_id) for label_id in added]
            conn.executemany(insert_sql, insert_params)

    def remove_email(self, conn: sqlite3.Connection, email_id: str):
        """Deletes an email and its label associations from the database."""
        conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))

    def upsert_label(
        self, conn: sqlite3.Connection, label_id: str, label_name: str, label_type: str
    ):
        """Inserts or updates a label entry."""
        conn.execute(
            "INSERT OR REPLACE INTO labels (id, name, type) VALUES (?, ?, ?)",
            (label_id, label_name, label_type),
        )


db = DatabaseService()

import contextlib
import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Generator, List, Optional

if TYPE_CHECKING:
    from shmail.models import Message

from shmail.config import CONFIG_DIR

DB_PATH = CONFIG_DIR / "shmail.db"

logger = logging.getLogger(__name__)


class DatabaseService:
    """Provides local SQLite persistence for messages, threads, labels, and contacts."""

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
                    CREATE TABLE IF NOT EXISTS messages (
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
                    CREATE TABLE IF NOT EXISTS message_labels (
                        message_id TEXT,
                        label_id TEXT,
                        PRIMARY KEY (message_id, label_id),
                        FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
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

    def get_message(self, message_id: str) -> Optional[dict]:
        """Returns a single message by its ID, joined with contact names."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT m.*, c_sender.name as sender_name
                FROM messages m
                LEFT JOIN contacts c_sender ON m.sender_address = c_sender.email
                WHERE m.id = ?
                """,
                (message_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_threads(
        self, label_id: str, limit: int = 50, offset: int = 0
    ) -> List[dict]:
        """Returns the latest message for each thread in a label, including message counts."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                WITH LatestMessages AS (
                    SELECT 
                        m.*,
                        COALESCE(NULLIF(c.name, ''), m.sender) as sender_display,
                        ROW_NUMBER() OVER (PARTITION BY m.thread_id ORDER BY m.timestamp DESC) as rank
                    FROM messages m
                    JOIN message_labels ml ON m.id = ml.message_id
                    LEFT JOIN contacts c ON m.sender_address = c.email
                    WHERE ml.label_id = ?
                ),
                ThreadCounts AS (
                    SELECT thread_id, COUNT(*) as thread_count
                    FROM messages
                    GROUP BY thread_id
                )
                SELECT lm.*, tc.thread_count
                FROM LatestMessages lm
                JOIN ThreadCounts tc ON lm.thread_id = tc.thread_id
                WHERE lm.rank = 1
                ORDER BY lm.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (label_id, limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_thread_messages(self, thread_id: str) -> List[dict]:
        """Retrieves all messages for a specific conversation, ordered by recency (latest first)."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT m.*, c_sender.name as sender_name
                FROM messages m
                LEFT JOIN contacts c_sender ON m.sender_address = c_sender.email
                WHERE m.thread_id = ?
                ORDER BY m.timestamp DESC
                """,
                (thread_id,),
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
        """Returns labels along with their unread message counts."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT l.id, l.name, l.type, COUNT(m.id) as unread_count
                FROM labels l
                LEFT JOIN message_labels ml ON l.id = ml.label_id
                LEFT JOIN messages m ON ml.message_id = m.id AND m.is_read = 0
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

    def upsert_message(self, conn: sqlite3.Connection, message: "Message"):
        """Inserts or updates a message record in the database."""
        conn.execute(
            """
            INSERT OR REPLACE INTO messages
            (id, thread_id, subject, sender, sender_address, recipient_to, recipient_to_addresses, recipient_cc, recipient_cc_addresses, recipient_bcc, recipient_bcc_addresses, snippet, body, timestamp, is_read, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.thread_id,
                message.subject,
                message.sender,
                message.sender_address,
                message.recipient_to,
                message.recipient_to_addresses,
                message.recipient_cc,
                message.recipient_cc_addresses,
                message.recipient_bcc,
                message.recipient_bcc_addresses,
                message.snippet,
                message.body,
                message.timestamp.isoformat(),
                int(message.is_read),
                int(message.has_attachments),
            ),
        )

        for label in message.labels:
            conn.execute(
                "INSERT OR IGNORE INTO labels (id, name, type) VALUES (?, ?, ?)",
                (label.id, label.name, label.type),
            )
            conn.execute(
                "INSERT OR IGNORE INTO message_labels (message_id, label_id) VALUES (?, ?)",
                (message.id, label.id),
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
        message_id: str,
        added_label_ids: List[str],
        removed_label_ids: List[str],
    ):
        """Updates the association between a message and its labels."""
        added = added_label_ids or []
        removed = removed_label_ids or []

        if removed:
            placeholders = ", ".join(["?"] * len(removed))
            delete_sql = f"DELETE FROM message_labels WHERE message_id = ? AND label_id IN ({placeholders})"
            conn.execute(delete_sql, [message_id] + removed)

        if added:
            insert_sql = "INSERT OR IGNORE INTO message_labels (message_id, label_id) VALUES (?, ?)"
            insert_params = [(message_id, label_id) for label_id in added]
            conn.executemany(insert_sql, insert_params)

    def remove_message(self, conn: sqlite3.Connection, message_id: str):
        """Deletes a message and its label associations from the database."""
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    def upsert_label(
        self, conn: sqlite3.Connection, label_id: str, label_name: str, label_type: str
    ):
        """Inserts or updates a label entry."""
        conn.execute(
            "INSERT OR REPLACE INTO labels (id, name, type) VALUES (?, ?, ?)",
            (label_id, label_name, label_type),
        )


db = DatabaseService()

import contextlib
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Generator, List, Optional

if TYPE_CHECKING:
    from shmail.models import Email

from shmail.config import CONFIG_DIR

DB_PATH = CONFIG_DIR / "shmail.db"


class DatabaseService:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    # --- CORE & LIFECYCLE ---
    # Methods for managing the database connection and schema.

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        # Provides a safe way to connect to the database.
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        # Manages a single database transaction, ensuring atomicity.
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def initialize(self):
        # Creates the tables if they don't exist.
        with self.get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")

            # 1. The main email data
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT,
                    subject TEXT,
                    sender TEXT,
                    recipient_to TEXT,
                    recipient_cc TEXT,
                    recipient_bcc TEXT,
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

            # 3. The mapping between them
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

            # 5. Contacts for autocomplete
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    email TEXT PRIMARY KEY,
                    name TEXT,
                    interaction_count INTEGER DEFAULT 1,
                    last_interaction DATETIME
                )
            """)
            conn.commit()

    # --- READ METHODS ---
    # These methods handle their own connections.

    def get_metadata(self, key: str) -> Optional[str]:
        # Retrieves a metadata value by key.
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def get_labels(self) -> List[dict]:
        # Returns all labels from the DB.
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, name, type FROM labels ORDER BY type ASC, name ASC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_top_contacts(self, limit: int = 50) -> List[dict]:
        # Returns contacts ranked by interaction count and recency.
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT email, name, interaction_count, last_interaction FROM contacts ORDER BY interaction_count DESC, last_interaction DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # --- WRITE METHODS ---
    # These methods REQUIRE an active sqlite3.Connection object.

    def set_metadata(self, conn: sqlite3.Connection, key: str, value: str):
        # Sets metadata using an existing connection.
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value),
        )

    def upsert_email(self, conn: sqlite3.Connection, email: "Email"):
        # Saves or updates an email and its label associations.
        conn.execute(
            """
            INSERT OR REPLACE INTO emails
            (id, thread_id, subject, sender, recipient_to, recipient_cc, recipient_bcc, snippet, body, timestamp, is_read, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email.id,
                email.thread_id,
                email.subject,
                email.sender,
                email.recipient_to,
                email.recipient_cc,
                email.recipient_bcc,
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
        # Insert or update a contact, incrementing interaction count.
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
        # Updates label associations using an existing connection.
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
        # Removes an email using an existing connection.
        conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))

    def upsert_label(
        self, conn: sqlite3.Connection, label_id: str, label_name: str, label_type: str
    ):
        # Saves or updates a label definition.
        conn.execute(
            "INSERT OR REPLACE INTO labels (id, name, type) VALUES (?, ?, ?)",
            (label_id, label_name, label_type),
        )


# Global instance
db = DatabaseService()

"""SQLite persistence layer for messages, labels, and sync metadata."""

import contextlib
import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Generator, List, Optional

if TYPE_CHECKING:
    from shmail.models import Message, MessageDraft

from shmail.config import CONFIG_DIR
from shmail.services.time import to_timestamp

DB_PATH = CONFIG_DIR / "shmail.db"

logger = logging.getLogger(__name__)


class DatabaseRepository:
    """Provide local SQLite persistence for messages, labels, and contacts."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    @contextlib.contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a database connection configured for this application."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a transactional connection and commit or roll back on exit."""
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                logger.exception("Database transaction failed")
                raise

    def initialize(self):
        """Create database schema objects when they do not exist."""
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
                        body_links TEXT,
                        body_source TEXT,
                        body_content_type TEXT,
                        body_charset TEXT,
                        body_link_count INTEGER DEFAULT 0,
                        body_conversion_warnings TEXT,
                        timestamp DATETIME,
                        is_read BOOLEAN DEFAULT 0,
                        has_attachments BOOLEAN DEFAULT 0
                    )
                """)

                self._ensure_message_schema(conn)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS labels (
                        id TEXT PRIMARY KEY,
                        name TEXT UNIQUE,
                        type TEXT,
                        label_list_visibility TEXT,
                        message_list_visibility TEXT,
                        background_color TEXT,
                        text_color TEXT
                    )
                """)

                self._ensure_label_schema(conn)

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

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS message_drafts (
                        id TEXT PRIMARY KEY,
                        mode TEXT NOT NULL,
                        to_addresses TEXT,
                        cc_addresses TEXT,
                        bcc_addresses TEXT,
                        subject TEXT,
                        body TEXT,
                        source_message_id TEXT,
                        source_thread_id TEXT,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )

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

    def _ensure_message_schema(self, conn: sqlite3.Connection) -> None:
        """Apply additive schema updates required by the current message model."""
        rows = conn.execute("PRAGMA table_info(messages)").fetchall()
        existing_columns = {row["name"] for row in rows}
        required_columns = {
            "body_links": "TEXT",
            "body_source": "TEXT",
            "body_content_type": "TEXT",
            "body_charset": "TEXT",
            "body_link_count": "INTEGER DEFAULT 0",
            "body_conversion_warnings": "TEXT",
        }

        for column, definition in required_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {column} {definition}")

    def _ensure_label_schema(self, conn: sqlite3.Connection) -> None:
        """Apply additive schema updates required by the current label model."""
        rows = conn.execute("PRAGMA table_info(labels)").fetchall()
        existing_columns = {row["name"] for row in rows}
        required_columns = {
            "label_list_visibility": "TEXT",
            "message_list_visibility": "TEXT",
            "background_color": "TEXT",
            "text_color": "TEXT",
        }

        for column, definition in required_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE labels ADD COLUMN {column} {definition}")

    def get_metadata(self, key: str) -> Optional[str]:
        """Return a metadata value for the provided key."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def get_message_draft(self, draft_id: str) -> Optional[dict]:
        """Return one message draft row by draft identifier."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM message_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_message_draft_by_source(
        self,
        mode: str,
        source_message_id: Optional[str],
        source_thread_id: Optional[str],
    ) -> Optional[dict]:
        """Return latest draft row for a specific seed source context."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM message_drafts
                WHERE mode = ?
                  AND (
                    source_message_id = ?
                    OR (source_message_id IS NULL AND ? IS NULL)
                  )
                  AND (
                    source_thread_id = ?
                    OR (source_thread_id IS NULL AND ? IS NULL)
                  )
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (
                    mode,
                    source_message_id,
                    source_message_id,
                    source_thread_id,
                    source_thread_id,
                ),
            ).fetchone()
            return dict(row) if row else None

    def list_message_drafts(self) -> List[dict]:
        """Return all persisted message drafts sorted by update time."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM message_drafts ORDER BY updated_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_message(self, message_id: str) -> Optional[dict]:
        """Return one message by ID joined with sender contact name."""
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
        """Return latest thread messages for a label with thread counts."""
        if label_id.upper() == "DRAFT":
            return self._get_draft_threads(limit=limit, offset=offset)

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
                ),
                DraftCounts AS (
                    SELECT source_thread_id AS thread_id, COUNT(*) AS draft_count
                    FROM message_drafts
                    WHERE source_thread_id IS NOT NULL
                    GROUP BY source_thread_id
                )
                SELECT
                    lm.*,
                    tc.thread_count,
                    COALESCE(dc.draft_count, 0) AS draft_count,
                    CASE WHEN COALESCE(dc.draft_count, 0) > 0 THEN 1 ELSE 0 END AS has_draft,
                    0 AS is_draft,
                    NULL AS draft_id
                FROM LatestMessages lm
                JOIN ThreadCounts tc ON lm.thread_id = tc.thread_id
                LEFT JOIN DraftCounts dc ON lm.thread_id = dc.thread_id
                WHERE lm.rank = 1
                ORDER BY lm.timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (label_id, limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]

    def count_messages(self) -> int:
        """Return the total number of persisted messages."""
        with self.get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM messages").fetchone()
            return int(row["total"]) if row is not None else 0

    def reset_message_cache(self, conn: sqlite3.Connection) -> None:
        """Delete all cached provider messages while preserving local drafts."""
        conn.execute("DELETE FROM messages")

    def _get_draft_threads(self, limit: int = 50, offset: int = 0) -> List[dict]:
        """Return thread rows derived from local message drafts."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                WITH DraftResolved AS (
                    SELECT
                        id AS draft_id,
                        COALESCE(source_thread_id, 'draft:' || id) AS resolved_thread_id,
                        mode,
                        to_addresses,
                        cc_addresses,
                        bcc_addresses,
                        subject,
                        body,
                        created_at,
                        updated_at
                    FROM message_drafts
                ),
                DraftLatest AS (
                    SELECT
                        dr.*,
                        ROW_NUMBER() OVER (PARTITION BY resolved_thread_id ORDER BY updated_at DESC) AS rank
                    FROM DraftResolved dr
                ),
                DraftCounts AS (
                    SELECT resolved_thread_id, COUNT(*) AS draft_count
                    FROM DraftResolved
                    GROUP BY resolved_thread_id
                ),
                MessageThreadCounts AS (
                    SELECT thread_id, COUNT(*) AS message_count
                    FROM messages
                    GROUP BY thread_id
                )
                SELECT
                    dl.resolved_thread_id AS thread_id,
                    COALESCE(NULLIF(dl.subject, ''), '(Draft)') AS subject,
                    'You' AS sender,
                    '' AS sender_address,
                    'You' AS sender_display,
                    dl.to_addresses AS recipient_to,
                    dl.to_addresses AS recipient_to_addresses,
                    dl.cc_addresses AS recipient_cc,
                    dl.cc_addresses AS recipient_cc_addresses,
                    dl.bcc_addresses AS recipient_bcc,
                    dl.bcc_addresses AS recipient_bcc_addresses,
                    SUBSTR(REPLACE(COALESCE(dl.body, ''), CHAR(10), ' '), 1, 120) AS snippet,
                    dl.body AS body,
                    dl.updated_at AS timestamp,
                    1 AS is_read,
                    0 AS has_attachments,
                    COALESCE(mtc.message_count, 0) + dc.draft_count AS thread_count,
                    dc.draft_count AS draft_count,
                    1 AS has_draft,
                    1 AS is_draft,
                    dl.draft_id AS draft_id
                FROM DraftLatest dl
                JOIN DraftCounts dc ON dl.resolved_thread_id = dc.resolved_thread_id
                LEFT JOIN MessageThreadCounts mtc ON dl.resolved_thread_id = mtc.thread_id
                WHERE dl.rank = 1
                ORDER BY dl.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_thread_messages(self, thread_id: str) -> List[dict]:
        """Return all messages for a thread ordered by most recent first."""
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
            messages = [dict(row) for row in cursor.fetchall()]

            draft_rows = conn.execute(
                """
                SELECT *
                FROM message_drafts
                WHERE COALESCE(source_thread_id, 'draft:' || id) = ?
                ORDER BY updated_at DESC
                """,
                (thread_id,),
            ).fetchall()

            anchored_drafts: dict[str, list[dict]] = {}
            unanchored_drafts: list[dict] = []
            for row in draft_rows:
                draft = dict(row)
                draft_message = {
                    "id": f"draft:{draft['id']}",
                    "thread_id": thread_id,
                    "subject": draft.get("subject") or "(Draft)",
                    "sender": "You (Draft)",
                    "sender_name": "You",
                    "sender_address": "",
                    "recipient_to": draft.get("to_addresses") or "",
                    "recipient_to_addresses": draft.get("to_addresses") or "",
                    "recipient_cc": draft.get("cc_addresses") or "",
                    "recipient_cc_addresses": draft.get("cc_addresses") or "",
                    "recipient_bcc": draft.get("bcc_addresses") or "",
                    "recipient_bcc_addresses": draft.get("bcc_addresses") or "",
                    "snippet": (draft.get("body") or "").splitlines()[0]
                    if draft.get("body")
                    else "",
                    "body": draft.get("body") or "",
                    "body_links": "[]",
                    "body_source": "draft",
                    "body_content_type": "text/plain",
                    "body_charset": "utf-8",
                    "body_link_count": 0,
                    "body_conversion_warnings": "[]",
                    "timestamp": draft.get("updated_at"),
                    "is_read": 1,
                    "has_attachments": 0,
                    "is_draft": 1,
                    "draft_id": draft.get("id"),
                    "source_message_id": draft.get("source_message_id"),
                }
                source_message_id = str(draft.get("source_message_id") or "").strip()
                if source_message_id:
                    anchored_drafts.setdefault(source_message_id, []).append(
                        draft_message
                    )
                else:
                    unanchored_drafts.append(draft_message)

            for draft_list in anchored_drafts.values():
                draft_list.sort(
                    key=lambda item: self._parse_timestamp(item.get("timestamp")),
                    reverse=True,
                )

            unanchored_drafts.sort(
                key=lambda item: self._parse_timestamp(item.get("timestamp")),
                reverse=True,
            )

            ordered_messages: list[dict] = [*unanchored_drafts]
            for message in messages:
                ordered_messages.extend(
                    anchored_drafts.get(str(message.get("id") or ""), [])
                )
                ordered_messages.append(message)

            return ordered_messages

    @staticmethod
    def _parse_timestamp(raw: object) -> float:
        """Parse message-like timestamp values for deterministic ordering."""
        if raw is None or not str(raw).strip():
            return 0.0
        return to_timestamp(raw)

    def get_labels(self) -> List[dict]:
        """Return all labels from local storage."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    id,
                    name,
                    type,
                    label_list_visibility,
                    message_list_visibility,
                    background_color,
                    text_color
                FROM labels
                ORDER BY type ASC, name ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_label(self, label_id: str) -> Optional[dict]:
        """Return one label row by identifier."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    id,
                    name,
                    type,
                    label_list_visibility,
                    message_list_visibility,
                    background_color,
                    text_color
                FROM labels
                WHERE id = ?
                """,
                (label_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_labels_with_counts(self) -> List[dict]:
        """Return labels with unread message counts."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                WITH DraftTotal AS (
                    SELECT COUNT(*) AS total_drafts FROM message_drafts
                )
                SELECT
                    l.id,
                    l.name,
                    l.type,
                    l.label_list_visibility,
                    l.message_list_visibility,
                    l.background_color,
                    l.text_color,
                    CASE
                        WHEN UPPER(l.id) = 'DRAFT' OR UPPER(l.name) LIKE 'DRAFT%' THEN (SELECT total_drafts FROM DraftTotal)
                        ELSE COUNT(m.id)
                    END as unread_count
                FROM labels l
                LEFT JOIN message_labels ml ON l.id = ml.label_id
                LEFT JOIN messages m ON ml.message_id = m.id AND m.is_read = 0
                GROUP BY l.id
                ORDER BY l.type ASC, l.name ASC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_total_local_draft_count(self) -> int:
        """Return total count of locally persisted draft messages."""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM message_drafts"
            ).fetchone()
            return int(row["total"]) if row is not None else 0

    def get_thread_draft_count(self, thread_id: str) -> int:
        """Return count of drafts associated with the provided thread id."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM message_drafts
                WHERE COALESCE(source_thread_id, 'draft:' || id) = ?
                """,
                (thread_id,),
            ).fetchone()
            return int(row["total"]) if row is not None else 0

    def get_top_contacts(self, limit: int = 50) -> List[dict]:
        """Return most frequently contacted addresses by interaction volume."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT email, name, interaction_count, last_interaction FROM contacts ORDER BY interaction_count DESC, last_interaction DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def set_metadata(self, conn: sqlite3.Connection, key: str, value: str):
        """Persist a metadata key-value pair."""
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value),
        )

    def upsert_message(self, conn: sqlite3.Connection, message: "Message") -> None:
        """Insert or update one message record."""
        conn.execute(
            """
            INSERT OR REPLACE INTO messages
            (id, thread_id, subject, sender, sender_address, recipient_to, recipient_to_addresses, recipient_cc, recipient_cc_addresses, recipient_bcc, recipient_bcc_addresses, snippet, body, body_links, body_source, body_content_type, body_charset, body_link_count, body_conversion_warnings, timestamp, is_read, has_attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                message.body_links,
                message.body_source,
                message.body_content_type,
                message.body_charset,
                message.body_link_count,
                message.body_conversion_warnings,
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

    def upsert_message_draft(
        self, conn: sqlite3.Connection, draft: "MessageDraft"
    ) -> None:
        """Insert or update one message draft record."""
        conn.execute(
            """
            INSERT OR REPLACE INTO message_drafts
            (id, mode, to_addresses, cc_addresses, bcc_addresses, subject, body, source_message_id, source_thread_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.id,
                draft.mode,
                draft.to_addresses,
                draft.cc_addresses,
                draft.bcc_addresses,
                draft.subject,
                draft.body,
                draft.source_message_id,
                draft.source_thread_id,
                draft.created_at.isoformat(),
                draft.updated_at.isoformat(),
            ),
        )

    def upsert_contact(
        self, conn: sqlite3.Connection, email: str, name: Optional[str], timestamp: str
    ) -> None:
        """Insert or update a contact entry and increment interaction count."""
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
    ) -> None:
        """Update label associations for a message."""
        added = added_label_ids or []
        removed = removed_label_ids or []

        if removed:
            placeholders = ", ".join(["?"] * len(removed))
            delete_sql = f"DELETE FROM message_labels WHERE message_id = ? AND label_id IN ({placeholders})"
            conn.execute(delete_sql, [message_id] + removed)

        if added:
            for label_id in added:
                conn.execute(
                    "INSERT OR IGNORE INTO labels (id, name, type) VALUES (?, ?, ?)",
                    (label_id, label_id, "unknown"),
                )
            insert_sql = "INSERT OR IGNORE INTO message_labels (message_id, label_id) VALUES (?, ?)"
            insert_params = [(message_id, label_id) for label_id in added]
            conn.executemany(insert_sql, insert_params)

    def remove_message(self, conn: sqlite3.Connection, message_id: str) -> None:
        """Delete a message row (and cascading associations)."""
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    def remove_message_draft(self, conn: sqlite3.Connection, draft_id: str) -> None:
        """Delete a message draft by identifier."""
        conn.execute("DELETE FROM message_drafts WHERE id = ?", (draft_id,))

    def upsert_label(
        self,
        conn: sqlite3.Connection,
        label_id: str,
        label_name: str,
        label_type: str,
        *,
        label_list_visibility: str | None = None,
        message_list_visibility: str | None = None,
        background_color: str | None = None,
        text_color: str | None = None,
    ) -> None:
        """Insert or update a label entry."""
        conn.execute(
            """
            INSERT OR REPLACE INTO labels (
                id,
                name,
                type,
                label_list_visibility,
                message_list_visibility,
                background_color,
                text_color
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                label_id,
                label_name,
                label_type,
                label_list_visibility,
                message_list_visibility,
                background_color,
                text_color,
            ),
        )

    def delete_label(self, conn: sqlite3.Connection, label_id: str) -> None:
        """Delete one label entry by identifier."""
        conn.execute("DELETE FROM labels WHERE id = ?", (label_id,))

    def prune_labels(
        self, conn: sqlite3.Connection, valid_label_ids: List[str]
    ) -> None:
        """Remove labels that no longer exist in the provider label set."""
        if valid_label_ids:
            placeholders = ", ".join(["?"] * len(valid_label_ids))
            conn.execute(
                f"DELETE FROM labels WHERE id NOT IN ({placeholders})", valid_label_ids
            )
        else:
            conn.execute("DELETE FROM labels")


db = DatabaseRepository()

"""Read-model service for main thread list data."""

from __future__ import annotations

from shmail.services.db import DatabaseRepository, db


class ThreadQueryService:
    """Provide thread-list-oriented read operations."""

    def __init__(self, repository: DatabaseRepository | None = None) -> None:
        self.repository = repository or db

    def list_threads(
        self, label_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """Return thread rows for one label."""
        threads = self.repository.get_threads(
            label_id=label_id, limit=limit, offset=offset
        )
        for thread in threads:
            thread_id = str(thread.get("thread_id") or "")
            thread["thread_labels"] = self.repository.list_thread_labels(thread_id)
        return threads

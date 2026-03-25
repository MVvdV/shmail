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
        return self.repository.get_threads(
            label_id=label_id, limit=limit, offset=offset
        )

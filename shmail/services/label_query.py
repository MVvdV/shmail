"""Read-model service for sidebar label data."""

from __future__ import annotations

from shmail.services.db import DatabaseRepository, db


class LabelQueryService:
    """Provide label/sidebar-oriented read operations."""

    def __init__(self, repository: DatabaseRepository | None = None) -> None:
        self.repository = repository or db

    def list_labels_with_counts(self) -> list[dict]:
        """Return labels shaped for sidebar rendering."""
        return self.repository.get_labels_with_counts()

"""Shared label-state authority for full refreshes and targeted patches."""

from __future__ import annotations

from shmail.services.label_query import LabelQueryService


class LabelStateService:
    """Own the current sidebar label state and targeted label patches."""

    def __init__(self, query_service: LabelQueryService) -> None:
        self.query_service = query_service
        self._labels: list[dict] = []

    def refresh(self) -> list[dict]:
        """Reload labels from the query service and replace cached state."""
        self._labels = [
            dict(label) for label in self.query_service.list_labels_with_counts()
        ]
        return self.list_labels()

    def list_labels(self) -> list[dict]:
        """Return a copy of the current cached label state."""
        return [dict(label) for label in self._labels]

    def patch_label(self, label_id: str, **changes: object) -> dict | None:
        """Apply one targeted patch to a cached label row and return it."""
        normalized_id = label_id.strip().upper()
        for label in self._labels:
            current_id = str(label.get("id") or "").strip().upper()
            current_name = str(label.get("name") or "").strip().upper()
            if current_id == normalized_id or current_name == normalized_id:
                label.update(changes)
                return dict(label)
        return None

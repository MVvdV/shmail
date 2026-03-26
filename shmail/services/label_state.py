"""Shared label-state authority for full refreshes and label mutations."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from shmail.services.db import DatabaseRepository
from shmail.services.label_query import LabelQueryService


@dataclass
class LabelMutationResult:
    """Describe the outcome of one label-management operation."""

    action: str
    label_id: str | None
    focus_label_id: str | None


class LabelStateService:
    """Own the current sidebar label state and targeted label mutations."""

    def __init__(self, query_service: LabelQueryService) -> None:
        self.query_service = query_service
        self.repository: DatabaseRepository = query_service.repository
        self._labels: list[dict] = []

    def refresh(self) -> list[dict]:
        """Reload labels from the query service and replace cached state."""
        self._labels = [
            dict(label) for label in self.query_service.list_labels_with_counts()
        ]
        return [dict(label) for label in self._labels]

    def list_labels(self) -> list[dict]:
        """Return a copy of the current cached label state."""
        if not self._labels:
            self.refresh()
        return [dict(label) for label in self._labels]

    def list_user_labels(self) -> list[dict]:
        """Return cached user labels sorted by full name."""
        return sorted(
            [label for label in self.list_labels() if str(label.get("type")) == "user"],
            key=lambda label: str(label.get("name") or "").lower(),
        )

    def get_label(self, label_id: str) -> dict | None:
        """Return one label from the repository by identifier."""
        row = self.repository.get_label(label_id)
        return dict(row) if row is not None else None

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

    def can_edit_label(self, label_id: str) -> bool:
        """Return True when the given label is a mutable user label."""
        label = self.get_label(label_id)
        if label is None:
            return False
        return str(label.get("type") or "").lower() == "user"

    def parent_label_id_for(self, label_id: str) -> str | None:
        """Return the parent label identifier for one nested user label."""
        label = self.get_label(label_id)
        if label is None:
            return None
        name = str(label.get("name") or "")
        if "/" not in name:
            return None
        parent_name = name.rsplit("/", 1)[0]
        for candidate in self.list_user_labels():
            if str(candidate.get("name") or "") == parent_name:
                return str(candidate.get("id") or "") or None
        return None

    def list_parent_candidates(self, label_id: str | None = None) -> list[dict]:
        """Return allowed parent labels for create/edit nesting."""
        candidates = self.list_user_labels()
        if not label_id:
            return candidates

        current = self.get_label(label_id)
        if current is None:
            return candidates
        blocked_ids = {str(current.get("id") or "")}
        blocked_ids.update(
            str(label.get("id") or "") for label in self.list_descendants(label_id)
        )
        return [
            candidate
            for candidate in candidates
            if str(candidate.get("id") or "") not in blocked_ids
        ]

    def list_descendants(self, label_id: str) -> list[dict]:
        """Return user labels nested beneath the given label."""
        current = self.get_label(label_id)
        if current is None:
            return []
        prefix = f"{str(current.get('name') or '')}/"
        descendants = [
            label
            for label in self.list_user_labels()
            if str(label.get("name") or "").startswith(prefix)
        ]
        return sorted(descendants, key=lambda label: str(label.get("name") or ""))

    def create_label(
        self,
        *,
        leaf_name: str,
        parent_label_id: str | None,
        background_color: str | None,
        text_color: str | None,
        gmail_service=None,
    ) -> LabelMutationResult:
        """Create one new user label locally and optionally in Gmail."""
        normalized_name = self._normalize_leaf_name(leaf_name)
        full_name = self._compose_full_name(normalized_name, parent_label_id)
        self._ensure_unique_name(full_name)
        color = self._normalize_color(background_color, text_color)

        provider_label = None
        if gmail_service is not None:
            provider_label = gmail_service.create_label(
                self._build_provider_body(full_name, color)
            )

        label_id = str((provider_label or {}).get("id") or f"local:{uuid4().hex}")
        label_row = self._merge_provider_label(
            {
                "id": label_id,
                "name": full_name,
                "type": "user",
                "labelListVisibility": None,
                "messageListVisibility": None,
                "color": None,
            },
            provider_label,
            color_override=color,
        )
        with self.repository.transaction() as conn:
            self.repository.upsert_label(conn, **label_row)
        self.refresh()
        return LabelMutationResult("created", label_id, label_id)

    def update_label(
        self,
        *,
        label_id: str,
        leaf_name: str,
        parent_label_id: str | None,
        background_color: str | None,
        text_color: str | None,
        gmail_service=None,
    ) -> LabelMutationResult:
        """Update one user label and keep nested descendants coherent."""
        current = self._require_user_label(label_id)
        normalized_name = self._normalize_leaf_name(leaf_name)
        next_full_name = self._compose_full_name(normalized_name, parent_label_id)
        previous_full_name = str(current.get("name") or "")
        self._ensure_unique_name(next_full_name, exclude_label_id=label_id)
        color = self._normalize_color(background_color, text_color)

        descendants = self.list_descendants(label_id)
        with self.repository.transaction() as conn:
            updated_label = self._patch_provider_label(
                gmail_service,
                current,
                name=next_full_name,
                color=color,
            )
            self.repository.upsert_label(conn, **updated_label)

            if previous_full_name != next_full_name and descendants:
                for descendant in descendants:
                    descendant_name = str(descendant.get("name") or "")
                    suffix = descendant_name.removeprefix(previous_full_name)
                    renamed = f"{next_full_name}{suffix}"
                    descendant_color: dict[str, str] | None = None
                    if descendant.get("background_color") and descendant.get(
                        "text_color"
                    ):
                        descendant_color = {
                            "backgroundColor": str(
                                descendant.get("background_color") or ""
                            ),
                            "textColor": str(descendant.get("text_color") or ""),
                        }
                    patched_descendant = self._patch_provider_label(
                        gmail_service,
                        descendant,
                        name=renamed,
                        color=descendant_color,
                    )
                    self.repository.upsert_label(conn, **patched_descendant)

        self.refresh()
        return LabelMutationResult("updated", label_id, label_id)

    def delete_label(self, *, label_id: str, gmail_service=None) -> LabelMutationResult:
        """Delete one user label when it has no nested descendants."""
        label = self._require_user_label(label_id)
        descendants = self.list_descendants(label_id)
        if descendants:
            raise ValueError("Delete sublabels first before removing this label.")

        focus_label_id = self.parent_label_id_for(label_id)
        if gmail_service is not None:
            gmail_service.delete_label(label_id)

        with self.repository.transaction() as conn:
            self.repository.delete_label(conn, label_id)
        self.refresh()
        return LabelMutationResult("deleted", label_id, focus_label_id)

    def _require_user_label(self, label_id: str) -> dict:
        """Return one user label or raise a validation error."""
        label = self.get_label(label_id)
        if label is None:
            raise ValueError("Label not found.")
        if str(label.get("type") or "").lower() != "user":
            raise ValueError("System labels cannot be modified.")
        return label

    def _normalize_leaf_name(self, leaf_name: str) -> str:
        """Normalize one editable leaf name and reject unsupported forms."""
        normalized = " ".join(leaf_name.strip().split())
        if not normalized:
            raise ValueError("Label name is required.")
        if "/" in normalized:
            raise ValueError("Label name cannot contain '/'. Use the parent field.")
        return normalized

    def _compose_full_name(self, leaf_name: str, parent_label_id: str | None) -> str:
        """Build the provider-facing slash name from one leaf and parent."""
        if not parent_label_id:
            return leaf_name
        parent = self.get_label(parent_label_id)
        if parent is None or str(parent.get("type") or "").lower() != "user":
            raise ValueError("Parent label must be an existing user label.")
        return f"{str(parent.get('name') or '')}/{leaf_name}"

    def _ensure_unique_name(
        self, full_name: str, exclude_label_id: str | None = None
    ) -> None:
        """Reject duplicate user-label names ignoring case."""
        target = full_name.casefold()
        for label in self.list_user_labels():
            current_id = str(label.get("id") or "")
            if exclude_label_id and current_id == exclude_label_id:
                continue
            if str(label.get("name") or "").casefold() == target:
                raise ValueError("A label with that path already exists.")

    @staticmethod
    def _normalize_color(
        background_color: str | None, text_color: str | None
    ) -> dict[str, str] | None:
        """Return one normalized Gmail color payload or None."""
        background = str(background_color or "").strip() or None
        text = str(text_color or "").strip() or None
        if background is None and text is None:
            return None
        if background is None or text is None:
            raise ValueError("Choose both background and text colors.")
        return {"backgroundColor": background, "textColor": text}

    @staticmethod
    def _build_provider_body(
        full_name: str, color: dict[str, str] | None
    ) -> dict[str, object]:
        """Build one provider create payload for a user label."""
        body: dict[str, object] = {
            "name": full_name,
            "labelListVisibility": "labelShow",
        }
        if color is not None:
            body["color"] = color
        return body

    def _patch_provider_label(
        self,
        gmail_service,
        label: dict,
        *,
        name: str,
        color: dict[str, str] | None,
    ) -> dict:
        """Patch one provider label when available and return local row shape."""
        if gmail_service is None:
            return {
                "label_id": str(label.get("id") or ""),
                "label_name": name,
                "label_type": str(label.get("type") or "user"),
                "label_list_visibility": label.get("label_list_visibility"),
                "message_list_visibility": label.get("message_list_visibility"),
                "background_color": (color or {}).get("backgroundColor"),
                "text_color": (color or {}).get("textColor"),
            }

        body: dict[str, object] = {"name": name}
        if color is None:
            body["color"] = None
        else:
            body["color"] = color
        provider_label = gmail_service.patch_label(str(label.get("id") or ""), body)
        return self._merge_provider_label(label, provider_label, color_override=color)

    @staticmethod
    def _resolve_merged_color(
        merged: dict,
        provider_label: dict | None,
        color_override: dict[str, str] | None,
    ) -> tuple[str | None, str | None]:
        """Resolve the stored color fields after one provider merge."""
        if provider_label is not None:
            provider_color = provider_label.get("color")
            if provider_color is None:
                return None, None
            return (
                provider_color.get("backgroundColor"),
                provider_color.get("textColor"),
            )

        if color_override is None:
            return None, None

        return color_override.get("backgroundColor"), color_override.get("textColor")

    @staticmethod
    def _merge_provider_label(
        current: dict,
        provider_label: dict | None,
        *,
        color_override: dict[str, str] | None,
    ) -> dict:
        """Merge one provider label response into repository upsert arguments."""
        merged = dict(current)
        if provider_label:
            merged.update(provider_label)
        background_color, text_color = LabelStateService._resolve_merged_color(
            merged, provider_label, color_override
        )
        return {
            "label_id": str(merged.get("id") or ""),
            "label_name": str(merged.get("name") or ""),
            "label_type": str(merged.get("type") or "user"),
            "label_list_visibility": merged.get("labelListVisibility")
            or merged.get("label_list_visibility"),
            "message_list_visibility": merged.get("messageListVisibility")
            or merged.get("message_list_visibility"),
            "background_color": background_color,
            "text_color": text_color,
        }

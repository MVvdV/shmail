"""Provider-agnostic local-first message and thread mutation service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from shmail.services.db import DatabaseRepository, db
from shmail.services.time import now_utc

MUTABLE_MAILBOX_MARKERS = {"INBOX", "UNREAD", "STARRED", "IMPORTANT", "SPAM"}
MOVE_DESTINATION_SYSTEM_LABELS = {"INBOX"}
NON_LABEL_MOVE_DESTINATIONS = {"DRAFT", "OUTBOX", "SENT", "TRASH", "SPAM"}


@dataclass
class MutationApplyResult:
    """Summarize one local mutation application for UI refresh behavior."""

    target_kind: str
    target_id: str
    current_view_label_id: str | None
    affected_thread_ids: list[str]
    thread_became_empty: bool = False


class MessageMutationService:
    """Apply provider-agnostic local mutations and append replay intents."""

    def __init__(self, repository: DatabaseRepository | None = None) -> None:
        self.repository = repository or db

    def list_mutable_label_choices(self) -> list[dict]:
        """Return labels that may be toggled through the generic label UI."""
        labels = self.repository.get_labels()
        result: list[dict] = []
        for label in labels:
            label_id = str(label.get("id") or "").upper()
            label_type = str(label.get("type") or "")
            if label_type == "user" or self._is_mutable_system_label(label_id):
                result.append(label)
        return result

    def list_move_destinations(self) -> list[dict]:
        """Return provider-agnostic move destinations for first-pass UI."""
        labels = self.repository.get_labels()
        destinations: list[dict] = []
        for label in labels:
            label_id = str(label.get("id") or "").upper()
            label_type = str(label.get("type") or "")
            if label_type == "user" or label_id in MOVE_DESTINATION_SYSTEM_LABELS:
                destinations.append(label)
        return destinations

    def sync_message_labels(
        self,
        *,
        account_id: str,
        provider_key: str,
        message_id: str,
        selected_label_ids: list[str],
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Apply one full mutable-label selection to a message."""
        current = set(self.repository.list_message_label_ids(message_id))
        mutable_ids = {
            str(item.get("id") or "") for item in self.list_mutable_label_choices()
        }
        selected = {
            label_id for label_id in selected_label_ids if label_id in mutable_ids
        }
        immutable = current - mutable_ids
        final_labels = sorted(immutable | selected)
        return self._set_message_labels(
            account_id=account_id,
            provider_key=provider_key,
            message_id=message_id,
            final_labels=final_labels,
            current_view_label_id=current_view_label_id,
            action_type="message_labels_sync",
            payload={"selected_label_ids": final_labels},
        )

    def _set_message_labels(
        self,
        *,
        account_id: str,
        provider_key: str,
        message_id: str,
        final_labels: list[str],
        current_view_label_id: str | None,
        action_type: str,
        payload: dict,
    ) -> MutationApplyResult:
        """Apply one finalized label set to a message and record intent."""
        current = set(self.repository.list_message_label_ids(message_id))
        added = sorted(set(final_labels) - current)
        removed = sorted(current - set(final_labels))

        with self.repository.transaction() as conn:
            self.repository.replace_labels(conn, message_id, final_labels)
            self.repository.set_message_read_state(
                conn, message_id, is_read=("UNREAD" not in final_labels)
            )
            self._append_mutation(
                conn,
                account_id=account_id,
                provider_key=provider_key,
                target_kind="message",
                target_id=message_id,
                action_type=action_type,
                payload={
                    **payload,
                    "selected_label_ids": final_labels,
                    "added_label_ids": added,
                    "removed_label_ids": removed,
                },
            )

        message = self.repository.get_message(message_id)
        thread_id = str(message.get("thread_id") or "") if message is not None else ""
        return MutationApplyResult(
            target_kind="message",
            target_id=message_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id] if thread_id else [],
            thread_became_empty=self._thread_hidden_in_view(
                thread_id, current_view_label_id
            ),
        )

    def sync_thread_labels(
        self,
        *,
        account_id: str,
        provider_key: str,
        thread_id: str,
        selected_label_ids: list[str],
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Apply one full mutable-label selection to all provider messages in a thread."""
        for message_id in self.repository.list_thread_message_ids(thread_id):
            self.sync_message_labels(
                account_id=account_id,
                provider_key=provider_key,
                message_id=message_id,
                selected_label_ids=selected_label_ids,
                current_view_label_id=current_view_label_id,
            )
        return MutationApplyResult(
            target_kind="thread",
            target_id=thread_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id],
            thread_became_empty=self._thread_hidden_in_view(
                thread_id, current_view_label_id
            ),
        )

    def sync_thread_labels_delta(
        self,
        *,
        account_id: str,
        provider_key: str,
        thread_id: str,
        initial_selected_label_ids: list[str],
        selected_label_ids: list[str],
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Apply thread label changes as add/remove deltas, preserving per-message differences."""
        mutable_ids = {
            str(item.get("id") or "") for item in self.list_mutable_label_choices()
        }
        initial = {
            label_id
            for label_id in initial_selected_label_ids
            if label_id in mutable_ids
        }
        selected = {
            label_id for label_id in selected_label_ids if label_id in mutable_ids
        }
        added = selected - initial
        removed = initial - selected

        for message_id in self.repository.list_thread_message_ids(thread_id):
            current = set(self.repository.list_message_label_ids(message_id))
            next_labels = (current | added) - removed
            self._set_message_labels(
                account_id=account_id,
                provider_key=provider_key,
                message_id=message_id,
                final_labels=sorted(next_labels),
                current_view_label_id=current_view_label_id,
                action_type="thread_labels_delta",
                payload={
                    "thread_id": thread_id,
                    "added_label_ids": sorted(added),
                    "removed_label_ids": sorted(removed),
                },
            )

        return MutationApplyResult(
            target_kind="thread",
            target_id=thread_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id],
            thread_became_empty=self._thread_hidden_in_view(
                thread_id, current_view_label_id
            ),
        )

    def move_message(
        self,
        *,
        account_id: str,
        provider_key: str,
        message_id: str,
        destination_label_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Move one message into a single destination container."""
        destination = str(destination_label_id or "").strip()
        current = set(self.repository.list_message_label_ids(message_id))
        next_labels = self._apply_move_policy(
            current, destination, current_view_label_id
        )
        return self._set_message_labels(
            account_id=account_id,
            provider_key=provider_key,
            message_id=message_id,
            final_labels=sorted(next_labels),
            current_view_label_id=current_view_label_id,
            action_type="message_move",
            payload={"destination_label_id": destination},
        )

    def move_thread(
        self,
        *,
        account_id: str,
        provider_key: str,
        thread_id: str,
        destination_label_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Move all provider messages in a thread into one destination container."""
        destination = str(destination_label_id or "").strip()
        message_ids = self.repository.list_thread_message_ids(thread_id)
        for message_id in message_ids:
            current = set(self.repository.list_message_label_ids(message_id))
            next_labels = self._apply_move_policy(
                current, destination, current_view_label_id
            )
            self._set_message_labels(
                account_id=account_id,
                provider_key=provider_key,
                message_id=message_id,
                final_labels=sorted(next_labels),
                current_view_label_id=current_view_label_id,
                action_type="message_move",
                payload={"destination_label_id": destination},
            )
        return MutationApplyResult(
            target_kind="thread",
            target_id=thread_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id],
            thread_became_empty=self._thread_hidden_in_view(
                thread_id, current_view_label_id
            ),
        )

    def trash_message(
        self,
        *,
        account_id: str,
        provider_key: str,
        message_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Move one message into local trash state."""
        current = set(self.repository.list_message_label_ids(message_id))
        selected = sorted((current - {"SPAM"}) | {"TRASH"})
        return self._set_message_labels(
            account_id=account_id,
            provider_key=provider_key,
            message_id=message_id,
            final_labels=selected,
            current_view_label_id=current_view_label_id,
            action_type="message_trash",
            payload={},
        )

    def trash_thread(
        self,
        *,
        account_id: str,
        provider_key: str,
        thread_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Move all provider messages in a thread into local trash state."""
        for message_id in self.repository.list_thread_message_ids(thread_id):
            self.trash_message(
                account_id=account_id,
                provider_key=provider_key,
                message_id=message_id,
                current_view_label_id=current_view_label_id,
            )
        return MutationApplyResult(
            target_kind="thread",
            target_id=thread_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id],
            thread_became_empty=self._thread_hidden_in_view(
                thread_id, current_view_label_id
            ),
        )

    def restore_message(
        self,
        *,
        account_id: str,
        provider_key: str,
        message_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Restore one trashed message back into Inbox visibility."""
        current = set(self.repository.list_message_label_ids(message_id))
        restored = sorted((current - {"TRASH", "SPAM"}) | {"INBOX"})
        return self._set_message_labels(
            account_id=account_id,
            provider_key=provider_key,
            message_id=message_id,
            final_labels=restored,
            current_view_label_id=current_view_label_id,
            action_type="message_restore",
            payload={},
        )

    def restore_thread(
        self,
        *,
        account_id: str,
        provider_key: str,
        thread_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Restore all provider messages in one trashed thread back to Inbox."""
        for message_id in self.repository.list_thread_message_ids(thread_id):
            self.restore_message(
                account_id=account_id,
                provider_key=provider_key,
                message_id=message_id,
                current_view_label_id=current_view_label_id,
            )
        return MutationApplyResult(
            target_kind="thread",
            target_id=thread_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id],
            thread_became_empty=self._thread_hidden_in_view(
                thread_id, current_view_label_id
            ),
        )

    def delete_message_forever(
        self,
        *,
        account_id: str,
        provider_key: str,
        message_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Permanently delete one provider message from the local cache."""
        message = self.repository.get_message(message_id)
        thread_id = str(message.get("thread_id") or "") if message is not None else ""
        with self.repository.transaction() as conn:
            self.repository.remove_message(conn, message_id)
            self._append_mutation(
                conn,
                account_id=account_id,
                provider_key=provider_key,
                target_kind="message",
                target_id=message_id,
                action_type="message_delete_forever",
                payload={},
            )
        return MutationApplyResult(
            target_kind="message",
            target_id=message_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id] if thread_id else [],
            thread_became_empty=self._thread_hidden_in_view(
                thread_id, current_view_label_id
            ),
        )

    def delete_thread_forever(
        self,
        *,
        account_id: str,
        provider_key: str,
        thread_id: str,
        current_view_label_id: str | None,
    ) -> MutationApplyResult:
        """Permanently delete all provider messages in one thread from local cache."""
        with self.repository.transaction() as conn:
            for message_id in self.repository.list_thread_message_ids(thread_id):
                self.repository.remove_message(conn, message_id)
            self._append_mutation(
                conn,
                account_id=account_id,
                provider_key=provider_key,
                target_kind="thread",
                target_id=thread_id,
                action_type="thread_delete_forever",
                payload={},
            )
        return MutationApplyResult(
            target_kind="thread",
            target_id=thread_id,
            current_view_label_id=current_view_label_id,
            affected_thread_ids=[thread_id],
            thread_became_empty=True,
        )

    def _thread_hidden_in_view(self, thread_id: str, label_id: str | None) -> bool:
        """Return True when a thread has no remaining visible provider messages."""
        if not thread_id:
            return False
        visible = self.repository.get_thread_messages(thread_id, label_id=label_id)
        return len(visible) == 0

    @staticmethod
    def _apply_move_policy(
        current_labels: set[str],
        destination_label_id: str,
        current_view_label_id: str | None,
    ) -> set[str]:
        """Apply first-pass destination-container semantics to one message label set."""
        destination = destination_label_id.strip()
        if not destination:
            return current_labels

        next_labels = set(current_labels)
        next_labels.add(destination)
        if destination.upper() != "INBOX":
            next_labels.discard("INBOX")

        current_view = str(current_view_label_id or "").strip().upper()
        if current_view and current_view not in NON_LABEL_MOVE_DESTINATIONS:
            next_labels = {
                label
                for label in next_labels
                if label.upper() != current_view or label == destination
            }
        next_labels.discard("SPAM")
        next_labels.discard("TRASH")
        return next_labels

    def _append_mutation(
        self,
        conn,
        *,
        account_id: str,
        provider_key: str,
        target_kind: str,
        target_id: str,
        action_type: str,
        payload: dict,
    ) -> None:
        now = now_utc().isoformat()
        self.repository.append_mutation(
            conn,
            mutation_id=str(uuid4()),
            account_id=account_id,
            provider_key=provider_key,
            target_kind=target_kind,
            target_id=target_id,
            action_type=action_type,
            payload_json=json.dumps(payload, sort_keys=True),
            state="ready_for_sync",
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _is_mutable_system_label(label_id: str) -> bool:
        """Return True when one system label should participate in add/remove label flows."""
        return label_id in MUTABLE_MAILBOX_MARKERS or label_id.startswith("CATEGORY_")

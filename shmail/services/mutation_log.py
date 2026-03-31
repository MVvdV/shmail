"""Mutation log state transitions and inspection helpers."""

from __future__ import annotations

from datetime import timedelta

from shmail.models import MutationRecord
from shmail.services.db import DatabaseRepository, db
from shmail.services.time import now_utc, parse_utc_datetime

MUTATION_PENDING_STATES = {"pending_local", "ready_for_sync", "in_flight"}
MUTATION_TERMINAL_STATES = {"acked", "failed", "blocked"}


class MutationLogService:
    """Provide one provider-neutral mutation state machine surface."""

    def __init__(self, repository: DatabaseRepository | None = None) -> None:
        self.repository = repository or db

    def list_ready_for_replay(self, limit: int = 100) -> list[MutationRecord]:
        """Return mutations that are ready for later provider replay."""
        return [
            self._row_to_model(row)
            for row in self.repository.list_mutations(
                states=["pending_local", "ready_for_sync", "failed"], limit=limit
            )
        ]

    def mark_in_flight(self, mutation_id: str) -> None:
        """Mark one mutation as claimed by a future replay worker."""
        mutation = self.get_mutation(mutation_id)
        retry_count = mutation.retry_count if mutation is not None else None
        self._update_state(
            mutation_id,
            state="in_flight",
            error_message=None,
            retry_count=retry_count,
            last_attempt_at=now_utc(),
            next_attempt_at=None,
        )

    def mark_ready(self, mutation_id: str) -> None:
        """Return one mutation to replay-ready state."""
        mutation = self.get_mutation(mutation_id)
        retry_count = mutation.retry_count if mutation is not None else None
        self._update_state(
            mutation_id,
            state="ready_for_sync",
            error_message=None,
            retry_count=retry_count,
            next_attempt_at=None,
        )

    def mark_acked(self, mutation_id: str) -> None:
        """Mark one mutation as provider-acknowledged."""
        mutation = self.get_mutation(mutation_id)
        retry_count = mutation.retry_count if mutation is not None else None
        self._update_state(
            mutation_id,
            state="acked",
            error_message=None,
            retry_count=retry_count,
            next_attempt_at=None,
        )

    def mark_failed(self, mutation_id: str, error_message: str) -> None:
        """Mark one mutation as failed with a user-visible error message."""
        mutation = self.get_mutation(mutation_id)
        retry_count = (mutation.retry_count if mutation is not None else 0) + 1
        backoff_minutes = min(60, 2 ** min(retry_count, 5))
        self._update_state(
            mutation_id,
            state="failed",
            error_message=error_message,
            retry_count=retry_count,
            next_attempt_at=now_utc() + timedelta(minutes=backoff_minutes),
        )

    def mark_blocked(self, mutation_id: str, error_message: str) -> None:
        """Mark one mutation as blocked pending manual resolution."""
        mutation = self.get_mutation(mutation_id)
        retry_count = mutation.retry_count if mutation is not None else None
        self._update_state(
            mutation_id,
            state="blocked",
            error_message=error_message,
            retry_count=retry_count,
            next_attempt_at=None,
        )

    def get_mutation(self, mutation_id: str) -> MutationRecord | None:
        """Return one mutation record by id."""
        row = self.repository.get_mutation(mutation_id)
        return self._row_to_model(row) if row is not None else None

    def retry_message_mutations(self, message_id: str) -> list[str]:
        """Return failed or blocked message mutations back to ready state."""
        ids = self.repository.list_retryable_mutation_ids_for_target(
            target_kind="message", target_id=message_id
        )
        for mutation_id in ids:
            self.mark_ready(mutation_id)
        return ids

    def retry_thread_mutations(self, thread_id: str) -> list[str]:
        """Return failed or blocked thread-associated mutations back to ready state."""
        ids = self.repository.list_retryable_mutation_ids_for_thread(thread_id)
        for mutation_id in ids:
            self.mark_ready(mutation_id)
        return ids

    def get_thread_status(self, thread_id: str) -> dict:
        """Return pending and failed replay counts for one thread."""
        return self.repository.get_thread_mutation_summary(thread_id)

    def get_message_status(self, message_id: str) -> dict:
        """Return pending and failed replay counts for one message."""
        return self.repository.get_message_mutation_summary(message_id)

    def _update_state(
        self,
        mutation_id: str,
        *,
        state: str,
        error_message: str | None,
        retry_count: int | None = None,
        last_attempt_at=None,
        next_attempt_at=None,
    ) -> None:
        """Persist one state transition in the mutation log."""
        with self.repository.transaction() as conn:
            self.repository.update_mutation_state(
                conn,
                mutation_id,
                state=state,
                error_message=error_message,
                updated_at=now_utc().isoformat(),
                retry_count=retry_count,
                last_attempt_at=(
                    last_attempt_at.isoformat() if last_attempt_at is not None else None
                ),
                next_attempt_at=(
                    next_attempt_at.isoformat() if next_attempt_at is not None else None
                ),
            )

    @staticmethod
    def _row_to_model(row: dict) -> MutationRecord:
        """Convert one database row into a typed mutation record."""
        created_at = parse_utc_datetime(row.get("created_at"))
        updated_at = parse_utc_datetime(row.get("updated_at"), default=created_at)
        last_attempt_at = (
            parse_utc_datetime(row.get("last_attempt_at"), default=updated_at)
            if row.get("last_attempt_at")
            else None
        )
        next_attempt_at = (
            parse_utc_datetime(row.get("next_attempt_at"), default=updated_at)
            if row.get("next_attempt_at")
            else None
        )
        return MutationRecord(
            id=str(row.get("id") or ""),
            account_id=str(row.get("account_id") or ""),
            provider_key=str(row.get("provider_key") or ""),
            target_kind=str(row.get("target_kind") or ""),
            target_id=str(row.get("target_id") or ""),
            action_type=str(row.get("action_type") or ""),
            payload_json=str(row.get("payload_json") or "{}"),
            state=str(row.get("state") or "pending_local"),
            error_message=(
                str(row.get("error_message"))
                if row.get("error_message") is not None
                else None
            ),
            retry_count=int(row.get("retry_count") or 0),
            last_attempt_at=last_attempt_at,
            next_attempt_at=next_attempt_at,
            created_at=created_at,
            updated_at=updated_at,
        )

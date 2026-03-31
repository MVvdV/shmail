"""Replay worker orchestration for provider-agnostic mutation execution."""

from __future__ import annotations

from shmail.services.mutation_log import MutationLogService
from shmail.services.provider_replay import ProviderReplayRegistry


class MutationReplayService:
    """Claim queued mutations, invoke provider adapters, and persist outcomes."""

    def __init__(
        self,
        mutation_log: MutationLogService,
        registry: ProviderReplayRegistry,
    ) -> None:
        self.mutation_log = mutation_log
        self.registry = registry

    def replay_ready(self, limit: int = 20) -> list[str]:
        """Attempt replay for pending/failed mutations up to the provided limit."""
        processed_ids: list[str] = []
        for mutation in self.mutation_log.list_ready_for_replay(limit=limit):
            self.mutation_log.mark_in_flight(mutation.id)
            adapter = self.registry.resolve(mutation.provider_key)
            result = adapter.replay_mutation(mutation)
            if result.state == "acked":
                self.mutation_log.mark_acked(mutation.id)
            elif result.state == "failed":
                self.mutation_log.mark_failed(
                    mutation.id, result.error_message or "Replay failed."
                )
            elif result.state == "ready_for_sync":
                self.mutation_log.mark_ready(mutation.id)
            else:
                self.mutation_log.mark_blocked(
                    mutation.id,
                    result.error_message or "Replay blocked pending provider support.",
                )
            processed_ids.append(mutation.id)
        return processed_ids

    def replay_one(self, mutation_id: str) -> bool:
        """Replay one specific mutation if it is pending or failed."""
        candidates = self.mutation_log.list_ready_for_replay(limit=500)
        target = next(
            (mutation for mutation in candidates if mutation.id == mutation_id), None
        )
        if target is None:
            return False
        self.mutation_log.mark_in_flight(target.id)
        adapter = self.registry.resolve(target.provider_key)
        result = adapter.replay_mutation(target)
        if result.state == "acked":
            self.mutation_log.mark_acked(target.id)
        elif result.state == "failed":
            self.mutation_log.mark_failed(
                target.id, result.error_message or "Replay failed."
            )
        elif result.state == "ready_for_sync":
            self.mutation_log.mark_ready(target.id)
        else:
            self.mutation_log.mark_blocked(
                target.id,
                result.error_message or "Replay blocked pending provider support.",
            )
        return True

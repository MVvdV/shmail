"""Provider replay adapter scaffolding for future outbound sync execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from typing import Protocol

from shmail.models import MutationRecord


@dataclass
class ProviderReplayResult:
    """Summarize the outcome of replaying one mutation to a provider."""

    state: str
    error_message: str | None = None


class ProviderReplayAdapter(Protocol):
    """Define provider-specific replay execution without UI coupling."""

    provider_key: str

    def replay_mutation(self, mutation: MutationRecord) -> ProviderReplayResult:
        """Replay one queued mutation against the provider backend."""
        raise NotImplementedError


class DeferredReplayAdapter:
    """Placeholder adapter used while provider replay remains intentionally disabled."""

    provider_key = "deferred"

    def replay_mutation(self, mutation: MutationRecord) -> ProviderReplayResult:
        """Return a blocked result until provider sync-back is explicitly enabled."""
        return ProviderReplayResult(
            state="blocked",
            error_message=(
                f"Provider replay is deferred for mutation {mutation.id} ({mutation.action_type})."
            ),
        )


class GmailReplayAdapter(DeferredReplayAdapter):
    """Placeholder Gmail adapter until live replay is explicitly enabled."""

    provider_key = "gmail"


class ProviderReplayRegistry:
    """Resolve provider replay adapters by provider key with safe fallback."""

    def __init__(
        self,
        adapters: Iterable[ProviderReplayAdapter] | None = None,
        fallback: ProviderReplayAdapter | None = None,
    ) -> None:
        self._fallback = fallback or DeferredReplayAdapter()
        self._adapters: dict[str, ProviderReplayAdapter] = {}
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: ProviderReplayAdapter) -> None:
        """Register one replay adapter by provider key."""
        self._adapters[str(adapter.provider_key)] = adapter

    def resolve(self, provider_key: str) -> ProviderReplayAdapter:
        """Return a provider adapter or the deferred fallback."""
        return self._adapters.get(str(provider_key), self._fallback)

from typing import Any, cast

from shmail.app import ShmailApp
from shmail.services.sync import SyncService


class _DummySyncService:
    def __init__(self) -> None:
        self.reset_calls = 0

    def reset_clients(self) -> None:
        self.reset_calls += 1


def test_sync_service_reset_clients_clears_cached_gmail() -> None:
    """Ensure wake recovery can force Gmail client recreation."""
    service = cast(Any, SyncService.__new__(SyncService))
    service._gmail = object()

    SyncService.reset_clients(service)

    assert service._gmail is None


def test_app_lifecycle_recovery_resets_provider_clients() -> None:
    """Ensure lifecycle recovery bumps generation and resets cached clients."""
    app = ShmailApp()
    dummy_sync = _DummySyncService()
    app.sync_service = cast(Any, dummy_sync)
    app._refresh_visible_surfaces = lambda: None  # type: ignore[method-assign]

    app._recover_from_lifecycle_event("test")

    assert app._lifecycle_generation == 1
    assert dummy_sync.reset_calls == 1
    assert app._resume_refresh_pending is False

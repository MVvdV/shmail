from typing import Any, cast

from shmail.app import ShmailApp
from shmail.services.sync import SyncService


class _DummySyncService:
    def __init__(self) -> None:
        self.reset_calls = 0

    def reset_clients(self) -> None:
        self.reset_calls += 1


class _DummyTimer:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


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
    existing_timer = _DummyTimer()
    replacement_timer = _DummyTimer()
    app.sync_service = cast(Any, dummy_sync)
    app._sync_timer = cast(Any, existing_timer)
    app._sync_in_flight = True
    app._refresh_visible_surfaces = lambda: None  # type: ignore[method-assign]
    app.set_interval = lambda interval, callback: replacement_timer  # type: ignore[method-assign]

    app._recover_from_lifecycle_event("test")

    assert app._lifecycle_generation == 1
    assert dummy_sync.reset_calls == 1
    assert existing_timer.stop_calls == 1
    assert app._sync_timer is replacement_timer
    assert app._sync_in_flight is False
    assert app._resume_refresh_pending is False


def test_lifecycle_recovery_skips_timer_restart_without_sync_service() -> None:
    """Ensure recovery remains a pure redraw when no sync service exists."""
    app = ShmailApp()
    existing_timer = _DummyTimer()
    app._sync_timer = cast(Any, existing_timer)
    app._refresh_visible_surfaces = lambda: None  # type: ignore[method-assign]

    def _unexpected_set_interval(*args, **kwargs):
        raise AssertionError("set_interval should not run without sync service")

    app.set_interval = _unexpected_set_interval  # type: ignore[method-assign]

    app._recover_from_lifecycle_event("test")

    assert existing_timer.stop_calls == 0
    assert app._sync_timer is existing_timer

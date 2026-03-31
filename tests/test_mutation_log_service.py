import json

import pytest

from shmail.services.db import DatabaseRepository
from shmail.services.mutation_log import MutationLogService
from shmail.services.mutation_replay import MutationReplayService
from shmail.services.provider_replay import DeferredReplayAdapter
from shmail.services.provider_replay import ProviderReplayRegistry


@pytest.fixture
def test_db(tmp_path):
    """Provide an isolated repository for mutation log tests."""
    db_file = tmp_path / "mutation_log.db"
    repository = DatabaseRepository(db_path=db_file)
    repository.initialize()
    return repository


def test_mutation_log_state_transitions(test_db):
    """Ensure mutation records can transition through replay states."""
    with test_db.transaction() as conn:
        test_db.append_mutation(
            conn,
            mutation_id="mut-1",
            account_id="user@example.com",
            provider_key="gmail",
            target_kind="message",
            target_id="m-1",
            action_type="message_trash",
            payload_json=json.dumps({"message_id": "m-1"}),
            state="ready_for_sync",
            created_at="2026-03-27T00:00:00+00:00",
            updated_at="2026-03-27T00:00:00+00:00",
        )

    service = MutationLogService(test_db)
    ready = service.list_ready_for_replay()
    assert len(ready) == 1
    assert ready[0].state == "ready_for_sync"

    service.mark_in_flight("mut-1")
    service.mark_failed("mut-1", "Network unavailable")
    ready = service.list_ready_for_replay()
    assert ready[0].state == "failed"
    assert ready[0].error_message == "Network unavailable"
    assert ready[0].retry_count == 1
    assert ready[0].last_attempt_at is not None
    assert ready[0].next_attempt_at is not None

    service.mark_ready("mut-1")
    service.mark_acked("mut-1")
    ready = service.list_ready_for_replay()
    assert ready == []


def test_deferred_replay_adapter_blocks_execution(test_db):
    """Ensure deferred replay never performs provider mutations yet."""
    with test_db.transaction() as conn:
        test_db.append_mutation(
            conn,
            mutation_id="mut-2",
            account_id="user@example.com",
            provider_key="gmail",
            target_kind="draft",
            target_id="d-1",
            action_type="draft_send",
            payload_json="{}",
            state="ready_for_sync",
            created_at="2026-03-27T00:00:00+00:00",
            updated_at="2026-03-27T00:00:00+00:00",
        )
    mutation = MutationLogService(test_db).list_ready_for_replay()[0]

    result = DeferredReplayAdapter().replay_mutation(mutation)

    assert result.state == "blocked"
    assert "deferred" in str(result.error_message).lower()


def test_mutation_replay_service_blocks_ready_items_with_deferred_adapter(test_db):
    """Ensure replay orchestration advances through state transitions safely."""
    with test_db.transaction() as conn:
        test_db.append_mutation(
            conn,
            mutation_id="mut-3",
            account_id="user@example.com",
            provider_key="gmail",
            target_kind="message",
            target_id="m-3",
            action_type="message_move",
            payload_json="{}",
            state="ready_for_sync",
            created_at="2026-03-27T00:00:00+00:00",
            updated_at="2026-03-27T00:00:00+00:00",
        )

    log_service = MutationLogService(test_db)
    replay = MutationReplayService(
        log_service,
        ProviderReplayRegistry(fallback=DeferredReplayAdapter()),
    )

    processed = replay.replay_ready()
    assert processed == ["mut-3"]
    rows = test_db.list_mutations(limit=10)
    assert rows[0]["state"] == "blocked"


def test_retry_helpers_mark_message_and_thread_mutations_ready(test_db):
    """Ensure inline retry helpers reset failed/blocked mutations to ready."""
    with test_db.transaction() as conn:
        test_db.append_mutation(
            conn,
            mutation_id="mut-message",
            account_id="user@example.com",
            provider_key="gmail",
            target_kind="message",
            target_id="m-4",
            action_type="message_labels_sync",
            payload_json="{}",
            state="failed",
            error_message="oops",
            retry_count=2,
            created_at="2026-03-27T00:00:00+00:00",
            updated_at="2026-03-27T00:00:00+00:00",
        )
        test_db.append_mutation(
            conn,
            mutation_id="mut-thread",
            account_id="user@example.com",
            provider_key="gmail",
            target_kind="thread",
            target_id="t-4",
            action_type="thread_trash",
            payload_json="{}",
            state="blocked",
            error_message="later",
            created_at="2026-03-27T00:00:00+00:00",
            updated_at="2026-03-27T00:00:00+00:00",
        )

    service = MutationLogService(test_db)

    assert service.retry_message_mutations("m-4") == ["mut-message"]
    message_mutation = service.get_mutation("mut-message")
    assert message_mutation is not None
    assert message_mutation.state == "ready_for_sync"
    assert service.retry_thread_mutations("t-4") == ["mut-thread"]
    thread_mutation = service.get_mutation("mut-thread")
    assert thread_mutation is not None
    assert thread_mutation.state == "ready_for_sync"

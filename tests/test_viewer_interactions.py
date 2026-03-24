"""Integration-style interaction tests for thread viewer navigation."""

import asyncio
from datetime import datetime, timedelta
from typing import Any, cast
from unittest.mock import patch

import pytest
from textual.app import App
from textual.widgets import Input, TextArea

from shmail.models import Message, MessageDraft
from shmail.screens.message_draft import MessageDraftScreen
from shmail.screens.thread_compose_action import ThreadComposeActionChooserScreen
from shmail.screens.thread_messages import ThreadMessagesScreen
from shmail.services.db import DatabaseService
from shmail.widgets import MessageItem


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh database for thread-viewer interaction tests."""
    db_file = tmp_path / "test_viewer.db"
    db_service = DatabaseService(db_path=db_file)
    db_service.initialize()
    return db_service


def _seed_thread_messages(test_db: DatabaseService) -> None:
    """Seeds two messages in one thread with deterministic link payloads."""
    now = datetime.now()
    body_links_payload = (
        '[{"label":"Example","href":"https://example.com","executable":true},'
        '{"label":"Blocked","href":"javascript:alert(1)","executable":false}]'
    )
    latest = Message(
        id="msg_latest",
        thread_id="thread_1",
        subject="Latest",
        sender="Alice",
        sender_address="alice@example.com",
        recipient_to_addresses="bob@example.com,tester@example.com",
        snippet="latest",
        body="[Example](https://example.com) and [Blocked](javascript:alert(1))",
        body_links=body_links_payload,
        timestamp=now,
    )
    older = Message(
        id="msg_older",
        thread_id="thread_1",
        subject="Older",
        sender="bob@example.com",
        snippet="older",
        body="No links",
        body_links="[]",
        timestamp=now - timedelta(minutes=1),
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, latest)
        test_db.upsert_message(conn, older)


class ViewerTestApp(App):
    """Minimal host app for exercising thread-viewer keyboard interactions."""

    def __init__(self, db_service: DatabaseService):
        super().__init__()
        self.db = db_service
        self.email = "tester@example.com"
        self.notifications: list[tuple[str, str]] = []

    def notify(self, message: str, severity: str = "information", **_kwargs) -> None:
        """Captures notifications for assertion in tests."""
        self.notifications.append((message, severity))

    def on_mount(self) -> None:
        """Pushes the thread viewer screen at startup."""
        self.push_screen(ThreadMessagesScreen("thread_1"))


def test_thread_viewer_cycle_traversal_between_links_and_cards(test_db):
    """Verify Tab-like traversal cycles links before advancing cards."""
    _seed_thread_messages(test_db)

    async def run_test() -> None:
        app = ViewerTestApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            screen = cast(ThreadMessagesScreen, app.screen)
            items = [
                child
                for child in screen.query("MessageItem")
                if isinstance(child, MessageItem)
            ]
            assert len(items) == 2

            latest, older = items
            assert latest.expanded is True
            assert screen.focused is latest

            screen.action_cycle_forward()
            await pilot.pause()
            assert latest.active_link_index == 0
            assert screen.focused is latest

            screen.action_cycle_forward()
            await pilot.pause()
            assert latest.active_link_index == 1
            assert screen.focused is latest

            screen.action_cycle_forward()
            await pilot.pause()
            assert latest.active_link_index == -1
            assert screen.focused is older

            screen.action_cycle_backward()
            await pilot.pause()
            assert screen.focused is latest
            assert latest.active_link_index == 1

            screen.action_cycle_backward()
            await pilot.pause()
            assert latest.active_link_index == 0

    asyncio.run(run_test())


def test_thread_viewer_keeps_only_active_message_expanded(test_db):
    """Verify accordion behavior keeps only the active message expanded."""
    _seed_thread_messages(test_db)

    async def run_test() -> None:
        app = ViewerTestApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            screen = cast(ThreadMessagesScreen, app.screen)
            items = [
                child
                for child in screen.query("MessageItem")
                if isinstance(child, MessageItem)
            ]
            assert len(items) == 2

            latest, older = items
            assert latest.expanded is True
            assert older.expanded is False

            screen.action_next_message()
            await pilot.pause()
            assert latest.expanded is False
            assert older.expanded is True

            screen.action_prev_message()
            await pilot.pause()
            assert latest.expanded is True
            assert older.expanded is False

    asyncio.run(run_test())


def test_enter_opens_allowed_link_and_blocks_disallowed_link(test_db):
    """Verify Enter opens allowed links and warns for blocked schemes."""
    _seed_thread_messages(test_db)

    async def run_test() -> None:
        app = ViewerTestApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            screen = cast(ThreadMessagesScreen, app.screen)
            latest = screen.query_one(MessageItem)

            latest.step_link(1)
            with patch("shmail.widgets.message_item.webbrowser.open") as mock_open:
                latest.action_toggle_expand()
                mock_open.assert_called_once_with("https://example.com")

            latest.step_link(1)
            latest.action_toggle_expand()
            assert app.notifications
            message, severity = app.notifications[-1]
            assert "Blocked link scheme" in message
            assert severity == "warning"

    asyncio.run(run_test())


def test_mouse_link_click_respects_case_insensitive_policy(test_db):
    """Verify mouse link activation uses the shared case-insensitive policy."""
    _seed_thread_messages(test_db)

    class DummyEvent:
        """Simple event stand-in carrying a href value."""

        href = "HTTPS://example.com"

    async def run_test() -> None:
        app = ViewerTestApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            latest = app.screen.query_one(MessageItem)
            with patch("shmail.widgets.message_item.webbrowser.open") as mock_open:
                latest.on_markdown_link_clicked(cast(Any, DummyEvent()))
                mock_open.assert_called_once_with("https://example.com")

    asyncio.run(run_test())


def test_message_item_loads_only_canonical_link_payloads(test_db):
    """Verify malformed persisted link payload entries are ignored or normalized."""
    now = datetime.now()
    malformed = Message(
        id="msg_malformed",
        thread_id="thread_1",
        subject="Malformed",
        sender="alice@example.com",
        snippet="malformed",
        body="Mixed links",
        body_links='[{"label":"MissingHref"},{"href":"HTTPS://example.com"},"bad"]',
        timestamp=now,
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, malformed)

    row = test_db.get_thread_messages("thread_1")[0]
    item = MessageItem(row)
    assert item.has_links() is True
    assert item.step_link(1) is False
    item.expanded = True
    assert item.step_link(1) is True
    active = item.get_active_link()
    assert active is not None
    assert active["href"] == "HTTPS://example.com"
    assert active["label"] == "HTTPS://example.com"
    assert active["executable"] is True


def test_thread_compose_binding_opens_chooser_then_reply_draft(test_db):
    """Verify c from thread screen opens chooser and reply draft seed."""
    _seed_thread_messages(test_db)

    async def run_test() -> None:
        app = ViewerTestApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()
            assert isinstance(app.screen, ThreadComposeActionChooserScreen)

            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            to_field = app.screen.query_one("#draft-to", Input)
            subject_field = app.screen.query_one("#draft-subject", Input)
            editor = app.screen.query_one("#message-draft-editor", TextArea)

            assert "alice@example.com" in to_field.value
            assert subject_field.value.startswith("Re:")
            assert "wrote:" in editor.text

    asyncio.run(run_test())


def test_thread_compose_on_draft_card_resumes_existing_draft(test_db):
    """Verify compose from focused draft card opens existing draft directly."""
    _seed_thread_messages(test_db)
    now = datetime.now()
    draft = MessageDraft(
        id="draft_resume",
        mode="reply",
        to_addresses="alice@example.com",
        cc_addresses="",
        bcc_addresses="",
        subject="Re: Latest",
        body="Resume me",
        source_message_id="msg_latest",
        source_thread_id="thread_1",
        created_at=now,
        updated_at=now,
    )

    with test_db.transaction() as conn:
        test_db.upsert_message_draft(conn, draft)

    async def run_test() -> None:
        app = ViewerTestApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            screen = cast(ThreadMessagesScreen, app.screen)
            items = [
                child
                for child in screen.query("MessageItem")
                if isinstance(child, MessageItem)
            ]
            draft_item = next(
                item for item in items if item.message_data.get("is_draft")
            )
            assert draft_item.get_shortcuts()[0] == ("ENTER", "Resume Draft")
            draft_item.focus()
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftScreen)
            subject_field = app.screen.query_one("#draft-subject", Input)
            assert subject_field.value == "Re: Latest"

    asyncio.run(run_test())


def test_mouse_click_ignores_noncanonical_markdown_link(test_db):
    """Verify mouse clicks are ignored when href is not in canonical payload."""
    _seed_thread_messages(test_db)

    class DummyEvent:
        """Simple event stand-in for non-canonical link clicks."""

        href = "https://not-in-index.example"

        def prevent_default(self) -> None:
            return None

    async def run_test() -> None:
        app = ViewerTestApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            latest = app.screen.query_one(MessageItem)
            with patch("shmail.widgets.message_item.webbrowser.open") as mock_open:
                latest.on_markdown_link_clicked(cast(Any, DummyEvent()))
                mock_open.assert_not_called()

            assert app.notifications
            message, severity = app.notifications[-1]
            assert "Ignored non-canonical link" in message
            assert severity == "warning"

    asyncio.run(run_test())

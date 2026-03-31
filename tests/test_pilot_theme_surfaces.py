"""Pilot coverage for runtime theme-sensitive UI surfaces."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Input, Static

from shmail.config import Theme, settings
from shmail.models import Label, Message, MessageDraft
from shmail.screens import MainScreen
from shmail.screens.message_draft import (
    MessageDraftDiscardConfirmScreen,
    MessageDraftScreen,
    MessageDraftSeed,
)
from shmail.screens.thread_messages import ThreadMessagesScreen
from shmail.services.db import DatabaseRepository
from shmail.services.label_query import LabelQueryService
from shmail.services.label_state import LabelStateService
from shmail.services.theme import build_textual_theme
from shmail.services.thread_query import ThreadQueryService
from shmail.services.thread_viewer import ThreadViewerService
from shmail.widgets import AppFooter, MessageItem, ThreadFooter, ThreadList, ThreadRow

CSS_PATH = str(Path(__file__).resolve().parents[1] / "shmail" / "shmail.tcss")


@pytest.fixture
def test_db(tmp_path: Path) -> DatabaseRepository:
    """Provide a fresh database for theme-sensitive Pilot tests."""
    db_path = tmp_path / "pilot_theme.db"
    repository = DatabaseRepository(db_path=db_path)
    repository.initialize()
    return repository


def _color_hex(widget: Widget, attribute: str) -> str:
    """Return one widget style color as a normalized hex string."""
    return getattr(widget.styles, attribute).hex.lower()


def _border_hex(widget: Widget) -> str:
    """Return the top border color as a normalized hex string."""
    return widget.styles.border.top[1].hex.lower()


def _shortcut_pairs(container: Widget) -> list[tuple[str, str]]:
    """Return rendered shortcut key-label pairs from one mounted container."""
    keys = [
        str(widget.content)
        for widget in container.query(".shortcut-key")
        if isinstance(widget, Static)
    ]
    labels = [
        str(widget.content)
        for widget in container.query(".shortcut-label")
        if isinstance(widget, Static)
    ]
    return list(zip(keys, labels, strict=True))


class ThemedMainApp(App[None]):
    """Host the main workspace with one configured runtime theme."""

    CSS_PATH = CSS_PATH

    def __init__(self, repository: DatabaseRepository, theme_config: Theme) -> None:
        super().__init__()
        self.repository = repository
        self.label_query = LabelQueryService(repository)
        self.label_state = LabelStateService(self.label_query)
        self.thread_query = ThreadQueryService(repository)
        self.thread_viewer = ThreadViewerService(repository)
        self.email = "tester@example.com"
        self._theme_config = theme_config

    def on_mount(self) -> None:
        """Apply the configured theme before mounting the main workspace."""
        theme = build_textual_theme(self._theme_config)
        self.register_theme(theme)
        self.theme = theme.name
        self.push_screen(MainScreen())


class MessageCardThemeApp(App[None]):
    """Mount standalone message cards under one configured runtime theme."""

    CSS_PATH = CSS_PATH

    def __init__(self, theme_config: Theme) -> None:
        super().__init__()
        self._theme_config = theme_config

    def compose(self) -> ComposeResult:
        """Render one normal and one draft message card."""
        yield MessageItem(
            {
                "subject": "Normal message",
                "sender": "Alice",
                "recipient_to": "Bob",
                "timestamp": datetime(2026, 3, 25, 10, 0, 0),
                "body": "Hello",
            },
            id="normal-message",
        )
        yield MessageItem(
            {
                "subject": "Draft message",
                "sender": "Alice",
                "recipient_to": "Bob",
                "timestamp": datetime(2026, 3, 25, 10, 5, 0),
                "body": "Draft body",
                "is_draft": True,
            },
            id="draft-message",
        )

    def on_mount(self) -> None:
        """Apply the configured theme for card-style assertions."""
        theme = build_textual_theme(self._theme_config)
        self.register_theme(theme)
        self.theme = theme.name


class ThreadShortcutApp(App[None]):
    """Host the thread viewer with one configured runtime theme."""

    CSS_PATH = CSS_PATH

    def __init__(self, repository: DatabaseRepository, theme_config: Theme) -> None:
        super().__init__()
        self.repository = repository
        self.label_query = LabelQueryService(repository)
        self.label_state = LabelStateService(self.label_query)
        self.thread_query = ThreadQueryService(repository)
        self.thread_viewer = ThreadViewerService(repository)
        self.email = "tester@example.com"
        self._theme_config = theme_config

    def on_mount(self) -> None:
        """Apply theme and open the thread viewer."""
        theme = build_textual_theme(self._theme_config)
        self.register_theme(theme)
        self.theme = theme.name
        self.push_screen(ThreadMessagesScreen("thread_shortcuts"))


def _seed_thread_shortcut_message(test_db: DatabaseRepository) -> None:
    """Seed one thread row for mounted footer shortcut tests."""
    with test_db.transaction() as conn:
        test_db.upsert_message(
            conn,
            Message(
                id="thread_shortcuts_message",
                thread_id="thread_shortcuts",
                subject="Shortcut thread",
                sender="alice@example.com",
                snippet="Shortcut body",
                body="Hello [Example](https://example.com)",
                body_links='[{"label":"Example","href":"https://example.com","executable":true}]',
                timestamp=datetime(2026, 3, 25, 10, 15, 0),
                labels=[Label(id="INBOX", name="Inbox", type="system")],
            ),
        )


def test_draft_discard_modal_uses_runtime_theme_tokens(
    test_db: DatabaseRepository,
) -> None:
    """Ensure modal backdrop and warning surfaces follow the active theme."""

    async def run_test() -> None:
        app = ThemedMainApp(test_db, Theme(name="white", source="preset"))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            compose = cast(MessageDraftScreen, app.screen)
            compose.query_one("#draft-subject", Input).value = "Unsaved"
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            screen = cast(MessageDraftDiscardConfirmScreen, app.screen)
            modal = screen.query_one("#message-draft-discard-modal")
            title = screen.query_one("#message-draft-discard-title", Static)

            assert _color_hex(screen, "background") == "#ffffff8c"
            assert _border_hex(modal) == "#4a4a4a"
            assert _color_hex(title, "color") == "#4a4a4a"

    asyncio.run(run_test())


def test_message_cards_use_primary_and_warning_theme_colors() -> None:
    """Ensure focused cards and draft surfaces resolve primary and warning tokens."""

    async def run_test() -> None:
        app = MessageCardThemeApp(Theme(name="white", source="preset"))
        async with app.run_test() as pilot:
            await pilot.pause()

            normal = app.query_one("#normal-message", MessageItem)
            draft = app.query_one("#draft-message", MessageItem)

            normal.focus()
            await pilot.pause()
            normal_subject = normal.query_one(".message-subject", Static)

            assert _border_hex(normal) == "#6e6e6e"
            assert _color_hex(normal_subject, "color") == "#6e6e6e"

            draft.focus()
            await pilot.pause()
            draft_subject = draft.query_one(".message-subject", Static)

            assert _border_hex(draft) == "#4a4a4a"
            assert _color_hex(draft_subject, "color") == "#4a4a4a"

    asyncio.run(run_test())


def test_thread_draft_chip_renders_after_runtime_update(
    test_db: DatabaseRepository,
) -> None:
    """Ensure Drafts chips appear in thread rows after local draft updates."""
    message = Message(
        id="draft_marker_message",
        thread_id="draft_marker_thread",
        subject="Thread with draft",
        sender="alice@example.com",
        snippet="Draft marker",
        timestamp=datetime(2026, 3, 25, 9, 30, 0),
        labels=[Label(id="INBOX", name="Inbox", type="system")],
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message)
        test_db.upsert_message_draft(
            conn,
            MessageDraft(
                id="draft_marker_local",
                mode="reply",
                to_addresses="alice@example.com",
                cc_addresses="",
                bcc_addresses="",
                subject="Re: Thread with draft",
                body="Draft body",
                source_message_id="draft_marker_message",
                source_thread_id="draft_marker_thread",
                created_at=datetime(2026, 3, 25, 9, 35, 0),
                updated_at=datetime(2026, 3, 25, 9, 35, 0),
            ),
        )

    async def run_test() -> None:
        app = ThemedMainApp(test_db, Theme(name="white", source="preset"))
        async with app.run_test() as pilot:
            await pilot.pause()

            thread_list = app.screen.query_one("#threads-list", ThreadList)
            thread_list.load_threads("INBOX")
            await pilot.pause()

            row = cast(ThreadRow, thread_list.query_one(ThreadRow))
            assert "Drafts" in row._render_label_chips()

    asyncio.run(run_test())


def test_main_footer_renders_configured_shortcut_labels(
    test_db: DatabaseRepository,
) -> None:
    """Ensure the mounted main footer reflects configured label-pane bindings."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "project", "Project", "user")

    original_compose = settings.keybindings.compose
    original_label_new = settings.keybindings.label_new
    original_label_edit = settings.keybindings.label_edit
    original_first = settings.keybindings.first
    original_last = settings.keybindings.last
    original_pane_next = settings.keybindings.pane_next
    try:
        settings.keybindings.compose = "c"
        settings.keybindings.label_new = "ctrl+n"
        settings.keybindings.label_edit = "ctrl+e"
        settings.keybindings.first = "home"
        settings.keybindings.last = "end"
        settings.keybindings.pane_next = "ctrl+l"

        async def run_test() -> None:
            app = ThemedMainApp(test_db, Theme(name="white", source="preset"))
            async with app.run_test() as pilot:
                await pilot.pause()

                app.screen.query_one("#labels-sidebar-list").focus()
                await pilot.pause()

                footer = app.screen.query_one(AppFooter)
                shortcuts = _shortcut_pairs(
                    footer.query_one("#app-shortcuts", Horizontal)
                )
                assert ("c", "Compose") in shortcuts
                assert ("Ctrl+n", "New label") in shortcuts
                assert ("Home/End", "Home/End") in shortcuts
                assert ("Ctrl+l", "Threads") in shortcuts
                assert ("Ctrl+e", "Edit label") not in shortcuts

                await pilot.press("down", "down", "down")
                await pilot.pause()

                shortcuts = _shortcut_pairs(
                    footer.query_one("#app-shortcuts", Horizontal)
                )
                assert ("Ctrl+e", "Edit label") in shortcuts

        asyncio.run(run_test())
    finally:
        settings.keybindings.compose = original_compose
        settings.keybindings.label_new = original_label_new
        settings.keybindings.label_edit = original_label_edit
        settings.keybindings.first = original_first
        settings.keybindings.last = original_last
        settings.keybindings.pane_next = original_pane_next


def test_thread_footer_renders_configured_shortcut_labels(
    test_db: DatabaseRepository,
) -> None:
    """Ensure the mounted thread footer reflects configured traversal bindings."""
    _seed_thread_shortcut_message(test_db)
    original_cycle_forward = settings.keybindings.thread_cycle_forward
    original_cycle_backward = settings.keybindings.thread_cycle_backward
    original_close = settings.keybindings.close
    try:
        settings.keybindings.thread_cycle_forward = "n"
        settings.keybindings.thread_cycle_backward = "shift+n"
        settings.keybindings.close = "ctrl+w"

        async def run_test() -> None:
            app = ThreadShortcutApp(test_db, Theme(name="white", source="preset"))
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.pause()

                footer = app.screen.query_one(ThreadFooter)
                shortcuts = _shortcut_pairs(
                    footer.query_one("#thread-shortcuts", Horizontal)
                )
                assert ("n/Shift+n", "Cycle") in shortcuts
                assert ("Ctrl+w", "Close") in shortcuts

        asyncio.run(run_test())
    finally:
        settings.keybindings.thread_cycle_forward = original_cycle_forward
        settings.keybindings.thread_cycle_backward = original_cycle_backward
        settings.keybindings.close = original_close


def test_discard_dialog_renders_configured_shortcut_labels(
    test_db: DatabaseRepository,
) -> None:
    """Ensure the mounted discard dialog reflects configured action bindings."""
    original_select = settings.keybindings.select
    original_close = settings.keybindings.close
    original_up = settings.keybindings.up
    original_down = settings.keybindings.down
    try:
        settings.keybindings.select = "space"
        settings.keybindings.close = "ctrl+w"
        settings.keybindings.up = "w"
        settings.keybindings.down = "s"

        async def run_test() -> None:
            app = ThemedMainApp(test_db, Theme(name="white", source="preset"))
            async with app.run_test() as pilot:
                await pilot.pause()

                app.push_screen(MessageDraftScreen(seed=MessageDraftSeed(mode="new")))
                await pilot.pause()

                compose = cast(MessageDraftScreen, app.screen)
                compose.query_one("#draft-subject", Input).value = "Unsaved"
                await pilot.pause()

                compose.action_close()
                await pilot.pause()

                dialog = cast(MessageDraftDiscardConfirmScreen, app.screen)
                shortcuts = _shortcut_pairs(
                    dialog.query_one("#message-draft-discard-shortcuts", Horizontal)
                )
                assert ("Space", "Choose") in shortcuts
                assert ("s/w", "Move") in shortcuts
                assert ("Ctrl+w", "Keep") in shortcuts

        asyncio.run(run_test())
    finally:
        settings.keybindings.select = original_select
        settings.keybindings.close = original_close
        settings.keybindings.up = original_up
        settings.keybindings.down = original_down

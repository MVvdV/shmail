import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest
from textual.app import App
from textual.reactive import reactive
from textual.widgets import Input, Select, Static, TabbedContent, TextArea

from shmail.services.auth import AuthService
from shmail.services.draft_preview import to_rendered_markdown_preview
from shmail.screens.message_draft import MessageDraftScreen
from shmail.screens import MainScreen
from shmail.widgets import AppHeader, LabelsSidebar, ThreadList, ThreadRow, LabelItem
from shmail.services.db import DatabaseService
from shmail.models import Label, Message, MessageDraft


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh, isolated database for each test."""
    db_path = tmp_path / "test.db"
    db_service = DatabaseService(db_path=db_path)
    db_service.initialize()
    return db_service


class MockApp(App):
    """A mock app to host the MainScreen for testing."""

    drafts_revision = reactive(0)

    def __init__(self, db_service):
        super().__init__()
        self.db = db_service
        self.email = "tester@example.com"
        self.notifications = []
        self.sign_out_calls = 0
        self.sign_in_calls = 0

    def notify(self, message: str, severity: str = "information", **_kwargs) -> None:
        """Capture notify messages for assertion in UI tests."""
        self.notifications.append((message, severity))

    def sign_out_current_account(self) -> None:
        """Track sign-out requests for account selector tests."""
        self.sign_out_calls += 1

    def sign_in_another_account(self) -> None:
        """Track add-account requests for account selector tests."""
        self.sign_in_calls += 1

    def bump_drafts_revision(self) -> None:
        """Mirror app draft-revision signal for widget watcher tests."""
        self.drafts_revision += 1

    def on_mount(self) -> None:
        self.push_screen(MainScreen())


def find_node_by_data(labels_sidebar, data):
    """Search for a LabelItem with specific data in the ListView."""
    for item in labels_sidebar.label_list.children:
        if isinstance(item, LabelItem) and item.label_id == data:
            return item
    return None


def _is_within(widget, ancestor) -> bool:
    """Returns True when a widget is the same as or inside ancestor."""
    current = widget
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def test_sidebar_labels_load(test_db):
    """Verifies labels are correctly populated in the Labels sidebar."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")
        test_db.upsert_label(conn, "SENT", "Sent", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            inbox_item = find_node_by_data(labels_sidebar, "INBOX")
            sent_item = find_node_by_data(labels_sidebar, "SENT")

            assert inbox_item is not None
            assert sent_item is not None
            assert "Inbox" in inbox_item.display_name
            assert "Sent" in sent_item.display_name

    asyncio.run(run_test())


def test_full_navigation_flow(test_db):
    """Verifies selecting a label in Labels updates the Threads list."""
    work_label = Label(id="WORK", name="Work", type="user")
    message1 = Message(
        id="e1",
        thread_id="t1",
        subject="Subject 1",
        sender="a@b.com",
        snippet="Snippet 1",
        timestamp=datetime.now(),
        labels=[work_label],
    )
    message2 = Message(
        id="e2",
        thread_id="t2",
        subject="Subject 2",
        sender="c@d.com",
        snippet="Snippet 2",
        timestamp=datetime.now(),
        labels=[work_label],
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message1)
        test_db.upsert_message(conn, message2)

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            thread_list = app.screen.query_one("#threads-list", ThreadList)

            work_item = find_node_by_data(labels_sidebar, "WORK")
            assert work_item is not None

            idx = labels_sidebar.label_list.children.index(work_item)
            labels_sidebar.label_list.index = idx
            labels_sidebar.label_list.action_select_cursor()

            await pilot.pause()

            rows = thread_list.query(ThreadRow)
            assert len(rows) == 2

    asyncio.run(run_test())


def test_sidebar_enter_selects_label_and_focuses_thread_list(test_db):
    """Verifies Enter on Labels selection shifts focus to Threads list."""
    work_label = Label(id="WORK", name="Work", type="user")
    message = Message(
        id="e_focus",
        thread_id="t_focus",
        subject="Subject Focus",
        sender="focus@test.com",
        snippet="Snippet Focus",
        timestamp=datetime.now(),
        labels=[work_label],
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message)

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            thread_list = app.screen.query_one("#threads-list", ThreadList)

            work_item = find_node_by_data(labels_sidebar, "WORK")
            assert work_item is not None

            idx = labels_sidebar.label_list.children.index(work_item)
            labels_sidebar.label_list.index = idx
            labels_sidebar.label_list.focus()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            assert _is_within(app.focused, thread_list)

    asyncio.run(run_test())


def test_empty_state_feedback(test_db):
    """Verifies that the UI displays a placeholder message when a label contains no messages."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "TRASH", "Trash", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            thread_list = app.screen.query_one("#threads-list", ThreadList)

            trash_item = find_node_by_data(labels_sidebar, "TRASH")
            assert trash_item is not None

            idx = labels_sidebar.label_list.children.index(trash_item)
            labels_sidebar.label_list.index = idx
            labels_sidebar.label_list.action_select_cursor()

            await pilot.pause()

            from textual.widgets import Static

            empty_msg = thread_list.query_one("#empty-state-msg", Static)
            assert "No conversations found" in str(empty_msg.render_line(0))

    asyncio.run(run_test())


def test_header_account_select_lists_emails_and_gates_account_switching(test_db):
    """Verify account selector uses real emails and blocks switching action."""

    async def run_test():
        app = MockApp(test_db)
        with patch.object(
            AuthService,
            "list_known_accounts",
            return_value=["tester@example.com", "second@example.com"],
        ):
            async with app.run_test() as pilot:
                await pilot.pause()

                account_select = app.screen.query_one("#app-account-select", Select)
                assert account_select.value == AppHeader._account_value(
                    "tester@example.com"
                )

                prompts = [str(prompt) for prompt, _ in account_select._options]
                assert "tester@example.com" in prompts
                assert "second@example.com" in prompts
                assert "Sign out of this account" in prompts
                assert "Sign in another account" in prompts

                account_select.value = AppHeader._account_value("second@example.com")
                await pilot.pause()

                assert account_select.value == AppHeader._account_value(
                    "tester@example.com"
                )
                assert app.notifications
                message, severity = app.notifications[-1]
                assert "disabled" in message
                assert severity == "warning"

    asyncio.run(run_test())


def test_header_account_select_sign_actions_dispatch_to_app(test_db):
    """Verify sign-out and sign-in options dispatch to app handlers."""

    async def run_test():
        app = MockApp(test_db)
        with patch.object(AuthService, "list_known_accounts", return_value=[app.email]):
            async with app.run_test() as pilot:
                await pilot.pause()

                account_select = app.screen.query_one("#app-account-select", Select)

                account_select.value = AppHeader.SIGN_OUT_THIS
                await pilot.pause()
                assert app.sign_out_calls == 1

                account_select.value = AppHeader.SIGN_IN_ANOTHER
                await pilot.pause()
                assert app.sign_in_calls == 1

    asyncio.run(run_test())


def test_tab_cycles_only_between_sidebar_and_thread_list(test_db):
    """Verify tab/shift+tab ignore header and only switch Labels/Threads."""

    async def run_test():
        app = MockApp(test_db)
        with patch.object(AuthService, "list_known_accounts", return_value=[app.email]):
            async with app.run_test() as pilot:
                await pilot.pause()

                labels_list = app.screen.query_one("#labels-sidebar-list")
                thread_list = app.screen.query_one("#threads-list", ThreadList)
                account_select = app.screen.query_one("#app-account-select", Select)

                labels_list.focus()
                await pilot.pause()

                await pilot.press("tab")
                await pilot.pause()
                assert _is_within(app.focused, thread_list)
                assert app.focused is not account_select

                await pilot.press("tab")
                await pilot.pause()
                assert _is_within(app.focused, labels_list)
                assert app.focused is not account_select

                await pilot.press("shift+tab")
                await pilot.pause()
                assert _is_within(app.focused, thread_list)
                assert app.focused is not account_select

    asyncio.run(run_test())


def test_account_menu_escape_restores_previous_focus(test_db):
    """Verify closing account menu with escape restores prior pane focus."""

    async def run_test():
        app = MockApp(test_db)
        with patch.object(AuthService, "list_known_accounts", return_value=[app.email]):
            async with app.run_test() as pilot:
                await pilot.pause()

                header = app.screen.query_one(AppHeader)
                thread_list = app.screen.query_one("#threads-list", ThreadList)
                account_select = app.screen.query_one("#app-account-select", Select)

                thread_list.focus()
                await pilot.pause()

                header.activate_account_menu()
                await pilot.pause()
                assert account_select.expanded is True

                await pilot.press("escape")
                await pilot.pause()

                assert account_select.expanded is False
                assert _is_within(app.focused, thread_list)

    asyncio.run(run_test())


def test_compose_binding_from_main_opens_message_draft_modal(test_db):
    """Verify compose keybinding opens a new MessageDraftScreen from main."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)

    asyncio.run(run_test())


def test_message_draft_screen_ctrl_s_persists_local_draft(test_db):
    """Verify explicit save in compose modal writes local message draft row."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_to = app.screen.query_one("#draft-to", Input)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_editor = app.screen.query_one("#message-draft-editor", TextArea)

            draft_to.value = "alice@example.com"
            draft_subject.value = "Draft Subject"
            draft_editor.load_text("Draft body content")
            app.screen.action_save_draft()
            await pilot.pause()

            rows = test_db.list_message_drafts()
            assert rows
            latest = rows[0]
            assert latest["to_addresses"] == "alice@example.com"
            assert latest["subject"] == "Draft Subject"
            assert latest["body"] == "Draft body content"

    asyncio.run(run_test())


def test_compose_tab_switch_binding_works_with_alt_fallback(test_db):
    """Verify compose body tab switching works with reliable fallback bindings."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            tabs = app.screen.query_one("#message-draft-body-tabs", TabbedContent)
            assert tabs.active == "draft-edit"

            await pilot.press("alt+right")
            await pilot.pause()
            assert tabs.active == "draft-preview"

            await pilot.press("alt+left")
            await pilot.pause()
            assert tabs.active == "draft-edit"

    asyncio.run(run_test())


def test_draft_thread_row_shows_draft_indicator_symbol(test_db):
    """Verify threads loaded from DRAFT label include visible draft marker."""
    now = datetime.now()
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "DRAFT", "Drafts", "system")
        test_db.upsert_message_draft(
            conn,
            MessageDraft(
                id="draft_visual",
                mode="new",
                to_addresses="alice@example.com",
                cc_addresses="",
                bcc_addresses="",
                subject="Draft Visual",
                body="Body",
                source_message_id=None,
                source_thread_id=None,
                created_at=now,
                updated_at=now,
            ),
        )

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            thread_list = app.screen.query_one("#threads-list", ThreadList)
            draft_item = find_node_by_data(labels_sidebar, "DRAFT")
            assert draft_item is not None

            idx = labels_sidebar.label_list.children.index(draft_item)
            labels_sidebar.label_list.index = idx
            labels_sidebar.label_list.action_select_cursor()
            await pilot.pause()

            row = thread_list.query_one(ThreadRow)
            indicator = row.query_one(".draft-indicator", Static)
            assert "✎" in str(indicator.render_line(0))

    asyncio.run(run_test())


def test_thread_row_draft_indicator_updates_without_label_switch(test_db):
    """Verify draft marker appears after revision bump without changing labels."""
    inbox = Label(id="INBOX", name="Inbox", type="system")
    now = datetime.now()
    message = Message(
        id="m_draft_refresh",
        thread_id="t_draft_refresh",
        subject="Refresh",
        sender="sender@example.com",
        snippet="snippet",
        timestamp=now,
        labels=[inbox],
    )

    with test_db.transaction() as conn:
        test_db.upsert_message(conn, message)

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()

            thread_row = app.screen.query_one(ThreadRow)
            draft_indicator = thread_row.query_one(".draft-indicator", Static)
            assert "✎" not in str(draft_indicator.render_line(0))

            with test_db.transaction() as conn:
                test_db.upsert_message_draft(
                    conn,
                    MessageDraft(
                        id="draft_refresh",
                        mode="reply",
                        to_addresses="alice@example.com",
                        cc_addresses="",
                        bcc_addresses="",
                        subject="Re: Refresh",
                        body="Draft body",
                        source_message_id="m_draft_refresh",
                        source_thread_id="t_draft_refresh",
                        created_at=now,
                        updated_at=now,
                    ),
                )

            app.bump_drafts_revision()
            await pilot.pause()
            await pilot.pause()

            updated_row = app.screen.query_one(ThreadRow)
            updated_indicator = updated_row.query_one(".draft-indicator", Static)
            assert "✎" in str(updated_indicator.render_line(0))

    asyncio.run(run_test())


def test_compose_preview_normalization_preserves_single_newlines_outside_code():
    """Ensure compose preview preserves visual line breaks for plain and quote lines."""
    source = "alpha\nbeta\n\n> one\n> two\n\n```\nline1\nline2\n```"
    preview = to_rendered_markdown_preview(source)
    assert "alpha  \nbeta" in preview
    assert "> one  \n> two" in preview
    assert "```\nline1\nline2\n```" in preview

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest
from textual.app import App
from textual.widgets import Input, Select, Static, TabbedContent, TextArea

from shmail.services.auth import AuthService
from shmail.config import settings
from shmail.services.label_query import LabelQueryService
from shmail.services.label_state import LabelStateService
from shmail.services.draft_preview import to_rendered_markdown_preview
from shmail.screens.message_draft import (
    MessageDraftCloseUpdate,
    MessageDraftDiscardConfirmScreen,
    MessageDraftScreen,
    MessageDraftSeed,
)
from shmail.screens.label_editor import LabelEditScreen
from shmail.screens import MainScreen
from shmail.widgets import (
    AppHeader,
    LabelsSidebar,
    ThreadList,
    ThreadRow,
    LabelItem,
    MessageItem,
)
from shmail.services.db import DatabaseRepository
from shmail.models import Label, Message, MessageDraft
from shmail.services.thread_query import ThreadQueryService
from shmail.services.thread_viewer import ThreadViewerService


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh, isolated database for each test."""
    db_path = tmp_path / "test.db"
    repository = DatabaseRepository(db_path=db_path)
    repository.initialize()
    return repository


class MockApp(App):
    """A mock app to host the MainScreen for testing."""

    def __init__(self, repository):
        super().__init__()
        self.repository = repository
        self.label_query = LabelQueryService(repository)
        self.label_state = LabelStateService(self.label_query)
        self.thread_query = ThreadQueryService(repository)
        self.thread_viewer = ThreadViewerService(repository)
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

    def apply_message_draft_update(self, update) -> None:
        """Mirror targeted draft refresh handling used by the real app."""
        if update is None or not update.did_change:
            return

        source_thread_id = (update.source_thread_id or "").strip()
        main_screen = self.screen
        labels_sidebar = main_screen.query_one("#labels-sidebar", LabelsSidebar)
        total_drafts = self.repository.get_total_local_draft_count()
        patch = self.label_state.patch_label("DRAFT", unread_count=total_drafts)
        if patch is not None:
            labels_sidebar.apply_label_patch(patch)
        else:
            labels_sidebar.refresh_labels()

        thread_list = main_screen.query_one("#threads-list", ThreadList)
        current_label = str(getattr(thread_list, "current_label_id", "") or "")
        if current_label.upper() == "DRAFT":
            thread_list.load_threads("DRAFT")
            return

        if source_thread_id:
            draft_count = self.repository.get_thread_draft_count(source_thread_id)
            thread_list.update_thread_draft_marker(source_thread_id, draft_count)

    def apply_label_update(self, result) -> None:
        """Mirror label-edit refresh handling used by the real app."""
        if result is None:
            return

        main_screen = self.screen
        labels_sidebar = main_screen.query_one("#labels-sidebar", LabelsSidebar)
        labels_sidebar.refresh_labels(selected_label_id=result.focus_label_id)

        thread_list = main_screen.query_one("#threads-list", ThreadList)
        current_label = str(getattr(thread_list, "current_label_id", "") or "")
        if current_label:
            thread_list.load_threads(current_label)

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


def test_thread_row_outbox_labels_include_outbox_chip():
    """Queued outbox rows should surface Outbox through label chips."""
    row = ThreadRow(
        {
            "thread_id": "thread-1",
            "current_label_id": "OUTBOX",
            "outbox_count": 1,
            "has_outbox": 1,
            "thread_labels": [{"id": "OUTBOX", "name": "Outbox"}],
        }
    )

    assert "Outbox" in row._render_label_chips()


def test_message_item_failed_state_renders_failure_icon_chip():
    """Failed message mutations should render an inline status icon chip."""
    item = MessageItem(
        {
            "subject": "Test",
            "sender": "A",
            "recipient_to": "B",
            "timestamp": "2026-03-25T10:00:00+00:00",
            "mutation_failed_count": 1,
        }
    )

    assert "!" in item._render_label_chips()


def test_thread_row_renders_saved_label_colors():
    """Thread rows should render custom colors from stored label metadata."""
    row = ThreadRow(
        {
            "thread_id": "thread-1",
            "thread_labels": [
                {
                    "id": "INBOX",
                    "name": "Inbox",
                    "background_color": "#4986e7",
                    "text_color": "#ffffff",
                }
            ],
        }
    )

    chips = row._render_label_chips()
    assert "#4986e7" in chips
    assert "#ffffff" in chips


def test_message_item_renders_saved_label_colors():
    """Message items should render custom colors from stored label metadata."""
    item = MessageItem(
        {
            "subject": "Test",
            "sender": "A",
            "recipient_to": "B",
            "timestamp": "2026-03-25T10:00:00+00:00",
            "labels": [
                {
                    "id": "INBOX",
                    "name": "Inbox",
                    "background_color": "#4986e7",
                    "text_color": "#ffffff",
                }
            ],
        }
    )

    chips = item._render_label_chips()
    assert "#4986e7" in chips
    assert "#ffffff" in chips


def test_message_item_attachment_shortcuts_and_select_render_when_available():
    """Expanded message cards should expose one inline attachment selector."""
    item = MessageItem(
        {
            "subject": "Test",
            "sender": "A",
            "recipient_to": "B",
            "timestamp": "2026-03-25T10:00:00+00:00",
            "attachments": [
                {"id": "msg:1", "filename": "report.pdf", "size_bytes": 2048}
            ],
        }
    )

    shortcuts = item.get_shortcuts()
    options = item._attachment_select_options()

    labels = {label for _, label in shortcuts}
    assert "Attachments" in labels
    assert options[0][0].startswith("report.pdf")
    assert options[-1][0] == "Download all attachments"


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


def test_sidebar_applies_label_state_patch_without_full_reload(test_db):
    """Verify sidebar can apply one targeted label-state patch in place."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "DRAFT", "Draft", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            draft_item = find_node_by_data(labels_sidebar, "DRAFT")
            assert draft_item is not None
            assert draft_item.count == 0

            patch = app.label_state.patch_label("DRAFT", unread_count=3, name="Draft")
            assert patch is not None
            labels_sidebar.apply_label_patch(patch)

            assert draft_item.count == 3

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


def test_sidebar_focus_restores_cursor_to_active_label(test_db):
    """Verify sidebar focus snaps back to the active label without stale selection drift."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")
        test_db.upsert_label(conn, "SENT", "Sent", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            labels_list = app.screen.query_one("#labels-sidebar-list")
            thread_list = app.screen.query_one("#threads-list", ThreadList)

            labels_list.focus()
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            selected_items = [
                item
                for item in labels_sidebar.label_list.query(LabelItem)
                if item.has_class("selected")
            ]
            assert len(selected_items) == 1
            assert selected_items[0].label_id == "SENT"
            assert _is_within(app.focused, thread_list)

            labels_sidebar.label_list.index = 0
            await pilot.press("tab")
            await pilot.pause()

            assert _is_within(app.focused, labels_list)
            assert labels_sidebar.label_list.index == 1
            selected_items = [
                item
                for item in labels_sidebar.label_list.query(LabelItem)
                if item.has_class("selected")
            ]
            assert len(selected_items) == 1
            assert selected_items[0].label_id == "SENT"

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


def test_message_draft_close_with_changes_opens_discard_confirmation(test_db):
    """Verify closing a dirty draft prompts for discard confirmation."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_subject.value = "Unsaved Subject"
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftDiscardConfirmScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftScreen)

    asyncio.run(run_test())


def test_message_draft_close_without_edits_does_not_prompt(test_db):
    """Verify open-close without edits dismisses directly without confirmation."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            await pilot.press("escape")
            await pilot.pause()

            assert isinstance(app.screen, MainScreen)

    asyncio.run(run_test())


def test_message_draft_close_after_autosave_still_opens_discard_confirmation(test_db):
    """Verify close confirmation still appears after autosave clears dirty flag."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_subject.value = "Autosaved Subject"
            await pilot.pause(1.0)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftDiscardConfirmScreen)

    asyncio.run(run_test())


def test_message_draft_discard_removes_new_local_draft(test_db):
    """Verify discarding a new dirty draft deletes its local persisted row."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_editor = app.screen.query_one("#message-draft-editor", TextArea)
            draft_subject.value = "Disposable"
            draft_editor.load_text("Delete me")
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftDiscardConfirmScreen)

            await pilot.press("d")
            await pilot.pause()
            await pilot.pause()

            assert isinstance(app.screen, MainScreen)
            assert test_db.list_message_drafts() == []
            assert app.notifications[-1] == ("Draft changes discarded.", "information")

    asyncio.run(run_test())


def test_message_draft_delete_option_removes_existing_draft(test_db):
    """Verify delete action removes an existing persisted draft entirely."""
    now = datetime.now()
    with test_db.transaction() as conn:
        test_db.upsert_message_draft(
            conn,
            MessageDraft(
                id="draft_delete_existing",
                mode="reply",
                to_addresses="alice@example.com",
                cc_addresses="",
                bcc_addresses="",
                subject="Re: Delete Me",
                body="Delete body",
                source_message_id="message_1",
                source_thread_id="thread_1",
                created_at=now,
                updated_at=now,
            ),
        )

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(
                MessageDraftScreen(
                    seed=MessageDraftSeed(
                        mode="draft", draft_id="draft_delete_existing"
                    )
                )
            )
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_subject.value = "Re: Delete Me Updated"
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftDiscardConfirmScreen)

            await pilot.press("x")
            await pilot.pause()
            await pilot.pause()

            assert isinstance(app.screen, MainScreen)
            assert test_db.get_message_draft("draft_delete_existing") is None
            assert app.notifications[-1] == ("Draft deleted.", "information")

    asyncio.run(run_test())


def test_message_draft_discard_removes_new_autosaved_local_draft(test_db):
    """Verify discarding a new autosaved draft deletes the draft row."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_editor = app.screen.query_one("#message-draft-editor", TextArea)
            draft_subject.value = "Disposable Autosaved"
            draft_editor.load_text("Delete me after autosave")
            await pilot.pause(1.0)

            assert test_db.list_message_drafts()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftDiscardConfirmScreen)

            await pilot.press("d")
            await pilot.pause()
            await pilot.pause()

            assert isinstance(app.screen, MainScreen)
            assert test_db.list_message_drafts() == []

    asyncio.run(run_test())


def test_message_draft_discard_restores_existing_draft_snapshot(test_db):
    """Verify discarding edits on a saved draft restores the original payload."""
    now = datetime.now()
    with test_db.transaction() as conn:
        test_db.upsert_message_draft(
            conn,
            MessageDraft(
                id="draft_existing",
                mode="reply",
                to_addresses="alice@example.com",
                cc_addresses="bob@example.com",
                bcc_addresses="",
                subject="Re: Original",
                body="Original body",
                source_message_id="message_1",
                source_thread_id="thread_1",
                created_at=now,
                updated_at=now,
            ),
        )

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(
                MessageDraftScreen(
                    seed=MessageDraftSeed(mode="draft", draft_id="draft_existing")
                )
            )
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_editor = app.screen.query_one("#message-draft-editor", TextArea)
            draft_subject.value = "Re: Changed"
            draft_editor.load_text("Changed body")
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftDiscardConfirmScreen)

            await pilot.press("d")
            await pilot.pause()
            await pilot.pause()

            restored = test_db.get_message_draft("draft_existing")
            assert restored is not None
            assert restored["subject"] == "Re: Original"
            assert restored["body"] == "Original body"

    asyncio.run(run_test())


def test_message_draft_discard_restores_existing_snapshot_after_autosave(test_db):
    """Verify autosaved edits still discard back to the draft-open snapshot."""
    now = datetime.now()
    with test_db.transaction() as conn:
        test_db.upsert_message_draft(
            conn,
            MessageDraft(
                id="draft_existing_autosave",
                mode="reply",
                to_addresses="alice@example.com",
                cc_addresses="",
                bcc_addresses="",
                subject="Re: Baseline",
                body="Baseline body",
                source_message_id="message_1",
                source_thread_id="thread_1",
                created_at=now,
                updated_at=now,
            ),
        )

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(
                MessageDraftScreen(
                    seed=MessageDraftSeed(
                        mode="draft", draft_id="draft_existing_autosave"
                    )
                )
            )
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            draft_subject = app.screen.query_one("#draft-subject", Input)
            draft_editor = app.screen.query_one("#message-draft-editor", TextArea)
            draft_subject.value = "Re: Autosaved Change"
            draft_editor.load_text("Autosaved change")
            await pilot.pause(1.0)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MessageDraftDiscardConfirmScreen)

            await pilot.press("d")
            await pilot.pause()
            await pilot.pause()

            restored = test_db.get_message_draft("draft_existing_autosave")
            assert restored is not None
            assert restored["subject"] == "Re: Baseline"
            assert restored["body"] == "Baseline body"

    asyncio.run(run_test())


def test_compose_preview_toggle_binding_switches_between_tabs(test_db):
    """Verify compose preview toggle binding switches edit and preview tabs."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            assert isinstance(app.screen, MessageDraftScreen)
            tabs = app.screen.query_one("#message-draft-body-tabs", TabbedContent)
            assert tabs.active == "draft-edit"

            await pilot.press(settings.keybindings.compose_preview_toggle)
            await pilot.pause()
            assert tabs.active == "draft-preview"

            await pilot.press("f2")
            await pilot.pause()
            assert tabs.active == "draft-edit"

            await pilot.press("f2")
            await pilot.pause()
            assert tabs.active == "draft-preview"

    asyncio.run(run_test())


def test_draft_thread_row_shows_drafts_label_chip(test_db):
    """Verify draft threads surface Drafts as a label chip."""
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
            chips = row.query_one(".thread-label-chips", Static)
            assert "Drafts" in str(chips.render_line(0))

    asyncio.run(run_test())


def test_thread_row_draft_chip_updates_without_label_switch(test_db):
    """Verify Drafts chip appears after revision bump without changing labels."""
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
            chips = thread_row.query_one(".thread-label-chips", Static)
            assert "Drafts" not in str(chips.render_line(0))

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

            app.apply_message_draft_update(
                MessageDraftCloseUpdate(
                    did_change=True,
                    draft_id="draft_refresh",
                    source_thread_id="t_draft_refresh",
                )
            )
            await pilot.pause()
            await pilot.pause()

            updated_row = app.screen.query_one(ThreadRow)
            updated_chips = updated_row.query_one(".thread-label-chips", Static)
            assert "Drafts" in str(updated_chips.render_line(0))

    asyncio.run(run_test())


def test_compose_preview_normalization_preserves_single_newlines_outside_code():
    """Ensure compose preview preserves visual line breaks for plain and quote lines."""
    source = "alpha\nbeta\n\n> one\n> two\n\n```\nline1\nline2\n```"
    preview = to_rendered_markdown_preview(source)
    assert "alpha  \nbeta" in preview
    assert "> one  \n> two" in preview
    assert "```\nline1\nline2\n```" in preview


def test_new_label_modal_creates_nested_user_label(test_db):
    """Verify the labels pane can create one nested custom label via modal."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")
        test_db.upsert_label(conn, "projects", "Projects", "user")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            labels_sidebar.label_list.focus()
            await pilot.pause()

            await pilot.press("n")
            await pilot.pause()

            assert isinstance(app.screen, LabelEditScreen)
            app.screen.query_one("#label-editor-name", Input).value = "Shmail"
            parent_select = app.screen.query_one("#label-editor-parent", Select)
            parent_select.value = "projects"
            await pilot.pause()

            await pilot.press("ctrl+s")
            await pilot.pause()
            await pilot.pause()

            assert isinstance(app.screen, MainScreen)
            created = next(
                label
                for label in test_db.get_labels()
                if label["name"] == "Projects/Shmail"
            )
            item = find_node_by_data(labels_sidebar, created["id"])
            assert item is not None
            assert item.display_name == "Shmail"

    asyncio.run(run_test())


def test_edit_label_modal_updates_selected_user_label(test_db):
    """Verify editing a custom label updates the sidebar and local storage."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")
        test_db.upsert_label(conn, "projects", "Projects", "user")
        test_db.upsert_label(conn, "project_old", "Projects/Old Name", "user")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            label_item = find_node_by_data(labels_sidebar, "project_old")
            assert label_item is not None
            labels_sidebar.label_list.focus()
            await pilot.pause()
            labels_sidebar.label_list.index = labels_sidebar.label_list.children.index(
                label_item
            )
            await pilot.pause()

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, LabelEditScreen)
            name_field = app.screen.query_one("#label-editor-name", Input)
            name_field.value = "Renamed"
            await pilot.pause()

            await pilot.press("ctrl+s")
            await pilot.pause()
            await pilot.pause()

            assert isinstance(app.screen, MainScreen)
            stored = test_db.get_label("project_old")
            assert stored is not None
            assert stored["name"] == "Projects/Renamed"

            renamed_item = find_node_by_data(labels_sidebar, "project_old")
            assert renamed_item is not None
            assert renamed_item.display_name == "Renamed"

    asyncio.run(run_test())


def test_edit_label_on_system_label_opens_color_only_modal(test_db):
    """Verify system labels can open a color-only label editor."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            inbox_item = find_node_by_data(labels_sidebar, "INBOX")
            assert inbox_item is not None
            labels_sidebar.label_list.index = labels_sidebar.label_list.children.index(
                inbox_item
            )
            labels_sidebar.label_list.focus()
            await pilot.pause()

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, LabelEditScreen)
            name_field = app.screen.query_one("#label-editor-name", Input)
            parent_select = app.screen.query_one("#label-editor-parent", Select)
            assert name_field.value == "Inbox"
            assert name_field.disabled is True
            assert parent_select.disabled is True

    asyncio.run(run_test())


def test_label_editor_focus_switch_collapses_previous_color_dropdown(test_db):
    """Verify tabbing between color selects closes the previously open dropdown."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            inbox_item = find_node_by_data(labels_sidebar, "INBOX")
            assert inbox_item is not None
            labels_sidebar.label_list.index = labels_sidebar.label_list.children.index(
                inbox_item
            )
            labels_sidebar.label_list.focus()
            await pilot.pause()

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, LabelEditScreen)
            background_select = app.screen.query_one(
                "#label-editor-background-color", Select
            )
            text_select = app.screen.query_one("#label-editor-text-color", Select)

            background_select.focus()
            background_select.expanded = True
            await pilot.pause()

            text_select.focus()
            await pilot.pause()

            assert background_select.expanded is False

    asyncio.run(run_test())


def test_edit_label_on_virtual_label_updates_color_without_renaming(test_db):
    """Verify virtual app labels support color-only edits through the modal."""

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            labels_sidebar = app.screen.query_one("#labels-sidebar", LabelsSidebar)
            draft_item = find_node_by_data(labels_sidebar, "DRAFT")
            assert draft_item is not None
            labels_sidebar.label_list.index = labels_sidebar.label_list.children.index(
                draft_item
            )
            labels_sidebar.label_list.focus()
            await pilot.pause()

            await pilot.press("e")
            await pilot.pause()

            assert isinstance(app.screen, LabelEditScreen)
            name_field = app.screen.query_one("#label-editor-name", Input)
            assert name_field.disabled is True
            background_select = app.screen.query_one(
                "#label-editor-background-color", Select
            )
            text_select = app.screen.query_one("#label-editor-text-color", Select)
            background_select.value = "#f6c5be"
            text_select.value = "#822111"
            await pilot.pause()

            await pilot.press("ctrl+s")
            await pilot.pause()
            await pilot.pause()

            assert isinstance(app.screen, MainScreen)
            stored = test_db.get_label("DRAFT")
            assert stored is not None
            assert stored["name"] == "Drafts"
            assert stored["background_color"] == "#f6c5be"
            assert stored["text_color"] == "#822111"

    asyncio.run(run_test())


def test_new_label_keybinding_works_from_thread_list_focus(test_db):
    """Verify the global new-label shortcut works while the thread list is focused."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            thread_list = app.screen.query_one("#threads-list", ThreadList)
            thread_list.focus()
            await pilot.pause()

            await pilot.press(settings.keybindings.label_new)
            await pilot.pause()

            assert isinstance(app.screen, LabelEditScreen)

    asyncio.run(run_test())


def test_shortcut_labels_follow_configured_bindings(monkeypatch):
    """Ensure user-facing shortcut labels reflect configured bindings."""
    original_first = settings.keybindings.first
    original_last = settings.keybindings.last
    original_pane_toggle = settings.keybindings.pane_toggle
    original_cycle_forward = settings.keybindings.thread_cycle_forward
    original_label_new = settings.keybindings.label_new
    original_label_edit = settings.keybindings.label_edit
    try:
        settings.keybindings.first = "home"
        settings.keybindings.last = "end"
        settings.keybindings.pane_toggle = "ctrl+l"
        settings.keybindings.thread_cycle_forward = "n"
        settings.keybindings.label_new = "ctrl+n"
        settings.keybindings.label_edit = "ctrl+e"

        labels_shortcuts = LabelsSidebar().get_shortcuts()
        thread_list = ThreadList()
        thread_shortcuts = thread_list.get_shortcuts()
        thread_list.current_label_id = "OUTBOX"
        outbox_shortcuts = thread_list.get_shortcuts()
        message_shortcuts = MessageItem(
            {
                "subject": "Test",
                "sender": "A",
                "recipient_to": "B",
                "timestamp": "2026-03-25T10:00:00+00:00",
            }
        ).get_shortcuts()

        assert ("Home/End", "Jump") in labels_shortcuts
        assert ("Ctrl+l", "Pane") in labels_shortcuts
        assert ("Home/End", "Jump") in thread_shortcuts
        assert ("x", "Cancel Queue") in outbox_shortcuts
        assert ("s", "Sync") in thread_shortcuts
        assert any(shortcut[0].startswith("n/") for shortcut in message_shortcuts)
    finally:
        settings.keybindings.first = original_first
        settings.keybindings.last = original_last
        settings.keybindings.pane_toggle = original_pane_toggle
        settings.keybindings.thread_cycle_forward = original_cycle_forward
        settings.keybindings.label_new = original_label_new
        settings.keybindings.label_edit = original_label_edit

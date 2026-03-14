import asyncio
from datetime import datetime
import pytest
from textual.app import App
from shmail.screens import MainScreen
from shmail.widgets import Sidebar, ThreadList, ThreadRow, LabelItem
from shmail.services.db import DatabaseService
from shmail.models import Message, Label


@pytest.fixture
def test_db(tmp_path):
    """Provides a fresh, isolated database for each test."""
    db_path = tmp_path / "test.db"
    db_service = DatabaseService(db_path=db_path)
    db_service.initialize()
    return db_service


class MockApp(App):
    """A mock app to host the MainScreen for testing."""

    def __init__(self, db_service):
        super().__init__()
        self.db = db_service

    def on_mount(self) -> None:
        self.push_screen(MainScreen())


def find_node_by_data(sidebar, data):
    """Search for a LabelItem with specific data in the ListView."""
    for item in sidebar.label_list.children:
        if isinstance(item, LabelItem) and item.label_id == data:
            return item
    return None


def test_sidebar_labels_load(test_db):
    """Verifies that labels from the database are correctly populated in the sidebar."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")
        test_db.upsert_label(conn, "SENT", "Sent", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            sidebar = app.screen.query_one("#sidebar", Sidebar)
            inbox_item = find_node_by_data(sidebar, "INBOX")
            sent_item = find_node_by_data(sidebar, "SENT")

            assert inbox_item is not None
            assert sent_item is not None
            assert "Inbox" in inbox_item.display_name
            assert "Sent" in sent_item.display_name

    asyncio.run(run_test())


def test_full_navigation_flow(test_db):
    """Verifies that selecting a label in the sidebar correctly updates the conversation list."""
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

            sidebar = app.screen.query_one("#sidebar", Sidebar)
            thread_list = app.screen.query_one("#thread-list", ThreadList)

            work_item = find_node_by_data(sidebar, "WORK")
            assert work_item is not None

            idx = sidebar.label_list.children.index(work_item)
            sidebar.label_list.index = idx
            sidebar.label_list.action_select_cursor()

            await pilot.pause()

            rows = thread_list.query(ThreadRow)
            assert len(rows) == 2

    asyncio.run(run_test())


def test_empty_state_feedback(test_db):
    """Verifies that the UI displays a placeholder message when a label contains no messages."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "TRASH", "Trash", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            sidebar = app.screen.query_one("#sidebar", Sidebar)
            thread_list = app.screen.query_one("#thread-list", ThreadList)

            trash_item = find_node_by_data(sidebar, "TRASH")
            assert trash_item is not None

            idx = sidebar.label_list.children.index(trash_item)
            sidebar.label_list.index = idx
            sidebar.label_list.action_select_cursor()

            await pilot.pause()

            from textual.widgets import Static

            empty_msg = thread_list.query_one("#empty-state-msg", Static)
            assert "No conversations found" in str(empty_msg.render_line(0))

    asyncio.run(run_test())

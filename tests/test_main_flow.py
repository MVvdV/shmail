import asyncio
from datetime import datetime
import pytest
from textual.app import App
from shmail.screens import MainScreen
from shmail.widgets import Sidebar, EmailList, EmailRow
from shmail.services.db import DatabaseService
from shmail.models import Email, Label


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


# --- Integration Tests ---


def test_sidebar_labels_load(test_db):
    """Goal: Verify labels from the DB appear in the Sidebar tree."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "INBOX", "Inbox", "system")
        test_db.upsert_label(conn, "SENT", "Sent", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            # Wait for MainScreen to be pushed and mounted
            await pilot.pause()

            sidebar = app.screen.query_one("#sidebar", Sidebar)
            nodes = sidebar.label_tree.root.children
            assert len(nodes) == 2
            node_labels = [str(node.label) for node in nodes]
            assert "Inbox" in node_labels
            assert "Sent" in node_labels

    asyncio.run(run_test())


def test_full_navigation_flow(test_db):
    """Goal: Verify selecting a label updates the email list."""
    work_label = Label(id="WORK", name="Work", type="user")
    email1 = Email(
        id="e1",
        thread_id="t1",
        subject="Subject 1",
        sender="a@b.com",
        snippet="Snippet 1",
        timestamp=datetime.now(),
        labels=[work_label],
    )
    email2 = Email(
        id="e2",
        thread_id="t2",
        subject="Subject 2",
        sender="c@d.com",
        snippet="Snippet 2",
        timestamp=datetime.now(),
        labels=[work_label],
    )

    with test_db.transaction() as conn:
        test_db.upsert_email(conn, email1)
        test_db.upsert_email(conn, email2)

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            sidebar = app.screen.query_one("#sidebar", Sidebar)
            email_list = app.screen.query_one("#email-list", EmailList)

            work_node = next(
                n for n in sidebar.label_tree.root.children if n.data == "WORK"
            )
            sidebar.label_tree.select_node(work_node)

            # Wait for the refresh logic to finish
            await pilot.pause()

            rows = email_list.query(EmailRow)
            assert len(rows) == 2

    asyncio.run(run_test())


def test_empty_state_feedback(test_db):
    """Goal: Verify the UI shows a message when a label is empty."""
    with test_db.transaction() as conn:
        test_db.upsert_label(conn, "TRASH", "Trash", "system")

    async def run_test():
        app = MockApp(test_db)
        async with app.run_test() as pilot:
            await pilot.pause()

            sidebar = app.screen.query_one("#sidebar", Sidebar)
            email_list = app.screen.query_one("#email-list", EmailList)

            trash_node = next(
                n for n in sidebar.label_tree.root.children if n.data == "TRASH"
            )
            sidebar.label_tree.select_node(trash_node)
            await pilot.pause()

            from textual.widgets import Static

            empty_msg = email_list.query_one("#empty-state-msg", Static)
            # Textual 0.85+ Static text can be accessed via ._renderable or .content
            assert "No emails found" in str(empty_msg.render_line(0))

    asyncio.run(run_test())

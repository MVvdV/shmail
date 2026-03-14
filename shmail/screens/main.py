from typing import TYPE_CHECKING, cast

from shmail.widgets import AppFooter, AppHeader, ThreadList, Sidebar
from .viewer import ThreadViewerScreen
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class MainScreen(Screen):
    """The primary workspace for navigating labels and viewing conversation threads."""

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields layout components for the main workspace."""
        yield AppHeader()
        with Horizontal():
            yield Sidebar(id="sidebar")
            yield ThreadList(id="thread-list")
        yield AppFooter()

    def on_sidebar_label_selected(self, message: Sidebar.LabelSelected) -> None:
        """Handles label selection events and updates the conversation list."""
        thread_list = self.query_one(ThreadList)
        thread_list.load_threads(message.label_id)

    def on_thread_list_thread_selected(
        self, message: ThreadList.ThreadSelected
    ) -> None:
        """Handles conversation selection and displays the entire thread in a modal."""
        self.app.push_screen(ThreadViewerScreen(message.thread_id))

    def watch_focused(self, focused) -> None:
        """Updates the footer shortcuts when the focused widget changes."""
        footer = self.query_one(AppFooter)
        if hasattr(focused, "get_shortcuts"):
            footer.update_shortcuts(focused.get_shortcuts())
        elif focused is not None:
            parent = focused.parent
            while parent is not None:
                if hasattr(parent, "get_shortcuts"):
                    footer.update_shortcuts(parent.get_shortcuts())
                    break
                parent = parent.parent

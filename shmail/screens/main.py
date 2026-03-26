from typing import TYPE_CHECKING, cast

from shmail.config import settings
from shmail.services.label_state import LabelMutationResult
from .label_editor import LabelEditScreen, LabelEditorSeed
from .message_draft import MessageDraftCloseUpdate, MessageDraftScreen, MessageDraftSeed
from shmail.widgets.shortcuts import binding_choices_label, resolve_shortcut_owner
from shmail.widgets import AppFooter, AppHeader, LabelsSidebar, ThreadList
from .thread_messages import ThreadMessagesScreen
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class MainScreen(Screen):
    """The primary workspace for navigating Labels and viewing Threads."""

    BINDINGS = [
        Binding(settings.keybindings.compose, "compose_message", "Compose", show=False),
        Binding(settings.keybindings.label_new, "new_label", "New Label", show=False),
        Binding(
            settings.keybindings.pane_next, "focus_next_pane", "Next Pane", show=False
        ),
        Binding(
            settings.keybindings.pane_prev,
            "focus_prev_pane",
            "Previous Pane",
            show=False,
        ),
    ]

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields layout components for the main workspace."""
        yield AppHeader()
        with Horizontal():
            yield LabelsSidebar(id="labels-sidebar")
            yield ThreadList(id="threads-list")
        yield AppFooter()

    def on_labels_sidebar_label_selected(
        self, message: LabelsSidebar.LabelSelected
    ) -> None:
        """Handles label selection events and updates the Threads list."""
        thread_list = self.query_one(ThreadList)
        thread_list.load_threads(message.label_id)
        thread_list.focus()

    def on_thread_list_thread_selected(
        self, message: ThreadList.ThreadSelected
    ) -> None:
        """Handles conversation selection and displays the entire thread in a modal."""
        self.app.push_screen(ThreadMessagesScreen(message.thread_id))

    def watch_focused(self, focused) -> None:
        """Updates the footer shortcuts when the focused widget changes."""
        self.refresh_footer_shortcuts(focused)

    def refresh_footer_shortcuts(self, focused=None) -> None:
        """Render footer shortcuts for the current main-screen context."""
        if not self.is_mounted:
            return
        footer = self.query_one(AppFooter)
        if not footer.is_mounted:
            return
        owner = resolve_shortcut_owner(self.app.focused if focused is None else focused)
        shortcuts = [
            (binding_choices_label(settings.keybindings.compose, "c"), "Compose"),
            (binding_choices_label(settings.keybindings.label_new, "n"), "New label"),
        ]

        if isinstance(owner, LabelsSidebar):
            shortcuts.extend(owner.get_shortcuts())
        elif isinstance(owner, ThreadList):
            shortcuts.extend(owner.get_shortcuts())
        else:
            shortcuts.append(
                (
                    binding_choices_label(settings.keybindings.pane_next, "Tab"),
                    "Threads",
                )
            )
        footer.update_shortcuts(shortcuts)

    @staticmethod
    def _is_within(widget: Widget | None, ancestor: Widget) -> bool:
        """Return True when widget is the ancestor or its descendant."""
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent if isinstance(current.parent, Widget) else None
        return False

    def _toggle_pane_focus(self) -> None:
        """Toggle focus strictly between Labels and Threads panes."""
        labels_list = self.query_one("#labels-sidebar-list", Widget)
        thread_list = self.query_one("#threads-list", ThreadList)
        focused = self.app.focused

        if self._is_within(focused, labels_list):
            thread_list.focus()
            return

        labels_list.focus()

    def action_focus_next_pane(self) -> None:
        """Move focus to the opposite main pane."""
        self._toggle_pane_focus()

    def action_focus_prev_pane(self) -> None:
        """Move focus to the opposite main pane."""
        self._toggle_pane_focus()

    def action_compose_message(self) -> None:
        """Open a new blank message draft modal from workspace."""
        self.app.push_screen(
            MessageDraftScreen(seed=MessageDraftSeed(mode="new")),
            self._on_message_draft_closed,
        )

    def action_new_label(self) -> None:
        """Open the label editor from anywhere in the main workspace."""
        self.app.push_screen(
            LabelEditScreen(LabelEditorSeed()), self._on_label_editor_closed
        )

    def _on_message_draft_closed(self, update: MessageDraftCloseUpdate | None) -> None:
        """Delegate draft-close refresh handling to the app authority."""
        apply_update = getattr(self.shmail_app, "apply_message_draft_update", None)
        if callable(apply_update):
            apply_update(update)

    def _on_label_editor_closed(self, result: LabelMutationResult | None) -> None:
        """Refresh labels after creating or editing one from the main workspace."""
        if result is None:
            return
        self.query_one(LabelsSidebar).refresh_labels(
            selected_label_id=result.focus_label_id
        )

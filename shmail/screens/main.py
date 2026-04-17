from typing import TYPE_CHECKING, cast

from shmail.config import settings
from .message_actions import LabelSelectionScreen, MoveSelectionScreen
from shmail.services.label_state import LabelMutationResult
from shmail.services.message_draft import MessageDraftService
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
            settings.keybindings.pane_toggle,
            "toggle_pane_focus",
            "Toggle Pane",
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
        thread_list = self.query_one(ThreadList)
        self.app.push_screen(
            ThreadMessagesScreen(
                message.thread_id,
                view_label_id=str(thread_list.current_label_id or "") or None,
            )
        )

    def on_thread_list_thread_mutation_requested(
        self, message: ThreadList.ThreadMutationRequested
    ) -> None:
        """Open or apply thread-scoped local mutation workflows."""
        current_label_id = (
            str(self.query_one(ThreadList).current_label_id or "") or None
        )
        if message.action == "labels":
            initial_selected = self._union_thread_label_ids(message.thread_id)
            self.app.push_screen(
                LabelSelectionScreen(
                    selected_label_ids=initial_selected,
                    title=f"Label {message.thread_count} Messages: {message.subject}",
                    warning=(
                        "Caution: you are overriding labels of individual messages within the thread."
                    ),
                ),
                lambda selection: self._on_thread_labels_selected(
                    message.thread_id,
                    current_label_id,
                    selection,
                    initial_selected,
                ),
            )
            return
        if message.action == "move":
            self.app.push_screen(
                MoveSelectionScreen(current_view_label_id=current_label_id),
                lambda destination: self._on_thread_move_selected(
                    message.thread_id, current_label_id, destination
                ),
            )
            return
        if message.action == "trash":
            self._apply_thread_trash_action(message.thread_id, current_label_id)
            return
        if message.action == "restore":
            self._apply_thread_restore_action(message.thread_id, current_label_id)
            return

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
            (
                binding_choices_label(settings.keybindings.sync, "S"),
                "Sync",
            ),
        ]

        if isinstance(owner, LabelsSidebar):
            shortcuts.extend(owner.get_shortcuts())
        elif isinstance(owner, ThreadList):
            shortcuts.extend(owner.get_shortcuts())
        else:
            shortcuts.append(
                (
                    binding_choices_label(settings.keybindings.pane_toggle, "Tab"),
                    "Pane",
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

    def action_toggle_pane_focus(self) -> None:
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
        """Delegate label-edit refresh handling to the app authority."""
        if result is None:
            return
        apply_update = getattr(self.shmail_app, "apply_label_update", None)
        if callable(apply_update):
            apply_update(result)

    def _union_thread_label_ids(self, thread_id: str) -> list[str]:
        """Return mutable labels present on any provider message in one thread."""
        message_ids = self.shmail_app.repository.list_thread_message_ids(thread_id)
        if not message_ids:
            return []
        mutable_ids = {
            str(label.get("id") or "")
            for label in self.shmail_app.message_mutation.list_mutable_label_choices()
        }
        union: set[str] = set()
        for message_id in message_ids:
            labels = set(self.shmail_app.repository.list_message_label_ids(message_id))
            union |= labels & mutable_ids
        return sorted(union)

    def _on_thread_labels_selected(
        self,
        thread_id: str,
        current_label_id: str | None,
        selection: list[str] | None,
        initial_selected: list[str],
    ) -> None:
        """Apply thread-scoped label selection."""
        if selection is None:
            return
        self.shmail_app.message_mutation.sync_thread_labels_delta(
            account_id=self.shmail_app.email or "",
            provider_key=self.shmail_app.provider_key,
            thread_id=thread_id,
            initial_selected_label_ids=initial_selected,
            selected_label_ids=selection,
            current_view_label_id=current_label_id,
        )
        self._refresh_local_mutation_surfaces(current_label_id)

    def _on_thread_move_selected(
        self,
        thread_id: str,
        current_label_id: str | None,
        destination_label_id: str | None,
    ) -> None:
        """Apply thread-scoped move selection."""
        if destination_label_id is None:
            return
        self.shmail_app.message_mutation.move_thread(
            account_id=self.shmail_app.email or "",
            provider_key=self.shmail_app.provider_key,
            thread_id=thread_id,
            destination_label_id=destination_label_id,
            current_view_label_id=current_label_id,
        )
        self._refresh_local_mutation_surfaces(current_label_id)

    def _apply_thread_trash_action(
        self, thread_id: str, current_label_id: str | None
    ) -> None:
        """Trash or permanently delete a thread locally based on current view."""
        if str(current_label_id or "").upper() == "OUTBOX":
            restored_ids = MessageDraftService(
                self.shmail_app.repository
            ).cancel_queued_sends_in_thread(thread_id)
            if restored_ids:
                self._refresh_local_mutation_surfaces(current_label_id)
                notify = getattr(self.app, "notify", None)
                if callable(notify):
                    notify(
                        "Queued sends cancelled; drafts restored locally.",
                        severity="information",
                    )
            return
        if str(current_label_id or "").upper() == "TRASH":
            self.shmail_app.message_mutation.delete_thread_forever(
                account_id=self.shmail_app.email or "",
                provider_key=self.shmail_app.provider_key,
                thread_id=thread_id,
                current_view_label_id=current_label_id,
            )
        else:
            self.shmail_app.message_mutation.trash_thread(
                account_id=self.shmail_app.email or "",
                provider_key=self.shmail_app.provider_key,
                thread_id=thread_id,
                current_view_label_id=current_label_id,
            )
        self._refresh_local_mutation_surfaces(current_label_id)

    def _apply_thread_restore_action(
        self, thread_id: str, current_label_id: str | None
    ) -> None:
        """Restore a trashed thread back to Inbox locally."""
        self.shmail_app.message_mutation.restore_thread(
            account_id=self.shmail_app.email or "",
            provider_key=self.shmail_app.provider_key,
            thread_id=thread_id,
            current_view_label_id=current_label_id,
        )
        self._refresh_local_mutation_surfaces(current_label_id)

    def _refresh_local_mutation_surfaces(self, current_label_id: str | None) -> None:
        """Refresh thread list and labels after a local-first mutation."""
        apply_update = getattr(self.shmail_app, "apply_local_mail_update", None)
        if callable(apply_update):
            apply_update(current_label_id, [])
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(
                "Updated locally; provider sync remains deferred.",
                severity="information",
            )

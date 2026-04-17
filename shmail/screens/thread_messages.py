from typing import TYPE_CHECKING, cast

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.binding import Binding
from textual.widget import Widget
from textual.worker import WorkerCancelled
from shmail.config import settings
from .message_actions import LabelSelectionScreen, MoveSelectionScreen
from .message_draft import MessageDraftCloseUpdate, MessageDraftScreen, MessageDraftSeed
from shmail.services.message_draft import MessageDraftService
from shmail.services.attachments import AttachmentService
from shmail.widgets.shortcuts import resolve_shortcut_owner
from shmail.widgets import MessageItem, ThreadFooter

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class ThreadMessagesScreen(ModalScreen):
    """A modal screen that displays thread messages using MessageItem cards."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close Thread"),
        Binding(settings.keybindings.reply, "reply", "Reply", show=False),
        Binding(settings.keybindings.reply_all, "reply_all", "Reply All", show=False),
        Binding(settings.keybindings.forward, "forward", "Forward", show=False),
        Binding(
            settings.keybindings.attachment_download,
            "download_attachment",
            "Download Attachment",
            show=False,
        ),
        Binding(
            settings.keybindings.delete_draft,
            "delete_draft",
            "Delete Draft",
            show=False,
        ),
        Binding(settings.keybindings.labels, "edit_labels", "Labels", show=False),
        Binding(settings.keybindings.move, "move_message", "Move", show=False),
        Binding(settings.keybindings.trash, "trash_message", "Trash", show=False),
        Binding(settings.keybindings.restore, "restore_message", "Restore", show=False),
        Binding(
            settings.keybindings.retry_send,
            "retry_send",
            "Retry Send",
            show=False,
        ),
        Binding(settings.keybindings.down, "next_message", "Next Message", show=False),
        Binding(
            settings.keybindings.up, "prev_message", "Previous Message", show=False
        ),
        Binding(
            settings.keybindings.first, "first_message", "First Message", show=False
        ),
        Binding(settings.keybindings.last, "last_message", "Last Message", show=False),
        Binding(
            settings.keybindings.thread_cycle_forward,
            "cycle_forward",
            "Next Focus",
            show=False,
        ),
        Binding(
            settings.keybindings.thread_cycle_backward,
            "cycle_backward",
            "Previous Focus",
            show=False,
        ),
    ]

    def __init__(self, thread_id: str, view_label_id: str | None = None):
        super().__init__(id="thread-viewer-screen")
        self.thread_id = thread_id
        self.view_label_id = view_label_id

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields a container for the conversation thread and a custom footer."""
        with Vertical(id="thread-modal-container", classes="shmail-modal-panel"):
            yield ScrollableContainer(id="thread-stack")
            yield ThreadFooter(id="thread-footer")

    async def on_mount(self) -> None:
        """Fetch thread data in a worker, then mount cards on UI thread."""
        await self._reload_thread_messages()

    async def _reload_thread_messages(self) -> None:
        """Reload thread messages from storage and re-mount message cards."""
        worker = self.run_worker(
            lambda: self.shmail_app.thread_viewer.list_thread_messages(
                self.thread_id, self.view_label_id
            ),
            thread=True,
            exclusive=False,
        )
        try:
            messages = await worker.wait()
        except WorkerCancelled:
            return
        await self._mount_thread_messages(messages)

    def _on_message_draft_closed(self, update: MessageDraftCloseUpdate | None) -> None:
        """Delegate draft-close refresh handling to the app authority."""
        apply_update = getattr(self.shmail_app, "apply_message_draft_update", None)
        if callable(apply_update):
            apply_update(update)

    def reload_thread_if_matching(self, thread_id: str) -> None:
        """Reload this thread when one draft update targets its source thread."""
        if thread_id != self.thread_id:
            return
        self.run_worker(self._reload_thread_messages(), exclusive=False)

    async def _mount_thread_messages(self, messages: list[dict]) -> None:
        """Mount all thread message cards and initialize accordion state."""
        stack = self.query_one("#thread-stack")
        await stack.remove_children()
        mounted_items = [MessageItem(message_data) for message_data in messages]
        mounted_widgets: list[Widget] = list(mounted_items)

        for item in mounted_items:
            item.expanded = False

        if mounted_items:
            await stack.mount_all(mounted_widgets)
            self.call_after_refresh(lambda: self._set_active_message(mounted_items[0]))

    def on_show(self) -> None:
        """Reassert single-expanded accordion state when screen becomes visible."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        target = current if isinstance(current, MessageItem) else message_items[0]
        self._set_active_message(target)

    def action_next_message(self) -> None:
        """Focuses the next message card in the thread stack."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        if current is None:
            message_items[0].focus()
            return

        idx = message_items.index(current)
        if idx < len(message_items) - 1:
            next_item = message_items[idx + 1]
            self._set_active_message(next_item)

    def action_prev_message(self) -> None:
        """Focuses the previous message card in the thread stack."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        if current is None:
            message_items[0].focus()
            return

        idx = message_items.index(current)
        if idx > 0:
            prev_item = message_items[idx - 1]
            self._set_active_message(prev_item)

    def action_first_message(self) -> None:
        """Jumps to the first (latest) message."""
        message_items = self._get_message_items()
        if message_items:
            self._set_active_message(message_items[0])

    def action_last_message(self) -> None:
        """Jumps to the last (oldest) message."""
        message_items = self._get_message_items()
        if message_items:
            self._set_active_message(message_items[-1])

    def action_cycle_forward(self) -> None:
        """Cycles focus forward across cards and inner interactive elements."""
        self._cycle_focus(direction=1)

    def action_cycle_backward(self) -> None:
        """Cycles focus backward across cards and inner interactive elements."""
        self._cycle_focus(direction=-1)

    def _cycle_focus(self, direction: int) -> None:
        """Applies hierarchical traversal for card and interactive element focus."""
        message_items = self._get_message_items()
        if not message_items:
            return

        current = self._resolve_focused_message_item()
        if current is None:
            self._set_active_message(
                message_items[0], enter_internal_direction=direction
            )
            return

        if current.attachment_selector_has_focus():
            if direction < 0:
                current.focus()
                self.watch_focused(current)
                return
            current.focus()
            if current.has_links():
                current.active_link_index = -1
                current.step_link(1)
                self.watch_focused(current)
                return
        elif current.expanded and current.active_link_index >= 0:
            if current.step_link(direction):
                self.watch_focused(current)
                return
            if direction < 0 and current.has_attachment_selector():
                current.focus_attachment_selector(open_overlay=False)
                self.watch_focused(self.focused)
                return
        elif direction > 0 and current.focus_attachment_selector(open_overlay=False):
            self.watch_focused(self.focused)
            return
        elif current.expanded and current.has_links():
            current.active_link_index = -1
            if current.step_link(direction):
                self.watch_focused(current)
                return

        current_idx = message_items.index(current)
        target_idx = (current_idx + direction) % len(message_items)
        target = message_items[target_idx]
        self._set_active_message(target, enter_internal_direction=direction)

    def action_close(self) -> None:
        """Dismisses the modal conversation screen."""
        self.app.pop_screen()

    def action_reply(self) -> None:
        """Open a reply draft from the focused thread message."""
        self._open_compose_from_focus("reply")

    def action_reply_all(self) -> None:
        """Open a reply-all draft from the focused thread message."""
        self._open_compose_from_focus("reply_all")

    def action_forward(self) -> None:
        """Open a forward draft from the focused thread message."""
        self._open_compose_from_focus("forward")

    def open_focused_draft(self) -> None:
        """Resume the focused draft card when one is selected."""
        self._open_compose_from_focus(None)

    def action_delete_draft(self) -> None:
        """Delete the focused draft card when one is selected."""
        message_item = self._resolve_focused_message_item()
        if message_item is None:
            return

        source_data = dict(message_item.message_data)
        if not source_data.get("is_draft") or not source_data.get("draft_id"):
            return

        draft_id = str(source_data.get("draft_id") or "").strip()
        if not draft_id:
            return

        if str(source_data.get("draft_state") or "") == "queued_to_send":
            restored = MessageDraftService(
                self.shmail_app.repository
            ).cancel_queued_send(draft_id)
            if restored is None:
                return
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify(
                    "Queued send cancelled; draft restored locally.",
                    severity="information",
                )
            apply_update = getattr(self.shmail_app, "apply_message_draft_update", None)
            update = MessageDraftCloseUpdate(
                did_change=True,
                draft_id=draft_id,
                source_thread_id=str(source_data.get("thread_id") or "") or None,
                draft_state="editing",
            )
            if callable(apply_update):
                apply_update(update)
            else:
                self.reload_thread_if_matching(update.source_thread_id or "")
            return

        MessageDraftService(self.shmail_app.repository).delete_draft(draft_id)
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify("Draft deleted.", severity="information")

        apply_update = getattr(self.shmail_app, "apply_message_draft_update", None)
        update = MessageDraftCloseUpdate(
            did_change=True,
            draft_id=draft_id,
            source_thread_id=str(source_data.get("thread_id") or "") or None,
        )
        if callable(apply_update):
            apply_update(update)
        else:
            self.reload_thread_if_matching(update.source_thread_id or "")

    def action_edit_labels(self) -> None:
        """Open label add/remove workflow for the focused message."""
        message_item = self._resolve_focused_message_item()
        if message_item is None or bool(message_item.message_data.get("is_draft")):
            return
        message_id = str(message_item.message_data.get("id") or "")
        selected = [
            str(label.get("id") or "")
            for label in list(message_item.message_data.get("labels") or [])
        ]
        self.app.push_screen(
            LabelSelectionScreen(
                selected_label_ids=selected,
                title=f"Label Message: {str(message_item.message_data.get('subject') or '(No Subject)')}",
            ),
            lambda selection: self._on_message_labels_selected(message_id, selection),
        )

    def action_move_message(self) -> None:
        """Open destination-container picker for the focused message."""
        message_item = self._resolve_focused_message_item()
        if message_item is None or bool(message_item.message_data.get("is_draft")):
            return
        self.app.push_screen(
            MoveSelectionScreen(current_view_label_id=self.view_label_id),
            lambda destination: self._on_message_move_selected(
                str(message_item.message_data.get("id") or ""), destination
            ),
        )

    def action_trash_message(self) -> None:
        """Trash or permanently delete the focused message, based on current view."""
        message_item = self._resolve_focused_message_item()
        if message_item is None:
            return
        source_data = dict(message_item.message_data)
        if source_data.get("is_draft"):
            self.action_delete_draft()
            return
        message_id = str(source_data.get("id") or "")
        if not message_id:
            return
        if str(self.view_label_id or "").upper() == "TRASH":
            result = self.shmail_app.message_mutation.delete_message_forever(
                account_id=self.shmail_app.email or "",
                provider_key=self.shmail_app.provider_key,
                message_id=message_id,
                current_view_label_id=self.view_label_id,
            )
            self._apply_message_mutation_result(result, deleted=True)
            return
        result = self.shmail_app.message_mutation.trash_message(
            account_id=self.shmail_app.email or "",
            provider_key=self.shmail_app.provider_key,
            message_id=message_id,
            current_view_label_id=self.view_label_id,
        )
        self._apply_message_mutation_result(result)

    def action_restore_message(self) -> None:
        """Restore the focused trashed message back to Inbox locally."""
        if str(self.view_label_id or "").upper() != "TRASH":
            return
        message_item = self._resolve_focused_message_item()
        if message_item is None or bool(message_item.message_data.get("is_draft")):
            return
        message_id = str(message_item.message_data.get("id") or "")
        if not message_id:
            return
        result = self.shmail_app.message_mutation.restore_message(
            account_id=self.shmail_app.email or "",
            provider_key=self.shmail_app.provider_key,
            message_id=message_id,
            current_view_label_id=self.view_label_id,
        )
        self._apply_message_mutation_result(result)

    def action_retry_send(self) -> None:
        """Retry one failed queued send for the focused outbox draft."""
        message_item = self._resolve_focused_message_item()
        if message_item is None or not bool(message_item.message_data.get("is_draft")):
            return
        if str(message_item.message_data.get("draft_state") or "") != "queued_to_send":
            return
        draft_id = str(message_item.message_data.get("draft_id") or "")
        if not draft_id:
            return
        failed_count = int(message_item.message_data.get("mutation_failed_count") or 0)
        blocked_count = int(
            message_item.message_data.get("mutation_blocked_count") or 0
        )
        if failed_count <= 0 and blocked_count <= 0:
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify("No failed queued send to retry.", severity="warning")
            return
        mutation_ids = self.shmail_app.mutation_log.retry_draft_mutations(draft_id)
        if not mutation_ids:
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify("No failed queued send to retry.", severity="warning")
            return
        self.shmail_app.replay_mutations(mutation_ids)
        self.reload_thread_if_matching(self.thread_id)

    def action_download_attachment(self) -> None:
        """Focus and open the inline attachment selector for the focused message."""
        message_item = self._resolve_focused_message_item()
        if message_item is None or bool(message_item.message_data.get("is_draft")):
            return
        if not message_item.focus_attachment_selector(open_overlay=True):
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify("No attachments available to download.", severity="warning")
                return
        self.watch_focused(self.focused)

    def _open_compose_from_focus(self, action: str | None) -> None:
        """Open or resume compose from the currently focused thread card."""
        message_item = self._resolve_focused_message_item()
        if message_item is None:
            message_items = self._get_message_items()
            if not message_items:
                return
            message_item = message_items[0]

        source_data = dict(message_item.message_data)

        if source_data.get("is_draft") and source_data.get("draft_id"):
            self.app.push_screen(
                MessageDraftScreen(
                    seed=MessageDraftSeed(
                        mode="draft",
                        draft_id=str(source_data.get("draft_id") or ""),
                    )
                ),
                self._on_message_draft_closed,
            )
            return

        if action is None:
            return

        seed = self.shmail_app.thread_viewer.build_message_draft_seed(
            source_data,
            action,
            current_account=self.shmail_app.email or "",
        )
        self.app.push_screen(
            MessageDraftScreen(seed=seed), self._on_message_draft_closed
        )

    def watch_focused(self, focused) -> None:
        """Updates the footer shortcuts when the focused widget changes."""
        footer = self.query_one(ThreadFooter)
        if isinstance(focused, MessageItem):
            footer.update_shortcuts(focused.get_shortcuts())
            return

        owner = resolve_shortcut_owner(focused)
        if owner is not None:
            get_shortcuts = getattr(owner, "get_shortcuts", None)
            if callable(get_shortcuts):
                footer.update_shortcuts(cast(list[tuple[str, str]], get_shortcuts()))

    def _get_message_items(self) -> list[MessageItem]:
        """Returns all MessageItem widgets in the thread stack order."""
        stack = self.query_one("#thread-stack")
        return [child for child in stack.children if isinstance(child, MessageItem)]

    def _on_message_labels_selected(
        self, message_id: str, selection: list[str] | None
    ) -> None:
        """Apply label selection results for one focused message."""
        if selection is None:
            return
        result = self.shmail_app.message_mutation.sync_message_labels(
            account_id=self.shmail_app.email or "",
            provider_key=self.shmail_app.provider_key,
            message_id=message_id,
            selected_label_ids=selection,
            current_view_label_id=self.view_label_id,
        )
        self._apply_message_mutation_result(result)

    def _on_message_move_selected(
        self, message_id: str, destination_label_id: str | None
    ) -> None:
        """Apply move selection result for one focused message."""
        if destination_label_id is None:
            return
        result = self.shmail_app.message_mutation.move_message(
            account_id=self.shmail_app.email or "",
            provider_key=self.shmail_app.provider_key,
            message_id=message_id,
            destination_label_id=destination_label_id,
            current_view_label_id=self.view_label_id,
        )
        self._apply_message_mutation_result(result)

    def _apply_message_mutation_result(self, result, deleted: bool = False) -> None:
        """Refresh thread-view surfaces after one local-first message mutation."""
        apply_update = getattr(self.shmail_app, "apply_local_mail_update", None)
        if callable(apply_update):
            apply_update(self.view_label_id, result.affected_thread_ids)
        if result.thread_became_empty:
            self.app.pop_screen()
            return
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(
                "Message deleted locally."
                if deleted
                else "Message updated locally; provider sync is still deferred.",
                severity="information",
            )

    def _download_attachments(self, message_id: str, attachment_id: str | None) -> None:
        """Download one or all attachments for the provided message."""
        gmail_service = self._resolve_gmail_service()
        try:
            service = AttachmentService(self.shmail_app.repository)
            if attachment_id is None:
                results = service.download_all_attachments(
                    message_id=message_id, gmail_service=gmail_service
                )
            else:
                results = [
                    service.download_attachment(
                        message_id=message_id,
                        attachment_id=attachment_id,
                        gmail_service=gmail_service,
                    )
                ]
        except ValueError as exc:
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify(str(exc), severity="warning")
            return
        except Exception as exc:
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify(f"Attachment download failed: {exc}", severity="error")
            return

        notify = getattr(self.app, "notify", None)
        if callable(notify):
            if len(results) == 1:
                notify(
                    f"Downloaded {results[0].path.name} to {results[0].path.parent}",
                    severity="information",
                )
            else:
                notify(
                    f"Downloaded {len(results)} attachments to {results[0].path.parent}",
                    severity="information",
                )

    def _resolve_gmail_service(self):
        """Return the active Gmail service when one session is connected."""
        sync_service = getattr(self.app, "sync_service", None)
        if sync_service is None:
            return None
        return getattr(sync_service, "gmail", None)

    def _resolve_focused_message_item(self) -> MessageItem | None:
        """Resolves focused context to the owning message card."""
        current = self.focused
        while current is not None and not isinstance(current, MessageItem):
            current = current.parent
        return current

    def on_message_item_expanded_changed(
        self, _event: MessageItem.ExpandedChanged
    ) -> None:
        """Refreshes shortcuts when a message is expanded or collapsed."""
        sender = getattr(_event, "sender", None)
        if isinstance(sender, MessageItem):
            self._set_active_message(sender)
        self.watch_focused(self.focused)

    def on_message_item_attachment_download_requested(
        self, event: MessageItem.AttachmentDownloadRequested
    ) -> None:
        """Download the chosen attachment from one inline message selector."""
        self._download_attachments(event.message_id, event.attachment_id)

    def _set_active_message(
        self,
        target: MessageItem,
        enter_internal_direction: int | None = None,
    ) -> None:
        """Apply accordion behavior and optionally enter target link context."""
        stack = self.query_one("#thread-stack")
        message_items = self._get_message_items()
        if target not in message_items:
            return

        for item in message_items:
            if item is target:
                continue
            item.expanded = False

        target.expanded = True
        target.focus()
        stack.scroll_to_widget(target)

        if enter_internal_direction is None:
            return
        target.active_link_index = -1
        if enter_internal_direction > 0:
            if target.focus_attachment_selector(open_overlay=False):
                return
            if target.has_links():
                target.step_link(1)
            return
        if target.has_links():
            target.step_link(-1)
            return
        target.focus_attachment_selector(open_overlay=False)

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import (
    Input,
    Markdown,
    ListItem,
    ListView,
    Static,
    TabPane,
    TabbedContent,
    Tabs,
    TextArea,
)

from shmail.config import settings
from shmail.models import MessageDraft
from shmail.services.draft_preview import to_rendered_markdown_preview
from shmail.services.message_draft import MessageDraftService
from shmail.services.outbound_message import OutboundMessageService
from shmail.services.parser import MessageParser
from shmail.widgets.shortcuts import (
    ShortcutFooter,
    binding_choices_label,
    movement_pair_label,
)


@dataclass
class MessageDraftSeed:
    """Initial values used to open a draft message editor."""

    mode: str = "new"
    to: str = ""
    cc: str = ""
    bcc: str = ""
    subject: str = ""
    body: str = ""
    source_message_id: str | None = None
    source_thread_id: str | None = None
    draft_id: str | None = None


@dataclass
class MessageDraftCloseUpdate:
    """Summarize draft-session changes for targeted caller refreshes."""

    did_change: bool
    draft_id: str | None
    source_thread_id: str | None
    draft_state: str | None = None


class DraftDiscardActionItem(ListItem):
    """List row representing one discard-confirmation action."""

    def __init__(self, action_value: str, label: str) -> None:
        super().__init__()
        self.add_class("message-draft-discard-action")
        self.action_value = action_value
        self.label = label

    def compose(self) -> ComposeResult:
        """Render discard action label."""
        yield Static(self.label, markup=False)


class MessageDraftDiscardConfirmScreen(ModalScreen[str | None]):
    """Modal confirmation screen for unresolved compose changes."""

    BINDINGS = [
        Binding(settings.keybindings.close, "keep_editing", "Keep Editing", show=False),
        Binding(settings.keybindings.up, "cursor_up", "Previous Action", show=False),
        Binding(settings.keybindings.down, "cursor_down", "Next Action", show=False),
        Binding(
            settings.keybindings.select, "select_action", "Select Action", show=False
        ),
        Binding("ctrl+s", "save_and_close", "Save and Close", show=False),
        Binding("d", "discard", "Discard", show=False),
        Binding("x", "delete_draft", "Delete Draft", show=False),
    ]

    def __init__(self, *, can_delete: bool) -> None:
        super().__init__(id="message-draft-discard-screen")
        self.can_delete = can_delete

    def compose(self) -> ComposeResult:
        """Render save-or-discard confirmation copy, actions, and shortcuts."""
        select_key = binding_choices_label(settings.keybindings.select, "ENTER")
        close_key = binding_choices_label(settings.keybindings.close, "Q/ESC")
        move_key = movement_pair_label(
            settings.keybindings.up, settings.keybindings.down
        )
        with Vertical(
            id="message-draft-discard-modal",
            classes="shmail-picker-panel shmail-picker-panel-warning",
        ):
            yield Static(
                "Save or discard changes?",
                id="message-draft-discard-title",
                classes="shmail-picker-title",
            )
            yield Static(
                "Close now, keep editing, or discard the unsaved changes in this draft.",
                id="message-draft-discard-body",
                classes="shmail-picker-body",
                markup=False,
            )
            yield ListView(
                DraftDiscardActionItem("save", "Save and close"),
                DraftDiscardActionItem("keep", "Keep editing"),
                DraftDiscardActionItem("discard", "Discard edits"),
                *(
                    [DraftDiscardActionItem("delete", "Delete draft")]
                    if self.can_delete
                    else []
                ),
                id="message-draft-discard-list",
                classes="shmail-picker-list",
            )
            with Horizontal(
                id="message-draft-discard-shortcuts",
                classes="shmail-picker-shortcuts",
            ):
                yield Static(select_key, classes="shortcut-key", markup=False)
                yield Static("Choose", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static(move_key, classes="shortcut-key", markup=False)
                yield Static("Nav", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static("CTRL+S", classes="shortcut-key", markup=False)
                yield Static("Save", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static("D", classes="shortcut-key", markup=False)
                yield Static("Discard", classes="shortcut-label", markup=False)
                if self.can_delete:
                    yield Static("•", classes="shortcut-separator")
                    yield Static("X", classes="shortcut-key", markup=False)
                    yield Static("Delete", classes="shortcut-label", markup=False)
                yield Static("•", classes="shortcut-separator")
                yield Static(close_key, classes="shortcut-key", markup=False)
                yield Static("Keep", classes="shortcut-label", markup=False)

    def on_mount(self) -> None:
        """Initialize confirmation focus and default selection."""
        action_list = self.query_one("#message-draft-discard-list", ListView)
        action_list.index = 0
        action_list.focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Dismiss confirmation modal with selected intent."""
        if isinstance(event.item, DraftDiscardActionItem):
            self.dismiss(event.item.action_value)

    def action_cursor_up(self) -> None:
        """Move confirmation selection up."""
        self.query_one("#message-draft-discard-list", ListView).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move confirmation selection down."""
        self.query_one("#message-draft-discard-list", ListView).action_cursor_down()

    def action_select_action(self) -> None:
        """Activate the currently highlighted confirmation action."""
        self.query_one("#message-draft-discard-list", ListView).action_select_cursor()

    def action_keep_editing(self) -> None:
        """Dismiss confirmation and return to compose editor."""
        self.dismiss("keep")

    def action_save_and_close(self) -> None:
        """Dismiss confirmation and persist before closing compose."""
        self.dismiss("save")

    def action_discard(self) -> None:
        """Dismiss confirmation and discard current compose edits."""
        self.dismiss("discard")

    def action_delete_draft(self) -> None:
        """Dismiss confirmation and delete the entire draft."""
        if self.can_delete:
            self.dismiss("delete")


class MessageDraftFooter(ShortcutFooter):
    """Compose footer bar displaying keyboard shortcuts for draft workflow."""

    version_id = "message-draft-version"
    shortcuts_id = "message-draft-shortcuts"
    show_version = False


class MessageDraftScreen(ModalScreen[MessageDraftCloseUpdate | None]):
    """Modal draft editor for composing new messages and thread replies."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close", show=False),
        Binding(
            settings.keybindings.compose_preview_toggle,
            "toggle_body_tab",
            "Toggle Body Tab",
            show=False,
        ),
        Binding("ctrl+s", "save_draft", "Save Draft", show=False),
        Binding(settings.keybindings.send, "send_draft", "Send Draft", show=False),
        Binding(
            settings.keybindings.delete_draft,
            "cancel_queued_send",
            "Cancel Queued Send",
            show=False,
        ),
        Binding(
            settings.keybindings.retry_send,
            "retry_send",
            "Retry Send",
            show=False,
        ),
    ]

    def __init__(self, seed: MessageDraftSeed | None = None) -> None:
        super().__init__(id="message-draft-modal-screen")
        self.seed = seed or MessageDraftSeed()
        self._draft_service: MessageDraftService | None = None
        self._outbound_service: OutboundMessageService | None = None
        self._draft: MessageDraft | None = None
        self._opened_draft_snapshot: MessageDraft | None = None
        self._persisted_draft_snapshot: MessageDraft | None = None
        self._draft_dirty = False
        self._autosave_timer = None
        self._dirty_since_open = False
        self._created_draft_on_open = False
        self._discard_requested = False
        self._suspend_change_tracking = False

    def compose(self) -> ComposeResult:
        """Render message draft fields, body mode tabs, and shortcut footer."""
        with Vertical(id="message-draft-modal-container", classes="shmail-modal-panel"):
            with Vertical(id="message-draft-header-fields"):
                yield Input(
                    self.seed.to,
                    placeholder="To",
                    id="draft-to",
                    classes="shmail-form-input",
                )
                yield Input(
                    self.seed.cc,
                    placeholder="Cc",
                    id="draft-cc",
                    classes="shmail-form-input",
                )
                yield Input(
                    self.seed.bcc,
                    placeholder="Bcc",
                    id="draft-bcc",
                    classes="shmail-form-input",
                )
                yield Input(
                    self.seed.subject,
                    placeholder="Subject",
                    id="draft-subject",
                    classes="shmail-form-input",
                )

            with TabbedContent(initial="draft-edit", id="message-draft-body-tabs"):
                with TabPane("Edit", id="draft-edit"):
                    yield TextArea(
                        self.seed.body,
                        id="message-draft-editor",
                        tab_behavior="focus",
                        classes="shmail-form-textarea",
                    )
                with TabPane("Rendered (Markdown)", id="draft-preview"):
                    yield Markdown(
                        self.seed.body,
                        id="message-draft-preview",
                        parser_factory=lambda: MessageParser.create_markdown_parser(
                            breaks=True
                        ),
                    )

            yield MessageDraftFooter(id="message-draft-footer")

    def on_mount(self) -> None:
        """Initialize focus and footer state after mounting draft modal."""
        repository = getattr(self.app, "repository", None)  # type: ignore[attr-defined]
        if repository is None:
            self.action_close()
            return

        self._draft_service = MessageDraftService(repository)
        self._outbound_service = OutboundMessageService(repository)
        if self.seed.draft_id:
            existing = self._draft_service.get_draft(self.seed.draft_id)
            if existing is not None:
                self._draft = existing

        if self._draft is None:
            self._created_draft_on_open = True
            self._draft = self._draft_service.resolve_or_create_draft(
                mode=self.seed.mode,
                to_addresses=self.seed.to,
                cc_addresses=self.seed.cc,
                bcc_addresses=self.seed.bcc,
                subject=self.seed.subject,
                body=self.seed.body,
                source_message_id=self.seed.source_message_id,
                source_thread_id=self.seed.source_thread_id,
            )
        self._opened_draft_snapshot = self._draft.model_copy(deep=True)
        self._persisted_draft_snapshot = self._draft.model_copy(deep=True)
        self._hydrate_fields_from_draft(self._draft)
        self._apply_editability()
        self._draft_dirty = False
        self._dirty_since_open = False

        try:
            compose_tabs = self.query_one("#message-draft-body-tabs", TabbedContent)
            tabs_widget = compose_tabs.query_one(Tabs)
            tabs_widget.can_focus = False
        except NoMatches:
            pass

        footer = self.query_one(MessageDraftFooter)
        footer.update_shortcuts(self.get_shortcuts())

        if self.seed.mode == "new":
            self.query_one("#draft-to", Input).focus()
            return
        self.query_one("#message-draft-editor", TextArea).focus()

    @on(TextArea.Changed, "#message-draft-editor")
    def on_editor_changed(self, event: TextArea.Changed) -> None:
        """Keep preview tab synchronized with editor body text."""
        preview = self.query_one("#message-draft-preview", Markdown)
        preview.update(to_rendered_markdown_preview(event.text_area.text))
        if self._suspend_change_tracking:
            return
        self._schedule_autosave()

    @on(Input.Changed, "#draft-to")
    @on(Input.Changed, "#draft-cc")
    @on(Input.Changed, "#draft-bcc")
    @on(Input.Changed, "#draft-subject")
    def on_header_field_changed(self, _event: Input.Changed) -> None:
        """Mark draft state dirty when any header field changes."""
        if self._suspend_change_tracking:
            return
        self._schedule_autosave()

    @on(TabbedContent.TabActivated, "#message-draft-body-tabs")
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Route focus to the active body mode widget."""
        if event.pane.id == "draft-edit":
            self.query_one("#message-draft-editor", TextArea).focus()
            return
        self.query_one("#message-draft-preview", Markdown).focus()

    def action_toggle_body_tab(self) -> None:
        """Toggle between compose edit and preview tabs."""
        tabs = self.query_one("#message-draft-body-tabs", TabbedContent)
        tabs.active = "draft-preview" if tabs.active == "draft-edit" else "draft-edit"

    def action_save_draft(self) -> None:
        """Persist draft immediately and confirm save state to the user."""
        self._persist_now(notify_user=True)

    def action_send_draft(self) -> None:
        """Queue the current draft for send without provider replay."""
        if self._draft_service is None or self._outbound_service is None:
            return
        payload = self._collect_draft_payload()
        if payload is None:
            return
        if payload.state == "queued_to_send":
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify("This message is already queued in Outbox.", severity="warning")
            return
        self._draft = self._draft_service.save_draft(payload)
        account_id = str(getattr(self.app, "email", "") or "")
        provider_key = str(getattr(self.app, "provider_key", "gmail") or "gmail")
        result = self._outbound_service.queue_send(
            account_id=account_id,
            provider_key=provider_key,
            draft=self._draft,
        )
        self._draft = self._draft_service.get_draft(result.draft_id)
        self._persisted_draft_snapshot = (
            self._draft.model_copy(deep=True) if self._draft is not None else None
        )
        self._opened_draft_snapshot = self._persisted_draft_snapshot
        self._draft_dirty = False
        self._dirty_since_open = False
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify("Message queued locally in Outbox.", severity="information")
        self.dismiss(
            MessageDraftCloseUpdate(
                did_change=True,
                draft_id=result.draft_id,
                source_thread_id=result.source_thread_id,
                draft_state="queued_to_send",
            )
        )

    def action_cancel_queued_send(self) -> None:
        """Return a queued draft back to editable local-draft state."""
        if self._draft_service is None or self._draft is None:
            return
        if self._draft.state != "queued_to_send":
            return
        restored = self._draft_service.cancel_queued_send(self._draft.id)
        if restored is None:
            return
        self._draft = restored
        self._opened_draft_snapshot = restored.model_copy(deep=True)
        self._persisted_draft_snapshot = restored.model_copy(deep=True)
        self._draft_dirty = False
        self._dirty_since_open = False
        self._hydrate_fields_from_draft(restored)
        self._apply_editability()
        self.query_one(MessageDraftFooter).update_shortcuts(self.get_shortcuts())
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(
                "Queued send cancelled; draft restored locally.", severity="information"
            )

    def action_retry_send(self) -> None:
        """Retry one failed queued send from the draft modal."""
        if self._draft is None or self._draft.state != "queued_to_send":
            return
        status = self._queued_send_status()
        if (
            int(status.get("failed_count") or 0) <= 0
            and int(status.get("blocked_count") or 0) <= 0
        ):
            return
        mutation_log = getattr(self.app, "mutation_log", None)
        replay_mutations = getattr(self.app, "replay_mutations", None)
        if mutation_log is None or not callable(replay_mutations):
            return
        mutation_ids = mutation_log.retry_draft_mutations(self._draft.id)
        if not mutation_ids:
            return
        replay_mutations(mutation_ids)
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify("Retrying queued send.", severity="information")

    def on_unmount(self) -> None:
        """Flush pending autosave and stop timers when screen unmounts."""
        self._stop_autosave_timer()
        if self._discard_requested:
            return
        self._persist_now(notify_user=False)

    def _schedule_autosave(self) -> None:
        """Debounce local draft persistence while user is editing."""
        self._draft_dirty = True
        self._dirty_since_open = True
        self._stop_autosave_timer()
        self._autosave_timer = self.set_timer(0.8, self._flush_autosave)

    def _stop_autosave_timer(self) -> None:
        """Cancel pending autosave timer when present."""
        timer = self._autosave_timer
        if timer is None:
            return
        stop = getattr(timer, "stop", None)
        if callable(stop):
            stop()
        self._autosave_timer = None

    def _flush_autosave(self) -> None:
        """Persist dirty draft state after debounce delay."""
        self._autosave_timer = None
        self._persist_now(notify_user=False)

    def _hydrate_fields_from_draft(self, draft: MessageDraft) -> None:
        """Populate compose widgets from persisted draft payload."""
        self._suspend_change_tracking = True
        try:
            self.query_one("#draft-to", Input).value = draft.to_addresses
            self.query_one("#draft-cc", Input).value = draft.cc_addresses
            self.query_one("#draft-bcc", Input).value = draft.bcc_addresses
            self.query_one("#draft-subject", Input).value = draft.subject

            editor = self.query_one("#message-draft-editor", TextArea)
            editor.load_text(draft.body)
            self.query_one("#message-draft-preview", Markdown).update(
                to_rendered_markdown_preview(draft.body)
            )
        finally:
            self._suspend_change_tracking = False

    def _apply_editability(self) -> None:
        """Toggle compose field editability based on draft lifecycle state."""
        is_editable = not (self._draft and self._draft.state == "queued_to_send")
        for selector in ("#draft-to", "#draft-cc", "#draft-bcc", "#draft-subject"):
            self.query_one(selector, Input).disabled = not is_editable
        self.query_one("#message-draft-editor", TextArea).disabled = not is_editable

    def _collect_draft_payload(self) -> MessageDraft | None:
        """Build updated draft model from current widget field state."""
        if self._draft is None:
            return None
        try:
            return self._draft.model_copy(
                update={
                    "to_addresses": self.query_one("#draft-to", Input).value,
                    "cc_addresses": self.query_one("#draft-cc", Input).value,
                    "bcc_addresses": self.query_one("#draft-bcc", Input).value,
                    "subject": self.query_one("#draft-subject", Input).value,
                    "body": self.query_one("#message-draft-editor", TextArea).text,
                }
            )
        except NoMatches:
            return self._draft

    def _persist_now(self, notify_user: bool) -> None:
        """Persist local draft state if dirty or when explicitly requested."""
        if self._draft_service is None:
            return
        payload = self._collect_draft_payload()
        if payload is None:
            return
        if payload.state == "queued_to_send":
            return
        if not self._draft_dirty and not notify_user:
            return
        self._draft = self._draft_service.save_draft(payload)
        self._persisted_draft_snapshot = self._draft.model_copy(deep=True)
        self._draft_dirty = False
        notify = getattr(self.app, "notify", None)
        if notify_user and callable(notify):
            notify("Draft saved locally.", severity="information")

    def _build_close_update(self) -> MessageDraftCloseUpdate:
        """Build close payload for caller-scoped draft refresh decisions."""
        draft_for_update = self._draft or self._opened_draft_snapshot
        return MessageDraftCloseUpdate(
            did_change=self._has_session_changes(),
            draft_id=draft_for_update.id if draft_for_update is not None else None,
            source_thread_id=(
                draft_for_update.source_thread_id
                if draft_for_update is not None
                else None
            ),
            draft_state=(
                draft_for_update.state if draft_for_update is not None else None
            ),
        )

    def _close_without_confirmation(self) -> None:
        """Persist current draft state and dismiss compose modal."""
        self._stop_autosave_timer()
        self._persist_now(notify_user=False)
        self.dismiss(self._build_close_update())

    def _discard_draft_changes(self) -> None:
        """Remove or revert local draft state for this compose session."""
        if self._draft_service is None:
            self._close_without_confirmation()
            return

        self._stop_autosave_timer()
        self._discard_requested = True
        snapshot = self._opened_draft_snapshot

        if self._created_draft_on_open:
            draft_id = self._draft.id if self._draft is not None else None
            if draft_id:
                self._draft_service.delete_draft(draft_id)
            self._draft = None
        elif snapshot is not None:
            self._draft = self._draft_service.save_draft(snapshot)

        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify("Draft changes discarded.", severity="information")

        self.dismiss(self._build_close_update())

    def _delete_draft(self) -> None:
        """Delete the current persisted draft and dismiss compose."""
        if self._draft_service is None:
            self._close_without_confirmation()
            return

        self._stop_autosave_timer()
        self._discard_requested = True
        draft_for_update = self._draft or self._opened_draft_snapshot
        draft_id = draft_for_update.id if draft_for_update is not None else None
        if draft_id:
            self._draft_service.delete_draft(draft_id)
        self._draft = None

        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify("Draft deleted.", severity="information")

        self.dismiss(
            MessageDraftCloseUpdate(
                did_change=True,
                draft_id=draft_id,
                source_thread_id=(
                    draft_for_update.source_thread_id
                    if draft_for_update is not None
                    else None
                ),
                draft_state=(
                    draft_for_update.state if draft_for_update is not None else None
                ),
            )
        )

    def _should_confirm_discard(self) -> bool:
        """Return True when close should confirm discarding session edits."""
        return self._has_session_changes()

    def _has_session_changes(self) -> bool:
        """Return True when current compose fields differ from the open snapshot."""
        snapshot = self._opened_draft_snapshot
        payload = self._collect_draft_payload()
        if snapshot is None or payload is None:
            return False
        return any(
            [
                payload.to_addresses != snapshot.to_addresses,
                payload.cc_addresses != snapshot.cc_addresses,
                payload.bcc_addresses != snapshot.bcc_addresses,
                payload.subject != snapshot.subject,
                payload.body != snapshot.body,
            ]
        )

    def _on_discard_confirmation_closed(self, action: str | None) -> None:
        """Handle discard confirmation result and restore editor focus as needed."""
        if action == "save":
            self._close_without_confirmation()
            return
        if action == "discard":
            self._discard_draft_changes()
            return
        if action == "delete":
            self._delete_draft()
            return

        try:
            self.query_one("#message-draft-editor", TextArea).focus()
        except NoMatches:
            pass

    def action_close(self) -> None:
        """Dismiss draft modal."""
        if self._should_confirm_discard():
            self.app.push_screen(
                MessageDraftDiscardConfirmScreen(can_delete=self._draft is not None),
                self._on_discard_confirmation_closed,
            )
            return
        self._close_without_confirmation()

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return compose footer shortcut set for current draft workflow."""
        if self._draft is not None and self._draft.state == "queued_to_send":
            shortcuts = [
                (
                    binding_choices_label(settings.keybindings.delete_draft, "X"),
                    "Cancel Queue",
                ),
                (binding_choices_label(settings.keybindings.close, "Q/ESC"), "Close"),
            ]
            status = self._queued_send_status()
            if (
                int(status.get("failed_count") or 0) > 0
                or int(status.get("blocked_count") or 0) > 0
            ):
                shortcuts.insert(
                    1,
                    (
                        binding_choices_label(settings.keybindings.retry_send, "Y"),
                        "Retry Send",
                    ),
                )
            return shortcuts
        return [
            ("CTRL+S", "Save"),
            (
                binding_choices_label(settings.keybindings.send, "CTRL+ENTER"),
                "Queue Send",
            ),
            (
                binding_choices_label(
                    settings.keybindings.compose_preview_toggle, "F2"
                ),
                "Preview",
            ),
            ("TAB", "Next"),
            (binding_choices_label(settings.keybindings.close, "Q/ESC"), "Close"),
        ]

    def _queued_send_status(self) -> dict:
        """Return replay status for the current queued-send draft."""
        if self._draft is None:
            return {}
        repository = getattr(self.app, "repository", None)
        if repository is None:
            return {}
        return repository.get_draft_mutation_summary(self._draft.id)

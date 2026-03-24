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
from shmail.services.parser import MessageParser


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


class MessageDraftFooter(Horizontal):
    """Compose footer bar displaying keyboard shortcuts for draft workflow."""

    def compose(self) -> ComposeResult:
        """Render version and dynamic shortcut row."""
        yield Static("v0.1.0", id="message-draft-version")
        yield Horizontal(id="message-draft-shortcuts")

    def update_shortcuts(self, shortcuts: list[tuple[str, str]]) -> None:
        """Update compose shortcut labels in the footer."""
        container = self.query_one("#message-draft-shortcuts", Horizontal)
        container.remove_children()

        widgets = []
        for index, (key, label) in enumerate(shortcuts):
            if index > 0:
                widgets.append(Static("•", classes="shortcut-separator"))
            widgets.append(Static(key, classes="shortcut-key", markup=False))
            widgets.append(Static(label, classes="shortcut-label", markup=False))

        if widgets:
            container.mount(*widgets)


class MessageDraftScreen(ModalScreen[MessageDraftCloseUpdate | None]):
    """Modal draft editor for composing new messages and thread replies."""

    BINDINGS = [
        Binding(settings.keybindings.close, "close", "Close", show=False),
        Binding(
            settings.keybindings.compose_tab_next,
            "next_body_tab",
            "Next Body Tab",
            show=False,
        ),
        Binding(
            settings.keybindings.compose_tab_prev,
            "prev_body_tab",
            "Previous Body Tab",
            show=False,
        ),
        Binding("ctrl+s", "save_draft", "Save Draft", show=False),
    ]

    def __init__(self, seed: MessageDraftSeed | None = None) -> None:
        super().__init__(id="message-draft-screen")
        self.seed = seed or MessageDraftSeed()
        self._draft_service: MessageDraftService | None = None
        self._draft: MessageDraft | None = None
        self._draft_dirty = False
        self._autosave_timer = None
        self._dirty_since_open = False

    def compose(self) -> ComposeResult:
        """Render message draft fields, body mode tabs, and shortcut footer."""
        with Vertical(id="message-draft-modal-container"):
            with Vertical(id="message-draft-header-fields"):
                yield Input(self.seed.to, placeholder="To", id="draft-to")
                yield Input(self.seed.cc, placeholder="Cc", id="draft-cc")
                yield Input(self.seed.bcc, placeholder="Bcc", id="draft-bcc")
                yield Input(
                    self.seed.subject, placeholder="Subject", id="draft-subject"
                )

            with TabbedContent(initial="draft-edit", id="message-draft-body-tabs"):
                with TabPane("Edit", id="draft-edit"):
                    yield TextArea(
                        self.seed.body,
                        id="message-draft-editor",
                        tab_behavior="focus",
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
        db_service = getattr(self.app, "db", None)  # type: ignore[attr-defined]
        if db_service is None:
            self.action_close()
            return

        self._draft_service = MessageDraftService(db_service)
        if self.seed.draft_id:
            existing = self._draft_service.get_draft(self.seed.draft_id)
            if existing is not None:
                self._draft = existing

        if self._draft is None:
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
        self._hydrate_fields_from_draft(self._draft)

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
        self._schedule_autosave()

    @on(Input.Changed, "#draft-to")
    @on(Input.Changed, "#draft-cc")
    @on(Input.Changed, "#draft-bcc")
    @on(Input.Changed, "#draft-subject")
    def on_header_field_changed(self, _event: Input.Changed) -> None:
        """Mark draft state dirty when any header field changes."""
        self._schedule_autosave()

    @on(TabbedContent.TabActivated, "#message-draft-body-tabs")
    def on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Route focus to the active body mode widget."""
        if event.pane.id == "draft-edit":
            self.query_one("#message-draft-editor", TextArea).focus()
            return
        self.query_one("#message-draft-preview", Markdown).focus()

    def action_next_body_tab(self) -> None:
        """Switch to next compose body tab (Edit/Preview)."""
        tabs = self.query_one("#message-draft-body-tabs", TabbedContent)
        tabs.active = "draft-preview" if tabs.active == "draft-edit" else "draft-edit"

    def action_prev_body_tab(self) -> None:
        """Switch to previous compose body tab (Edit/Preview)."""
        self.action_next_body_tab()

    def action_save_draft(self) -> None:
        """Persist draft immediately and confirm save state to the user."""
        self._persist_now(notify_user=True)

    def on_unmount(self) -> None:
        """Flush pending autosave and stop timers when screen unmounts."""
        self._stop_autosave_timer()
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
        self.query_one("#draft-to", Input).value = draft.to_addresses
        self.query_one("#draft-cc", Input).value = draft.cc_addresses
        self.query_one("#draft-bcc", Input).value = draft.bcc_addresses
        self.query_one("#draft-subject", Input).value = draft.subject

        editor = self.query_one("#message-draft-editor", TextArea)
        editor.load_text(draft.body)
        self.query_one("#message-draft-preview", Markdown).update(
            to_rendered_markdown_preview(draft.body)
        )

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
        if not self._draft_dirty and not notify_user:
            return
        self._draft = self._draft_service.save_draft(payload)
        self._draft_dirty = False
        notify = getattr(self.app, "notify", None)
        if notify_user and callable(notify):
            notify("Draft saved locally.", severity="information")

    def _build_close_update(self) -> MessageDraftCloseUpdate:
        """Build close payload for caller-scoped draft refresh decisions."""
        return MessageDraftCloseUpdate(
            did_change=self._dirty_since_open,
            draft_id=self._draft.id if self._draft is not None else None,
            source_thread_id=(
                self._draft.source_thread_id if self._draft is not None else None
            ),
        )

    def action_close(self) -> None:
        """Dismiss draft modal."""
        self._stop_autosave_timer()
        self._persist_now(notify_user=False)
        self.dismiss(self._build_close_update())

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return compose footer shortcut set for current draft workflow."""
        return [
            ("CTRL+S", "Save"),
            ("CTRL+TAB", "Preview"),
            ("S-CTRL+TAB", "Edit"),
            ("TAB", "Next Field"),
            ("Q/ESC", "Close"),
        ]

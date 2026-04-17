"""Thread viewer message card and shortcut footer widgets."""

import json
import webbrowser
from typing import TYPE_CHECKING, cast

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.dom import NoScreen
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Markdown, Select, Static

from shmail.config import settings
from shmail.services.draft_preview import to_rendered_markdown_preview
from shmail.services.link_policy import is_executable_href
from shmail.services.parser import MessageParser
from shmail.services.time import format_compact_datetime
from shmail.widgets.shortcuts import (
    ShortcutFooter,
    binding_choices_label,
    primary_binding_label,
    movement_pair_label,
)

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class MessageItem(Vertical):
    """A focusable card representing a single message within a conversation."""

    can_focus = True

    BINDINGS = [
        Binding(
            settings.keybindings.select, "toggle_expand", "Expand/Collapse", show=False
        ),
    ]

    expanded = reactive(False)
    active_link_index = reactive(-1)

    ATTACHMENT_SELECT_ALL = "__download_all__"

    class AttachmentDownloadRequested(Message):
        """Sent when one attachment or the all-download option is selected."""

        def __init__(self, message_id: str, attachment_id: str | None) -> None:
            self.message_id = message_id
            self.attachment_id = attachment_id
            super().__init__()

    def __init__(self, message_data: dict, **kwargs):
        super().__init__(**kwargs)
        self.add_class("thread-message-card")
        self.message_data = message_data
        self.set_class(bool(self.message_data.get("is_draft")), "-draft")
        raw_body = str(self.message_data.get("body", "*No content*"))
        if bool(self.message_data.get("is_draft")):
            self._body_source = to_rendered_markdown_preview(raw_body)
        else:
            self._body_source = raw_body
        self._body_links = self._load_body_links()
        self._resetting_attachment_select = False

    @property
    def shmail_app(self) -> "ShmailApp":
        """Reference to the main application instance."""
        return cast("ShmailApp", self.app)

    def compose(self) -> ComposeResult:
        """Yields the structured layout for a single message card."""
        subject = self.message_data.get("subject", "(No Subject)")
        sender_name = self.message_data.get("sender_name")
        sender_email = self.message_data.get("sender_address")
        sender = (
            f"{sender_name} <{sender_email}>"
            if sender_name
            else self.message_data.get("sender", "Unknown")
        )
        recipient = self.message_data.get("recipient_to", "Unknown")

        with Vertical(classes="message-header-container"):
            yield Static(subject, classes="message-subject", markup=False)
            yield Static(f"From: {sender}", classes="message-from", markup=False)
            yield Static(f"To: {recipient}", classes="message-to", markup=False)
            yield Static(self._format_date(), classes="message-date")
            yield Static(
                self._render_label_chips(), classes="message-label-chips", markup=True
            )
            if self.has_attachment_selector():
                with Horizontal(classes="message-attachment-row"):
                    yield Static("Attachments", classes="message-attachment-label")
                    yield Select(
                        self._attachment_select_options(),
                        prompt="Choose attachment",
                        allow_blank=True,
                        id="message-attachment-select",
                        classes="message-attachment-select shmail-select-inline",
                    )

        yield Static("", classes="message-interaction-bar", markup=False)
        md = Markdown(
            self._body_source,
            classes="message-markdown",
            parser_factory=self._markdown_parser_factory,
        )
        md.can_focus = False
        md.can_focus_children = False
        yield md

    def _markdown_parser_factory(self):
        """Build markdown parser with optional active-link marker injection."""
        active_link = self.active_link_index if self.expanded else None
        return MessageParser.create_markdown_parser(
            active_link_index=active_link,
            active_marker_prefix="【↗ ",
            active_marker_suffix=" 】",
        )

    def _format_date(self) -> str:
        """Format the message timestamp for compact card display."""
        return format_compact_datetime(self.message_data.get("timestamp", ""))

    def watch_expanded(self, expanded: bool) -> None:
        """Toggles the visibility of the message body."""
        self.set_class(expanded, "-expanded")
        if not self.is_mounted:
            return
        if not expanded:
            self.active_link_index = -1
        self._update_interaction_bar()
        self._update_attachment_selector()
        self._refresh_markdown()

        if self.has_focus:
            self.screen.post_message(self.ExpandedChanged())

    def on_mount(self) -> None:
        """Applies initial expansion-dependent body visibility after mounting."""
        self.call_after_refresh(lambda: self.watch_expanded(self.expanded))

    class ExpandedChanged(Message):
        """Internal notification for shortcut refresh."""

    def on_click(self, event: Click) -> None:
        """Handles mouse interaction to toggle expansion."""
        if self._is_interactive_click(event.widget):
            return
        self.focus()
        self.expanded = not self.expanded

    def action_toggle_expand(self) -> None:
        """Toggles expansion on keyboard activation."""
        if bool(self.message_data.get("is_draft")):
            action = getattr(self.screen, "open_focused_draft", None)
            if callable(action):
                action()
                return
        if self.expanded and self.get_active_link() is not None:
            self.open_active_link()
            return
        self.expanded = not self.expanded

    def has_links(self) -> bool:
        """Returns True when message has links for keyboard interaction."""
        return bool(self._body_links)

    def has_attachment_selector(self) -> bool:
        """Return True when this message exposes attachment download options."""
        return bool(self.message_data.get("attachments")) and not bool(
            self.message_data.get("is_draft")
        )

    def attachment_selector_has_focus(self) -> bool:
        """Return True when the inline attachment selector owns focus."""
        if not self.has_attachment_selector() or self.screen is None:
            return False
        try:
            attachment_select = self.query_one("#message-attachment-select", Select)
        except NoMatches:
            return False
        current = self.screen.focused
        while current is not None:
            if current is attachment_select:
                return True
            current = current.parent
        return False

    def focus_attachment_selector(self, *, open_overlay: bool = False) -> bool:
        """Focus the attachment selector and optionally open its dropdown."""
        if not self.has_attachment_selector() or not self.expanded:
            return False
        try:
            attachment_select = self.query_one("#message-attachment-select", Select)
        except NoMatches:
            return False
        attachment_select.focus()
        if open_overlay:
            attachment_select.action_show_overlay()
        return True

    def step_link(self, direction: int) -> bool:
        """Moves the active link pointer; returns True if a link is selected."""
        if not self.expanded or not self._body_links:
            self.active_link_index = -1
            self._update_interaction_bar()
            return False

        if self.active_link_index < 0:
            self.active_link_index = 0 if direction > 0 else len(self._body_links) - 1
            self._update_interaction_bar()
            return True

        next_index = self.active_link_index + direction
        if 0 <= next_index < len(self._body_links):
            self.active_link_index = next_index
            self._update_interaction_bar()
            return True

        self.active_link_index = -1
        self._update_interaction_bar()
        return False

    def get_active_link(self) -> dict | None:
        """Returns currently selected link payload."""
        if 0 <= self.active_link_index < len(self._body_links):
            return self._body_links[self.active_link_index]
        return None

    def open_active_link(self) -> None:
        """Opens active link when executable, otherwise notifies user."""
        link = self.get_active_link()
        if link is None:
            return
        self._open_href(str(link.get("href", "")).strip())

    def _is_interactive_click(self, widget: Widget | None) -> bool:
        """Determines whether a click originated from an interactive body element."""
        node = widget
        while node is not None and node is not self:
            if isinstance(node, Markdown):
                return True
            if isinstance(node, Static) and node.has_class("message-interaction-bar"):
                return True
            node = node.parent
        return False

    @on(Markdown.LinkClicked)
    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Allows mouse activation of links while preserving safety rules."""
        href = event.href.strip()
        canonical = self._resolve_canonical_link(href)
        if canonical is None:
            prevent_default = getattr(event, "prevent_default", None)
            if callable(prevent_default):
                prevent_default()
            notify = getattr(self.app, "notify", None)
            if callable(notify):
                notify(f"Ignored non-canonical link: {href}", severity="warning")
            return

        self._open_href(str(canonical.get("href", href)).strip())

    def _resolve_canonical_link(self, href: str) -> dict | None:
        """Resolve a clicked href to canonical persisted link payload."""
        href_key = href.strip().lower()
        return next(
            (
                link
                for link in self._body_links
                if str(link.get("href", "")).strip().lower() == href_key
            ),
            None,
        )

    def _open_href(self, href: str) -> None:
        """Open canonical href when executable, otherwise notify user."""
        if is_executable_href(href):
            webbrowser.open(href)
            return

        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(f"Blocked link scheme: {href}", severity="warning")

    def watch_active_link_index(self, _value: int) -> None:
        """Re-renders interaction bar when active link changes."""
        self._update_interaction_bar()
        self._refresh_markdown()

    def _refresh_markdown(self) -> None:
        """Refresh markdown rendering to reflect active link marker state."""
        if not self.is_mounted:
            return
        try:
            markdown = self.query_one(".message-markdown", Markdown)
        except NoMatches:
            return
        markdown.update(self._body_source)

    def _update_interaction_bar(self) -> None:
        """Updates compact interaction summary above markdown body."""
        if not self.is_mounted:
            return

        try:
            bar = self.query_one(".message-interaction-bar", Static)
        except NoMatches:
            return

        if bool(self.message_data.get("is_draft")):
            if self.expanded:
                bar.update("• Draft message ✎ (ENTER/C to continue composing)")
            else:
                bar.update("")
            return

        if not self.expanded:
            bar.update("")
            return

        if not self._body_links:
            bar.update("• No interactive items")
            return

        active = self.get_active_link()
        if active is None:
            bar.update(f"• Links: {len(self._body_links)} (TAB/F to select)")
            return

        idx = self.active_link_index + 1
        label = str(active.get("label", "Open link"))
        blocked = (
            " [blocked]" if not is_executable_href(str(active.get("href", ""))) else ""
        )
        kind = str(active.get("kind", "")).strip()
        kind_hint = f" [{kind}]" if kind else ""
        bar.update(f"• {idx}/{len(self._body_links)}{kind_hint}{blocked} {label}")

    def _update_attachment_selector(self) -> None:
        """Show or hide the attachment selector based on expansion state."""
        if not self.is_mounted or not self.has_attachment_selector():
            return
        try:
            attachment_select = self.query_one("#message-attachment-select", Select)
        except NoMatches:
            return
        attachment_select.display = self.expanded
        label = self.query_one(".message-attachment-label", Static)
        label.display = self.expanded

    def _load_body_links(self) -> list[dict]:
        """Loads persisted body link index from message row payload."""
        raw = self.message_data.get("body_links")
        if not isinstance(raw, str) or not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                links: list[dict] = []
                for entry in parsed:
                    if not isinstance(entry, dict):
                        continue
                    href = " ".join(str(entry.get("href") or "").split())
                    if not href:
                        continue
                    label = " ".join(str(entry.get("label") or "").split())
                    if not label:
                        label = (
                            href.replace("mailto:", "", 1)
                            if href.startswith("mailto:")
                            else href
                        )
                    links.append(
                        {
                            "label": label,
                            "href": href,
                            "executable": is_executable_href(href),
                            "kind": (
                                str(entry.get("kind"))
                                if entry.get("kind")
                                in {"image_link", "mailto", "web", "placeholder"}
                                else (
                                    "mailto"
                                    if href.lower().startswith("mailto:")
                                    else ("placeholder" if href == "#" else "web")
                                )
                            ),
                        }
                    )
                return links
        except Exception:
            return []
        return []

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Return the active shortcuts for the message card."""
        select_key = binding_choices_label(settings.keybindings.select, "ENTER")
        reply_key = binding_choices_label(settings.keybindings.reply, "R")
        reply_all_key = binding_choices_label(settings.keybindings.reply_all, "A")
        forward_key = binding_choices_label(settings.keybindings.forward, "F")
        delete_key = binding_choices_label(settings.keybindings.delete_draft, "X")
        labels_key = binding_choices_label(settings.keybindings.labels, "L")
        trash_key = binding_choices_label(settings.keybindings.trash, "X")
        move_label = binding_choices_label(settings.keybindings.move, "M")
        retry_send_key = binding_choices_label(settings.keybindings.retry_send, "Y")
        sync_key = binding_choices_label(settings.keybindings.sync, "S")
        download_key = binding_choices_label(
            settings.keybindings.attachment_download, "D"
        )
        try:
            current_view = str(getattr(self.screen, "view_label_id", "") or "").upper()
        except NoScreen:
            current_view = ""
        navigation_key = movement_pair_label(
            settings.keybindings.up, settings.keybindings.down
        )
        close_key = binding_choices_label(settings.keybindings.close, "Q/ESC")
        restore_key = binding_choices_label(settings.keybindings.restore, "U")
        cycle_key = (
            f"{primary_binding_label(settings.keybindings.thread_cycle_forward, 'TAB')}/"
            f"{primary_binding_label(settings.keybindings.thread_cycle_backward, 'S+TAB')}"
        )
        has_attachments = bool(self.message_data.get("attachments"))
        if bool(self.message_data.get("is_draft")):
            if str(self.message_data.get("draft_state") or "") == "queued_to_send":
                shortcuts = [
                    (select_key, "View"),
                    (delete_key, "Cancel Queue"),
                    (sync_key, "Sync"),
                    (navigation_key, "Nav"),
                    (cycle_key, "Cycle"),
                    (close_key, "Close"),
                ]
                if (
                    int(self.message_data.get("mutation_failed_count") or 0) > 0
                    or int(self.message_data.get("mutation_blocked_count") or 0) > 0
                ):
                    shortcuts.insert(2, (retry_send_key, "Retry Send"))
                return shortcuts
            return [
                (select_key, "Resume"),
                (delete_key, "Delete"),
                (navigation_key, "Nav"),
                (cycle_key, "Cycle"),
                (close_key, "Close"),
            ]

        enter_label = (
            "Open Link"
            if self.expanded and self.get_active_link()
            else ("Collapse" if self.expanded else "Expand")
        )
        if self.expanded:
            shortcuts = [
                (select_key, "Open" if enter_label == "Open Link" else enter_label),
                (reply_key, "Reply"),
                (reply_all_key, "Reply all"),
                (forward_key, "Forward"),
                (labels_key, "Labels"),
                (move_label, "Move"),
                (trash_key, "Delete" if current_view == "TRASH" else "Trash"),
                (sync_key, "Sync"),
                (navigation_key, "Nav"),
                (cycle_key, "Cycle"),
                (close_key, "Close"),
            ]
            if has_attachments:
                shortcuts.insert(4, (download_key, "Attachments"))
            if current_view == "TRASH":
                shortcuts.insert(7, (restore_key, "Restore"))
            return shortcuts
        shortcuts = [
            (select_key, enter_label),
            (reply_key, "Reply"),
            (reply_all_key, "Reply all"),
            (forward_key, "Forward"),
            (labels_key, "Labels"),
            (move_label, "Move"),
            (trash_key, "Delete" if current_view == "TRASH" else "Trash"),
            (sync_key, "Sync"),
            (navigation_key, "Nav"),
            (cycle_key, "Cycle"),
            (close_key, "Close"),
        ]
        if has_attachments:
            shortcuts.insert(4, (download_key, "Attachments"))
        if current_view == "TRASH":
            shortcuts.insert(7, (restore_key, "Restore"))
        return shortcuts

    def _attachment_select_options(self) -> list[tuple[str, str]]:
        """Return formatted inline attachment options plus one download-all choice."""
        attachments = list(self.message_data.get("attachments") or [])
        if not attachments:
            return []
        size_labels = [self._format_attachment_size(item) for item in attachments]
        filename_width = min(
            44,
            max(len(str(item.get("filename") or "attachment")) for item in attachments),
        )
        options = [
            (
                self._format_attachment_option(
                    str(item.get("filename") or "attachment"),
                    size_labels[index],
                    filename_width,
                ),
                str(item.get("id") or ""),
            )
            for index, item in enumerate(attachments)
        ]
        options.append(("Download all attachments", self.ATTACHMENT_SELECT_ALL))
        return options

    @staticmethod
    def _format_attachment_option(
        filename: str, size_label: str, filename_width: int
    ) -> str:
        """Return one left/right aligned attachment option label."""
        trimmed = (
            filename
            if len(filename) <= filename_width
            else f"{filename[: filename_width - 1]}…"
        )
        return f"{trimmed:<{filename_width}}  {size_label:>10}"

    @staticmethod
    def _format_attachment_size(attachment: dict) -> str:
        """Return one compact human-readable attachment size label."""
        size = int(attachment.get("size_bytes") or 0)
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.0f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    @on(Select.Changed, "#message-attachment-select")
    def on_attachment_selected(self, event: Select.Changed) -> None:
        """Post one download request when the inline selector changes value."""
        if self._resetting_attachment_select:
            return
        value = str(event.value or "").strip()
        if not value:
            return
        message_id = str(self.message_data.get("id") or "")
        attachment_id = None if value == self.ATTACHMENT_SELECT_ALL else value
        self.post_message(self.AttachmentDownloadRequested(message_id, attachment_id))
        self._resetting_attachment_select = True
        event.select.clear()
        self._resetting_attachment_select = False

    def _render_label_chips(self) -> str:
        """Render one compact text-only label strip."""
        failed_count = int(self.message_data.get("mutation_failed_count") or 0)
        blocked_count = int(self.message_data.get("mutation_blocked_count") or 0)
        if str(self.message_data.get("draft_state") or "") == "queued_to_send":
            return "[black on yellow] Outbox [/]"
        labels = list(self.message_data.get("labels") or [])
        chips = [
            self._format_label_chip(label)
            for label in labels
            if str(label.get("id") or "").upper() not in {"UNREAD", "TRASH"}
        ]
        if failed_count > 0 or blocked_count > 0:
            chips.insert(0, "[black on red] ! [/]")
        return " ".join(chip for chip in chips if chip)

    @staticmethod
    def _format_label_chip(label: dict) -> str:
        """Return one inline markup chip for a message label."""
        name = str(label.get("name") or label.get("id") or "").strip()
        if not name:
            return ""
        text = escape(name.split("/")[-1])
        background = str(label.get("background_color") or "").strip()
        foreground = str(label.get("text_color") or "").strip()
        if background and foreground:
            return f"[{foreground} on {background}] {text} [/]"
        return f"[reverse] {text} [/]"


class ThreadFooter(ShortcutFooter):
    """A custom footer for the thread viewer modal displaying shortcuts."""

    version_id = "thread-version"
    shortcuts_id = "thread-shortcuts"
    show_version = False

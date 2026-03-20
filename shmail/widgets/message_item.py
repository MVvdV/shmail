"""Thread viewer message card and shortcut footer widgets."""

from datetime import datetime
import json
import webbrowser
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Markdown, Static

from shmail.services.link_policy import is_executable_href

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class MessageItem(Vertical):
    """A focusable card representing a single message within a conversation."""

    can_focus = True

    BINDINGS = [
        Binding("enter", "toggle_expand", "Expand/Collapse", show=False),
    ]

    expanded = reactive(False)
    active_link_index = reactive(-1)

    def __init__(self, message_data: dict, **kwargs):
        super().__init__(**kwargs)
        self.message_data = message_data
        self._body_links = self._load_body_links()

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

        with Vertical(classes="message-body-container"):
            yield Static("", classes="message-interaction-bar", markup=False)
            md = Markdown(
                self.message_data.get("body", "*No content*"),
                classes="message-markdown",
            )
            md.can_focus = False
            md.can_focus_children = False
            yield md

    def _format_date(self) -> str:
        """Converts database timestamps into user-friendly display strings."""
        raw = self.message_data.get("timestamp", "")
        if not raw:
            return ""
        try:
            clean_raw = str(raw).replace("Z", "+00:00").replace(" ", "T")
            dt = datetime.fromisoformat(clean_raw)
            return dt.strftime("%b %d, %H:%M")
        except Exception:
            return str(raw)[:16].replace("T", ", ").replace(" ", ", ")

    def watch_expanded(self, expanded: bool) -> None:
        """Toggles the visibility of the message body."""
        self.set_class(expanded, "-expanded")
        if not self.is_mounted:
            return
        body = self.query_one(".message-body-container")
        body.display = expanded
        if not expanded:
            self.active_link_index = -1
        self._update_interaction_bar()

        if self.has_focus:
            self.screen.post_message(self.ExpandedChanged())

    def on_mount(self) -> None:
        """Applies initial expansion-dependent body visibility after mounting."""
        self.watch_expanded(self.expanded)

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
        if self.expanded and self.get_active_link() is not None:
            self.open_active_link()
            return
        self.expanded = not self.expanded

    def has_links(self) -> bool:
        """Returns True when message has links for keyboard interaction."""
        return bool(self._body_links)

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

        href = str(link.get("href", "")).strip()
        executable = is_executable_href(href)
        if executable:
            webbrowser.open(href)
            return

        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(f"Blocked link scheme: {href}", severity="warning")

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
        if is_executable_href(href):
            webbrowser.open(href)
            return

        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(f"Blocked link scheme: {href}", severity="warning")

    def watch_active_link_index(self, _value: int) -> None:
        """Re-renders interaction bar when active link changes."""
        self._update_interaction_bar()

    def _update_interaction_bar(self) -> None:
        """Updates compact interaction summary above markdown body."""
        if not self.is_mounted:
            return

        bar = self.query_one(".message-interaction-bar", Static)
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
        bar.update(f"• {idx}/{len(self._body_links)}{blocked} {label}")

    def _load_body_links(self) -> list[dict]:
        """Loads persisted body link index from message row payload."""
        raw = self.message_data.get("body_links")
        if not isinstance(raw, str) or not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                links = [entry for entry in parsed if isinstance(entry, dict)]
                return links
        except Exception:
            return []
        return []

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Returns the active shortcuts for the message card."""
        enter_label = (
            "Open Link"
            if self.expanded and self.get_active_link()
            else ("Collapse" if self.expanded else "Expand")
        )
        if self.expanded:
            return [
                ("ENTER", enter_label),
                ("J/K", "Move"),
                ("TAB/F", "Next Link/Card"),
                ("S-TAB/F", "Prev Link/Card"),
                ("Q/ESC", "Close"),
            ]
        return [
            ("ENTER", enter_label),
            ("J/K", "Move"),
            ("TAB/F", "Next"),
            ("S-TAB/F", "Prev"),
            ("Q/ESC", "Close"),
        ]


class ThreadFooter(Horizontal):
    """A custom footer for the thread viewer modal displaying shortcuts."""

    def compose(self) -> ComposeResult:
        """Yields shortcut information."""
        yield Static("v0.1.0", id="thread-version")
        yield Horizontal(id="thread-shortcuts")

    def update_shortcuts(self, shortcuts: list[tuple[str, str]]) -> None:
        """Updates the displayed shortcuts in the footer."""
        container = self.query_one("#thread-shortcuts", Horizontal)
        container.remove_children()

        new_widgets = []
        for i, (key, label) in enumerate(shortcuts):
            if i > 0:
                new_widgets.append(Static("•", classes="shortcut-separator"))
            new_widgets.append(Static(key, classes="shortcut-key", markup=False))
            new_widgets.append(Static(label, classes="shortcut-label", markup=False))

        if new_widgets:
            container.mount(*new_widgets)

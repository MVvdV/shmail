from datetime import datetime
from typing import TYPE_CHECKING, cast
import webbrowser

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, Markdown
from textual.reactive import reactive

if TYPE_CHECKING:
    from shmail.app import ShmailApp


class MessageItem(Vertical):
    """A focusable card representing a single message within a conversation."""

    can_focus = True

    BINDINGS = [
        Binding("enter", "toggle_expand", "Expand/Collapse", show=False),
        Binding("f", "focus_links", "Follow Links", show=False),
    ]

    expanded = reactive(False)

    def __init__(self, message_data: dict, **kwargs):
        super().__init__(**kwargs)
        self.message_data = message_data

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
            md = Markdown(
                self.message_data.get("body", "*No content*"),
                classes="message-markdown",
            )
            # Enable child focus search for links
            md.can_focus_children = True
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

    def on_mount(self) -> None:
        """Unblocks internal link widgets for keyboard focus."""
        self.call_after_refresh(self._enable_links)

    def _enable_links(self) -> None:
        """Recursively enables focus on all link-like widgets within the Markdown body."""
        md = self.query_one(Markdown)
        for node in md.query("*"):
            if (
                node.__class__.__name__.endswith("Link")
                or node.__class__.__name__ == "MarkdownLink"
            ):
                node.can_focus = True

    def watch_expanded(self, expanded: bool) -> None:
        """Toggles the visibility of the message body."""
        self.set_class(expanded, "-expanded")
        body = self.query_one(".message-body-container")
        body.display = expanded

        if self.has_focus:
            self.screen.post_message(self.ExpandedChanged())

    class ExpandedChanged(Message):
        """Internal notification for shortcut refresh."""

    def on_click(self) -> None:
        """Handles mouse interaction to toggle expansion."""
        self.focus()
        self.expanded = not self.expanded

    def action_toggle_expand(self) -> None:
        """Toggles expansion on keyboard activation."""
        self.expanded = not self.expanded

    def action_focus_links(self) -> None:
        """Jumps focus from the card to the first link in the body."""
        if self.expanded:
            md = self.query_one(Markdown)
            for node in md.query("*"):
                if (
                    node.__class__.__name__.endswith("Link")
                    or node.__class__.__name__ == "MarkdownLink"
                ):
                    node.can_focus = True
                    node.focus()
                    return

    def get_shortcuts(self) -> list[tuple[str, str]]:
        """Returns the active shortcuts for the message card."""
        shortcuts = [
            ("ENTER", "Collapse" if self.expanded else "Expand"),
            ("J/K", "Move"),
            ("Q/ESC", "Close"),
        ]
        if self.expanded:
            shortcuts.insert(1, ("TAB", "Links"))
            shortcuts.insert(2, ("F", "Follow"))
        return shortcuts

    @on(Markdown.LinkClicked)
    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        """Opens selected links in the default system browser."""
        webbrowser.open(event.href)


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

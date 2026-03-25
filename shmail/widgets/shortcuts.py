"""Shared shortcut footer widgets, key labels, and focus helpers."""

from __future__ import annotations

from typing import Iterable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static


Shortcut = tuple[str, str]
APP_VERSION = "v0.1.0"


class ShortcutFooter(Horizontal):
    """Render a version badge with a dynamic shortcut row."""

    version_id = "version"
    shortcuts_id = "shortcuts"
    show_version = True

    def compose(self) -> ComposeResult:
        """Render the footer version and shortcuts container."""
        if self.show_version:
            yield Static(APP_VERSION, id=self.version_id)
        yield Horizontal(id=self.shortcuts_id)

    def update_shortcuts(self, shortcuts: Iterable[Shortcut]) -> None:
        """Render the provided shortcut labels in the footer."""
        container = self.query_one(f"#{self.shortcuts_id}", Horizontal)
        container.remove_children()

        widgets = []
        for index, (key, label) in enumerate(shortcuts):
            if index > 0:
                widgets.append(Static("•", classes="shortcut-separator"))
            widgets.append(Static(key, classes="shortcut-key", markup=False))
            widgets.append(Static(label, classes="shortcut-label", markup=False))

        if widgets:
            container.mount(*widgets)


def resolve_shortcut_owner(widget: Widget | None) -> Widget | None:
    """Return the nearest focused widget or ancestor that exposes shortcuts."""
    current = widget
    while current is not None:
        if hasattr(current, "get_shortcuts"):
            return current
        parent = current.parent
        current = parent if isinstance(parent, Widget) else None
    return None


def primary_binding_label(binding: str, default: str = "") -> str:
    """Return a compact label for the first binding variant."""
    parts = [part.strip() for part in binding.split(",") if part.strip()]
    if not parts:
        return default
    return _normalize_key_label(parts[0])


def binding_choices_label(binding: str, default: str = "") -> str:
    """Return a compact label joining all binding variants."""
    parts = [
        _normalize_key_label(part.strip())
        for part in binding.split(",")
        if part.strip()
    ]
    if not parts:
        return default
    return "/".join(parts)


def movement_pair_label(up_binding: str, down_binding: str) -> str:
    """Return a compact label for paired up/down movement bindings."""
    down = primary_binding_label(down_binding, "DOWN")
    up = primary_binding_label(up_binding, "UP")
    return f"{down}/{up}"


def _normalize_key_label(key: str) -> str:
    """Normalize one Textual binding token into a compact display label."""
    normalized = key.strip().upper()
    replacements = {
        "SHIFT+": "S+",
        "CTRL+": "CTRL+",
        "ESCAPE": "ESC",
        "RETURN": "ENTER",
        "PAGEDOWN": "PGDN",
        "PAGEUP": "PGUP",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized

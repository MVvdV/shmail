"""Shared shortcut footer widgets, key labels, and focus helpers."""

from __future__ import annotations

from typing import Iterable

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import MountError
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
        if not self.is_mounted:
            return
        container = self.query_one(f"#{self.shortcuts_id}", Horizontal)
        if not container.is_mounted:
            return
        container.remove_children()

        widgets = []
        for index, (key, label) in enumerate(shortcuts):
            if index > 0:
                widgets.append(Static("•", classes="shortcut-separator"))
            widgets.append(Static(key, classes="shortcut-key", markup=False))
            widgets.append(Static(label, classes="shortcut-label", markup=False))

        if widgets:
            try:
                container.mount(*widgets)
            except MountError:
                return


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
    normalized = key.strip()
    if not normalized:
        return normalized

    parts = normalized.split("+")
    modifiers = [part for part in parts[:-1] if part]
    key_part = parts[-1]

    modifier_map = {
        "shift": "Shift",
        "ctrl": "Ctrl",
        "alt": "Alt",
        "meta": "Meta",
        "super": "Super",
    }
    key_map = {
        "escape": "Esc",
        "return": "Enter",
        "enter": "Enter",
        "space": "Space",
        "pagedown": "PgDn",
        "pageup": "PgUp",
        "home": "Home",
        "end": "End",
        "tab": "Tab",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "backspace": "Backspace",
        "delete": "Delete",
    }

    display_modifiers = [modifier_map.get(part.lower(), part) for part in modifiers]
    display_key = key_map.get(key_part.lower(), key_part)
    return "+".join([*display_modifiers, display_key])

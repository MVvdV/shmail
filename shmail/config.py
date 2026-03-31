import logging
import tomllib
import tomli_w
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "shmail"
CONFIG_FILE = CONFIG_DIR / "config.toml"
DEFAULT_THEME_LIBRARY_DIR = Path.home() / ".local" / "share" / "omarchy" / "themes"
ACTIVE_THEME_DIR = Path.home() / ".config" / "omarchy" / "current" / "theme"
ACTIVE_THEME_NAME_FILE = Path.home() / ".config" / "omarchy" / "current" / "theme.name"


class UIColors(BaseModel):
    """Base color palette for the terminal user interface."""

    primary: Optional[str] = Field(
        default=None, description="Primary accent color for logos and focus."
    )
    secondary: Optional[str] = Field(
        default=None, description="Secondary accent color for borders and handles."
    )
    accent: Optional[str] = Field(
        default=None, description="Accent color for links and secondary emphasis."
    )
    foreground: Optional[str] = Field(
        default=None, description="Primary foreground color."
    )
    background: Optional[str] = Field(
        default=None, description="Main application background."
    )
    surface: Optional[str] = Field(
        default=None, description="Background for panes, sidebars, and headers."
    )
    panel: Optional[str] = Field(
        default=None, description="Contrast surface for focused or highlighted areas."
    )
    success: Optional[str] = Field(
        default=None, description="Color for success indicators."
    )
    warning: Optional[str] = Field(
        default=None, description="Color for warning indicators."
    )
    error: Optional[str] = Field(
        default=None, description="Color for error indicators."
    )


class Theme(BaseModel):
    """Encapsulates UI and content rendering styles."""

    name: str = Field(default="tokyo-night")
    source: Literal["preset", "current", "directory", "file"] = Field(
        default="preset",
        description="Theme source: shipped preset, active external theme, named theme directory, or explicit TOML file.",
    )
    theme_directory: Optional[str] = Field(
        default=None,
        description="Optional root directory containing named theme folders with `colors.toml`.",
    )
    colors_file: Optional[str] = Field(
        default=None,
        description="Explicit path to a compatible colors.toml file when source='file'.",
    )
    dark: Optional[bool] = Field(
        default=None,
        description="Optional explicit light/dark mode override for runtime theme registration.",
    )
    ui: UIColors = Field(default_factory=UIColors)


class Keybindings(BaseModel):
    """User-customizable keyboard shortcuts."""

    up: str = Field(default="k,up", description="Move selection or scroll up.")
    down: str = Field(default="j,down", description="Move selection or scroll down.")
    close: str = Field(default="q,escape", description="Close current view or overlay.")
    select: str = Field(default="enter", description="Activate the current selection.")
    account: str = Field(
        default="a", description="Focus and open the account selector in the header."
    )
    get_mail: str = Field(
        default="ctrl+g",
        description="Run a user-triggered sync and replay pass.",
    )
    mutations: str = Field(
        default="ctrl+m",
        description="Open the mutation inspector for pending and failed local replay items.",
    )
    compose: str = Field(
        default="c", description="Open message draft composer from supported screens."
    )
    reply: str = Field(default="r", description="Reply to the focused message.")
    reply_all: str = Field(
        default="a", description="Reply to all recipients of the focused message."
    )
    forward: str = Field(default="f", description="Forward the focused message.")
    delete_draft: str = Field(
        default="x", description="Delete the focused draft when available."
    )
    trash: str = Field(
        default="x", description="Trash the focused message or thread when available."
    )
    labels: str = Field(
        default="l",
        description="Open the add/remove labels workflow for the focused item.",
    )
    move: str = Field(
        default="m",
        description="Move the focused message or thread to one destination container.",
    )
    restore: str = Field(
        default="u",
        description="Restore the focused trashed message or thread back to Inbox.",
    )
    retry: str = Field(
        default="ctrl+r",
        description="Retry failed or blocked local replay for the focused message or thread.",
    )
    send: str = Field(
        default="ctrl+enter",
        description="Queue the current draft to send without immediate provider sync.",
    )
    compose_preview_toggle: str = Field(
        default="f2",
        description="Toggle between compose edit and preview tabs with a dedicated compose-safe key.",
    )
    first: str = Field(default="g", description="Jump to the first item in a list.")
    last: str = Field(default="G", description="Jump to the last item in a list.")
    pane_next: str = Field(
        default="tab", description="Move focus to the next primary pane."
    )
    pane_prev: str = Field(
        default="shift+tab", description="Move focus to the previous primary pane."
    )
    resize_narrow: str = Field(
        default="[", description="Shrink the current resizable pane."
    )
    resize_wide: str = Field(
        default="]", description="Expand the current resizable pane."
    )
    label_new: str = Field(
        default="n", description="Create a new custom label from the labels pane."
    )
    label_edit: str = Field(
        default="e", description="Edit the selected custom label from the labels pane."
    )
    label_delete: str = Field(
        default="ctrl+shift+d",
        description="Delete the current custom label from the label editor.",
    )
    thread_cycle_forward: str = Field(
        default="tab",
        description="Advance through thread card and link focus targets.",
    )
    thread_cycle_backward: str = Field(
        default="shift+tab",
        description="Reverse through thread card and link focus targets.",
    )


class Settings(BaseModel):
    """Root configuration model for the Shmail application."""

    email: Optional[str] = Field(
        default=None, description="The authorized Gmail address."
    )
    theme: Theme = Field(default_factory=Theme)
    refresh_interval: int = Field(
        default=300, description="Seconds between background synchronizations."
    )
    max_messages_cached: int = Field(
        default=500,
        description="Maximum number of messages to store in the local cache.",
    )
    keybindings: Keybindings = Field(default_factory=Keybindings)


def default_theme() -> Theme:
    """Return the default theme based on local active-theme availability."""
    if (ACTIVE_THEME_DIR / "colors.toml").exists():
        active_name = "current"
        if ACTIVE_THEME_NAME_FILE.exists():
            active_name = ACTIVE_THEME_NAME_FILE.read_text().strip() or active_name
        return Theme(name=active_name, source="current")
    return Theme(name="tokyo-night", source="preset")


def normalize_theme_source(raw: object) -> str:
    """Normalize legacy theme source names into the current model."""
    text = str(raw or "preset").strip().lower()
    aliases = {
        "omarchy-current": "current",
        "omarchy-theme": "directory",
    }
    return aliases.get(text, text or "preset")


def load_settings() -> Settings:
    """Loads application settings from the TOML configuration file."""
    if not CONFIG_FILE.exists():
        settings = Settings(theme=default_theme())
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(settings.model_dump(), f)
        return settings

    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)

        if isinstance(data.get("theme"), str):
            data["theme"] = Theme(name=data["theme"], source="preset").model_dump(
                exclude_none=True
            )
        elif isinstance(data.get("theme"), dict):
            theme_data = dict(data["theme"])
            theme_data["source"] = normalize_theme_source(theme_data.get("source"))
            data["theme"] = theme_data

        keybinding_data = data.get("keybindings")
        if isinstance(keybinding_data, dict):
            keybinding_data = dict(keybinding_data)
            if (
                "compose_preview_toggle" not in keybinding_data
                and "compose_tab_next" in keybinding_data
            ):
                toggle_parts = [str(keybinding_data["compose_tab_next"])]
                previous = keybinding_data.get("compose_tab_prev")
                if previous:
                    toggle_parts.append(str(previous))
                keybinding_data["compose_preview_toggle"] = ",".join(toggle_parts)
            keybinding_data.pop("compose_tab_next", None)
            keybinding_data.pop("compose_tab_prev", None)
            if keybinding_data.get("thread_cycle_forward") == "tab,f":
                keybinding_data["thread_cycle_forward"] = "tab"
            if keybinding_data.get("thread_cycle_backward") == "shift+tab,F":
                keybinding_data["thread_cycle_backward"] = "shift+tab"
            data["keybindings"] = keybinding_data

        return Settings(**data)
    except Exception as exc:
        logger.warning(
            "Failed to load config from %s; using defaults. Error: %s",
            CONFIG_FILE,
            exc,
        )
        return Settings(theme=default_theme())


CONFIG_DIR.mkdir(parents=True, exist_ok=True)
settings = load_settings()

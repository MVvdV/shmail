import tomllib
import tomli_w
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".config" / "shmail"
CONFIG_FILE = CONFIG_DIR / "config.toml"


class UIColors(BaseModel):
    """Base color palette for the terminal user interface."""

    primary: str = Field(
        default="#bb9af7", description="Primary accent color for logos and focus."
    )
    secondary: str = Field(
        default="#7aa2f7", description="Secondary accent color for borders and handles."
    )
    background: str = Field(
        default="#1a1b26", description="Main application background."
    )
    surface: str = Field(
        default="#24283b", description="Background for panes, sidebars, and headers."
    )
    text: str = Field(default="#a9b1d6", description="Primary text color.")
    success: str = Field(default="#9ece6a", description="Color for success indicators.")
    error: str = Field(default="#f7768e", description="Color for error indicators.")


class Theme(BaseModel):
    """Encapsulates UI and content rendering styles."""

    name: str = Field(default="tokyo-night")
    ui: UIColors = Field(default_factory=UIColors)


class Keybindings(BaseModel):
    """User-customizable keyboard shortcuts."""

    up: str = Field(default="k,up", description="Move selection or scroll up.")
    down: str = Field(default="j,down", description="Move selection or scroll down.")
    close: str = Field(default="q,escape", description="Close current view or overlay.")
    select: str = Field(default="enter", description="Activate the current selection.")


class Settings(BaseModel):
    """Root configuration model for the Shmail application."""

    email: Optional[str] = Field(
        default=None, description="The authorized Gmail address."
    )
    theme: Theme = Field(default_factory=Theme)
    refresh_interval: int = Field(
        default=300, description="Seconds between background synchronizations."
    )
    max_emails_cached: int = Field(
        default=500,
        description="Maximum number of messages to store in the local cache.",
    )
    keybindings: Keybindings = Field(default_factory=Keybindings)


def load_settings() -> Settings:
    """Loads application settings from the TOML configuration file."""
    if not CONFIG_FILE.exists():
        settings = Settings()
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(settings.model_dump(), f)
        return settings

    try:
        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)

        if isinstance(data.get("theme"), str):
            data["theme"] = Theme(name=data["theme"]).model_dump()

        return Settings(**data)
    except Exception:
        return Settings()


CONFIG_DIR.mkdir(parents=True, exist_ok=True)
settings = load_settings()

import tomllib
import tomli_w
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

# 1. Define where our data lives
CONFIG_DIR = Path.home() / ".config" / "shmail"
CONFIG_FILE = CONFIG_DIR / "config.toml"


# 2. Define our Settings model
class Settings(BaseModel):
    email: Optional[str] = Field(default=None, description="The user's Gmail address")
    theme: str = Field(default="charming", description="The UI theme name")
    refresh_interval: int = Field(
        default=300, description="Seconds between Gmail syncs"
    )
    max_emails_cached: int = Field(
        default=500, description="Number of emails to store locally"
    )


def load_settings() -> Settings:
    """Loads settings from the TOML file, or creates it with defaults if missing."""
    if not CONFIG_FILE.exists():
        settings = Settings()
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(settings.model_dump(), f)
        return settings

    with open(CONFIG_FILE, "rb") as f:
        data = tomllib.load(f)
    return Settings(**data)


# 3. Initialization
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
settings = load_settings()

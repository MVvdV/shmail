"""Theme resolution for shipped presets and compatible palette sources."""

from __future__ import annotations

import tomllib
import logging
from pathlib import Path
from typing import Any

from textual.theme import Theme as TextualTheme

from shmail.config import (
    ACTIVE_THEME_DIR,
    DEFAULT_THEME_LIBRARY_DIR,
    Theme,
    UIColors,
)

USER_THEME_LIBRARY_DIR = Path.home() / ".config" / "omarchy" / "themes"

logger = logging.getLogger(__name__)

STANDARD_THEME_PRESETS: dict[str, dict[str, str]] = {
    "catppuccin-latte": {
        "accent": "#1e66f5",
        "foreground": "#4c4f69",
        "background": "#eff1f5",
        "selection_background": "#dc8a78",
        "color0": "#bcc0cc",
        "color1": "#d20f39",
        "color2": "#40a02b",
        "color3": "#df8e1d",
        "color4": "#1e66f5",
        "color8": "#acb0be",
        "color11": "#df8e1d",
        "color12": "#1e66f5",
        "color14": "#179299",
    },
    "catppuccin": {
        "accent": "#89b4fa",
        "foreground": "#cdd6f4",
        "background": "#1e1e2e",
        "selection_background": "#f5e0dc",
        "color0": "#45475a",
        "color1": "#f38ba8",
        "color2": "#a6e3a1",
        "color3": "#f9e2af",
        "color4": "#89b4fa",
        "color8": "#585b70",
        "color11": "#f9e2af",
        "color12": "#89b4fa",
        "color14": "#94e2d5",
    },
    "ethereal": {
        "accent": "#7d82d9",
        "foreground": "#ffcead",
        "background": "#060B1E",
        "selection_background": "#ffcead",
        "color0": "#060B1E",
        "color1": "#ED5B5A",
        "color2": "#92a593",
        "color3": "#E9BB4F",
        "color4": "#7d82d9",
        "color8": "#6d7db6",
        "color11": "#f7dc9c",
        "color12": "#c2c4f0",
        "color14": "#dfeaf0",
    },
    "everforest": {
        "accent": "#7fbbb3",
        "foreground": "#d3c6aa",
        "background": "#2d353b",
        "selection_background": "#d3c6aa",
        "color0": "#475258",
        "color1": "#e67e80",
        "color2": "#a7c080",
        "color3": "#dbbc7f",
        "color4": "#7fbbb3",
        "color8": "#475258",
        "color11": "#dbbc7f",
        "color12": "#7fbbb3",
        "color14": "#83c092",
    },
    "flexoki-light": {
        "accent": "#205EA6",
        "foreground": "#100F0F",
        "background": "#FFFCF0",
        "selection_background": "#CECDC3",
        "color0": "#100F0F",
        "color1": "#D14D41",
        "color2": "#879A39",
        "color3": "#D0A215",
        "color4": "#205EA6",
        "color8": "#100F0F",
        "color11": "#D0A215",
        "color12": "#4385BE",
        "color14": "#3AA99F",
    },
    "gruvbox": {
        "accent": "#7daea3",
        "foreground": "#d4be98",
        "background": "#282828",
        "selection_background": "#d65d0e",
        "color0": "#3c3836",
        "color1": "#ea6962",
        "color2": "#a9b665",
        "color3": "#d8a657",
        "color4": "#7daea3",
        "color8": "#3c3836",
        "color11": "#d8a657",
        "color12": "#7daea3",
        "color14": "#89b482",
    },
    "hackerman": {
        "accent": "#82FB9C",
        "foreground": "#ddf7ff",
        "background": "#0B0C16",
        "selection_background": "#ddf7ff",
        "color0": "#0B0C16",
        "color1": "#50f872",
        "color2": "#4fe88f",
        "color3": "#50f7d4",
        "color4": "#829dd4",
        "color8": "#6a6e95",
        "color11": "#a4ffec",
        "color12": "#c4d2ed",
        "color14": "#d1fffe",
    },
    "kanagawa": {
        "accent": "#7e9cd8",
        "foreground": "#dcd7ba",
        "background": "#1f1f28",
        "selection_background": "#2d4f67",
        "color0": "#090618",
        "color1": "#c34043",
        "color2": "#76946a",
        "color3": "#c0a36e",
        "color4": "#7e9cd8",
        "color8": "#727169",
        "color11": "#e6c384",
        "color12": "#7fb4ca",
        "color14": "#7aa89f",
    },
    "lumon": {
        "accent": "#f2fcff",
        "foreground": "#d6e2ee",
        "background": "#16242d",
        "selection_background": "#4d9ed3",
        "color0": "#1b2d40",
        "color1": "#4d86b0",
        "color2": "#5e95bc",
        "color3": "#6fa4c9",
        "color4": "#6fb8e3",
        "color8": "#304860",
        "color11": "#9dcae5",
        "color12": "#f2fcff",
        "color14": "#d1eef8",
    },
    "matte-black": {
        "accent": "#e68e0d",
        "foreground": "#bebebe",
        "background": "#121212",
        "selection_background": "#333333",
        "color0": "#333333",
        "color1": "#D35F5F",
        "color2": "#FFC107",
        "color3": "#b91c1c",
        "color4": "#e68e0d",
        "color8": "#8a8a8d",
        "color11": "#b90a0a",
        "color12": "#f59e0b",
        "color14": "#eaeaea",
    },
    "miasma": {
        "accent": "#78824b",
        "foreground": "#c2c2b0",
        "background": "#222222",
        "selection_background": "#78824b",
        "color0": "#000000",
        "color1": "#685742",
        "color2": "#5f875f",
        "color3": "#b36d43",
        "color4": "#78824b",
        "color8": "#666666",
        "color11": "#b36d43",
        "color12": "#78824b",
        "color14": "#c9a554",
    },
    "nord": {
        "accent": "#81a1c1",
        "foreground": "#d8dee9",
        "background": "#2e3440",
        "selection_background": "#4c566a",
        "color0": "#3b4252",
        "color1": "#bf616a",
        "color2": "#a3be8c",
        "color3": "#ebcb8b",
        "color4": "#81a1c1",
        "color8": "#4c566a",
        "color11": "#ebcb8b",
        "color12": "#81a1c1",
        "color14": "#8fbcbb",
    },
    "osaka-jade": {
        "accent": "#509475",
        "foreground": "#C1C497",
        "background": "#111c18",
        "selection_background": "#C1C497",
        "color0": "#23372B",
        "color1": "#FF5345",
        "color2": "#549e6a",
        "color3": "#459451",
        "color4": "#509475",
        "color8": "#53685B",
        "color11": "#E5C736",
        "color12": "#ACD4CF",
        "color14": "#8CD3CB",
    },
    "ristretto": {
        "accent": "#f38d70",
        "foreground": "#e6d9db",
        "background": "#2c2525",
        "selection_background": "#403e41",
        "color0": "#72696a",
        "color1": "#fd6883",
        "color2": "#adda78",
        "color3": "#f9cc6c",
        "color4": "#f38d70",
        "color8": "#948a8b",
        "color11": "#fcd675",
        "color12": "#f8a788",
        "color14": "#9bf1e1",
    },
    "rose-pine": {
        "accent": "#56949f",
        "foreground": "#575279",
        "background": "#faf4ed",
        "selection_background": "#dfdad9",
        "color0": "#f2e9e1",
        "color1": "#b4637a",
        "color2": "#286983",
        "color3": "#ea9d34",
        "color4": "#56949f",
        "color8": "#9893a5",
        "color11": "#ea9d34",
        "color12": "#56949f",
        "color14": "#d7827e",
    },
    "tokyo-night": {
        "accent": "#7aa2f7",
        "foreground": "#a9b1d6",
        "background": "#1a1b26",
        "selection_background": "#7aa2f7",
        "color0": "#32344a",
        "color1": "#f7768e",
        "color2": "#9ece6a",
        "color3": "#e0af68",
        "color4": "#7aa2f7",
        "color8": "#444b6a",
        "color11": "#ff9e64",
        "color12": "#7da6ff",
        "color14": "#0db9d7",
    },
    "vantablack": {
        "accent": "#8d8d8d",
        "foreground": "#ffffff",
        "background": "#0d0d0d",
        "selection_background": "#ffffff",
        "color0": "#0d0d0d",
        "color1": "#a4a4a4",
        "color2": "#b6b6b6",
        "color3": "#cecece",
        "color4": "#8d8d8d",
        "color8": "#fdfdfd",
        "color11": "#cecece",
        "color12": "#8d8d8d",
        "color14": "#b0b0b0",
    },
    "white": {
        "accent": "#6e6e6e",
        "foreground": "#000000",
        "background": "#ffffff",
        "selection_background": "#1a1a1a",
        "color0": "#ffffff",
        "color1": "#2a2a2a",
        "color2": "#3a3a3a",
        "color3": "#4a4a4a",
        "color4": "#1a1a1a",
        "color8": "#c0c0c0",
        "color11": "#4a4a4a",
        "color12": "#1a1a1a",
        "color14": "#3e3e3e",
    },
}


class ThemeResolutionError(ValueError):
    """Describe one invalid or unusable theme configuration."""


def build_textual_theme(theme_config: Theme) -> TextualTheme:
    """Resolve one configured theme into a Textual runtime theme."""
    palette = resolve_theme_palette(theme_config)
    dark = (
        theme_config.dark
        if theme_config.dark is not None
        else _is_dark(palette.background)
    )

    return TextualTheme(
        name=theme_config.name or "shmail",
        primary=palette.primary or palette.secondary or palette.foreground or "#7aa2f7",
        secondary=palette.secondary
        or palette.primary
        or palette.foreground
        or "#89b4fa",
        accent=palette.accent or palette.primary or palette.secondary or "#94e2d5",
        foreground=palette.foreground or "#cdd6f4",
        background=palette.background or "#1e1e2e",
        surface=palette.surface or palette.background or "#313244",
        panel=palette.panel or palette.surface or "#45475a",
        success=palette.success or "#a6e3a1",
        warning=palette.warning or "#f9e2af",
        error=palette.error or "#f38ba8",
        dark=dark,
    )


def build_textual_theme_with_fallback(
    theme_config: Theme,
) -> tuple[TextualTheme, str | None]:
    """Build one runtime theme and fall back to the default preset on errors."""
    try:
        return build_textual_theme(theme_config), None
    except ThemeResolutionError as exc:
        fallback_theme = build_textual_theme(Theme(name="tokyo-night", source="preset"))
        warning = (
            f"Theme config warning: {exc}. Falling back to '{fallback_theme.name}'."
        )
        logger.warning(warning)
        return fallback_theme, warning


def resolve_theme_palette(theme_config: Theme) -> UIColors:
    """Resolve one configured theme into a full UI palette."""
    base = _resolve_palette_source(theme_config)
    overrides = theme_config.ui.model_dump(exclude_none=True)
    return UIColors(**{**base.model_dump(exclude_none=True), **overrides})


def _resolve_palette_source(theme_config: Theme) -> UIColors:
    """Load palette values from the configured source."""
    if theme_config.source not in {"preset", "current", "directory", "file"}:
        raise ThemeResolutionError(f"unsupported theme source '{theme_config.source}'")

    if theme_config.source == "file" and theme_config.colors_file:
        file_path = Path(theme_config.colors_file)
        if not file_path.exists():
            raise ThemeResolutionError(f"theme file not found at '{file_path}'")
        return _map_palette_file(_read_colors_file(file_path))

    if theme_config.source == "file":
        raise ThemeResolutionError("theme file source requires 'colors_file'")

    if theme_config.source == "current":
        current_path = ACTIVE_THEME_DIR / "colors.toml"
        if current_path.exists():
            return _map_palette_file(_read_colors_file(current_path))
        raise ThemeResolutionError(f"active theme file not found at '{current_path}'")

    if theme_config.source == "directory":
        for root in _theme_search_roots(theme_config):
            candidate = root / theme_config.name / "colors.toml"
            if candidate.exists():
                return _map_palette_file(_read_colors_file(candidate))
        searched = ", ".join(str(root) for root in _theme_search_roots(theme_config))
        raise ThemeResolutionError(
            f"theme directory '{theme_config.name}' not found in [{searched}]"
        )

    preset = STANDARD_THEME_PRESETS.get(theme_config.name)
    if preset is not None:
        return _map_palette_file(preset)

    if theme_config.source == "preset":
        raise ThemeResolutionError(f"unknown preset theme '{theme_config.name}'")

    return _map_palette_file(STANDARD_THEME_PRESETS["tokyo-night"])


def _read_colors_file(path: Path) -> dict[str, Any]:
    """Read one compatible colors TOML file."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ThemeResolutionError(f"invalid theme file '{path}': {exc}") from exc
    return {str(key): value for key, value in data.items()}


def _theme_search_roots(theme_config: Theme) -> list[Path]:
    """Return the ordered directories searched for named theme folders."""
    roots: list[Path] = []
    if theme_config.theme_directory:
        roots.append(Path(theme_config.theme_directory))
    roots.extend([USER_THEME_LIBRARY_DIR, DEFAULT_THEME_LIBRARY_DIR])
    seen: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.append(root)
    return seen


def _map_palette_file(colors: dict[str, Any]) -> UIColors:
    """Map one compatible palette file into the Shmail/Textual palette model."""
    return UIColors(
        primary=_get_color(colors, "accent", "color4"),
        secondary=_get_color(colors, "color12", "color4", "accent"),
        accent=_get_color(colors, "color14", "color12", "accent"),
        foreground=_get_color(colors, "foreground"),
        background=_get_color(colors, "background"),
        surface=_get_color(colors, "color0", "background"),
        panel=_get_color(colors, "selection_background", "color8", "color0"),
        success=_get_color(colors, "color2"),
        warning=_get_color(colors, "color11", "color3"),
        error=_get_color(colors, "color1"),
    )


def _get_color(colors: dict[str, Any], *keys: str) -> str | None:
    """Return the first non-empty color value from the given keys."""
    for key in keys:
        value = colors.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_dark(background: str | None) -> bool:
    """Return True when the background color is dark."""
    if not background or not background.startswith("#"):
        return True
    raw = background.lstrip("#")
    if len(raw) != 6:
        return True
    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
    return luminance < 140

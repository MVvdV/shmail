from pathlib import Path

import pytest

from shmail.config import Theme, UIColors, normalize_theme_source
from shmail.services.theme import (
    ThemeResolutionError,
    build_textual_theme,
    build_textual_theme_with_fallback,
    resolve_theme_palette,
)


def test_preset_theme_resolves_palette() -> None:
    """Ensure shipped presets resolve into a full UI palette."""
    palette = resolve_theme_palette(Theme(name="nord", source="preset"))

    assert palette.primary == "#81a1c1"
    assert palette.background == "#2e3440"
    assert palette.surface == "#3b4252"
    assert palette.warning == "#ebcb8b"


def test_file_theme_applies_partial_overrides(tmp_path: Path) -> None:
    """Ensure compatible colors files can be overridden per token."""
    colors_file = tmp_path / "colors.toml"
    colors_file.write_text(
        "\n".join(
            [
                'accent = "#112233"',
                'foreground = "#ddeeff"',
                'background = "#111111"',
                'selection_background = "#222222"',
                'color0 = "#1b1b1b"',
                'color1 = "#ff0000"',
                'color2 = "#00ff00"',
                'color3 = "#ffff00"',
                'color4 = "#334455"',
                'color8 = "#444444"',
                'color11 = "#ffaa00"',
                'color12 = "#556677"',
                'color14 = "#778899"',
            ]
        )
    )

    theme = Theme(
        name="custom-file",
        source="file",
        colors_file=str(colors_file),
        ui=UIColors(warning="#123456"),
    )
    textual_theme = build_textual_theme(theme)

    assert textual_theme.primary == "#112233"
    assert textual_theme.secondary == "#556677"
    assert textual_theme.accent == "#778899"
    assert textual_theme.warning == "#123456"


def test_current_theme_source_reads_active_theme_file(
    tmp_path: Path, monkeypatch
) -> None:
    """Ensure the current theme source follows the active external theme file."""
    current_dir = tmp_path / "current" / "theme"
    current_dir.mkdir(parents=True)
    (current_dir / "colors.toml").write_text(
        'accent = "#abcdef"\nforeground = "#eeeeee"\nbackground = "#111111"\nselection_background = "#333333"\ncolor0 = "#1b1b1b"\ncolor1 = "#ff0000"\ncolor2 = "#00ff00"\ncolor3 = "#ffff00"\ncolor4 = "#223344"\ncolor8 = "#555555"\ncolor11 = "#ffaa00"\ncolor12 = "#556677"\ncolor14 = "#778899"\n'
    )
    monkeypatch.setattr("shmail.services.theme.ACTIVE_THEME_DIR", current_dir)

    theme = build_textual_theme(Theme(name="active", source="current"))

    assert theme.primary == "#abcdef"
    assert theme.background == "#111111"


def test_directory_theme_source_searches_named_theme_folder(
    tmp_path: Path, monkeypatch
) -> None:
    """Ensure named theme directories resolve through configured roots."""
    root = tmp_path / "themes"
    named = root / "custom-nord"
    named.mkdir(parents=True)
    (named / "colors.toml").write_text(
        'accent = "#81a1c1"\nforeground = "#d8dee9"\nbackground = "#2e3440"\nselection_background = "#4c566a"\ncolor0 = "#3b4252"\ncolor1 = "#bf616a"\ncolor2 = "#a3be8c"\ncolor3 = "#ebcb8b"\ncolor4 = "#81a1c1"\ncolor8 = "#4c566a"\ncolor11 = "#ebcb8b"\ncolor12 = "#88c0d0"\ncolor14 = "#8fbcbb"\n'
    )
    monkeypatch.setattr("shmail.services.theme.USER_THEME_LIBRARY_DIR", root)
    monkeypatch.setattr(
        "shmail.services.theme.DEFAULT_THEME_LIBRARY_DIR", tmp_path / "missing"
    )

    palette = resolve_theme_palette(Theme(name="custom-nord", source="directory"))

    assert palette.background == "#2e3440"
    assert palette.accent == "#8fbcbb"


def test_light_and_high_contrast_palettes_register_expected_theme_state() -> None:
    """Ensure light and high-contrast presets produce coherent runtime themes."""
    light_theme = build_textual_theme(Theme(name="white", source="preset"))
    high_contrast_theme = build_textual_theme(Theme(name="vantablack", source="preset"))

    assert light_theme.dark is False
    assert light_theme.background == "#ffffff"
    assert high_contrast_theme.dark is True
    assert high_contrast_theme.accent == "#b0b0b0"


def test_legacy_theme_source_aliases_normalize() -> None:
    """Ensure legacy provider-specific theme source names remain supported."""
    assert normalize_theme_source("omarchy-current") == "current"
    assert normalize_theme_source("omarchy-theme") == "directory"


def test_invalid_preset_raises_clear_theme_error() -> None:
    """Ensure unknown preset names fail with a descriptive error."""
    with pytest.raises(ThemeResolutionError, match="unknown preset theme"):
        build_textual_theme(Theme(name="missing-theme", source="preset"))


def test_missing_theme_file_raises_clear_theme_error() -> None:
    """Ensure file-based themes fail clearly when the file is missing."""
    with pytest.raises(ThemeResolutionError, match="theme file not found"):
        build_textual_theme(
            Theme(name="missing-file", source="file", colors_file="/tmp/nope.toml")
        )


def test_malformed_theme_file_raises_clear_theme_error(tmp_path: Path) -> None:
    """Ensure malformed theme files fail with parse context."""
    bad_file = tmp_path / "broken.toml"
    bad_file.write_text("accent = [oops")

    with pytest.raises(ThemeResolutionError, match="invalid theme file"):
        build_textual_theme(
            Theme(name="broken", source="file", colors_file=str(bad_file))
        )


def test_theme_fallback_returns_warning_message() -> None:
    """Ensure runtime theme fallback surfaces one explicit warning."""
    theme, warning = build_textual_theme_with_fallback(
        Theme(name="missing-theme", source="preset")
    )

    assert theme.name == "tokyo-night"
    assert warning is not None
    assert "Theme config warning" in warning

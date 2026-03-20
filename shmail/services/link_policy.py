"""Shared link interaction policy for viewer and parser."""

ALLOWED_SCHEMES = ("http://", "https://", "mailto:")


def is_executable_href(href: str) -> bool:
    """Return True when a href is allowed to open externally."""
    lowered = href.strip().lower()
    return lowered.startswith(ALLOWED_SCHEMES)

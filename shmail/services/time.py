"""Shared helpers for deterministic timestamp normalization and display."""

from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    """Return the current time as a UTC-aware datetime."""
    return datetime.now(timezone.utc)


def parse_utc_datetime(raw: object, *, default: datetime | None = None) -> datetime:
    """Parse one timestamp-like value into a UTC-aware datetime."""
    if isinstance(raw, datetime):
        return _coerce_utc(raw)

    text = str(raw or "").strip()
    if text:
        normalized = text.replace("Z", "+00:00")
        if "T" not in normalized and " " in normalized:
            normalized = normalized.replace(" ", "T", 1)
        try:
            return _coerce_utc(datetime.fromisoformat(normalized))
        except ValueError:
            pass

    if default is not None:
        return _coerce_utc(default)

    return datetime.fromtimestamp(0, tz=timezone.utc)


def to_timestamp(raw: object) -> float:
    """Convert one timestamp-like value into a sortable epoch value."""
    return parse_utc_datetime(raw).timestamp()


def format_compact_datetime(raw: object) -> str:
    """Format one timestamp-like value for compact list and card display."""
    if raw in (None, ""):
        return ""

    parsed = parse_utc_datetime(raw)
    if parsed == datetime.fromtimestamp(0, tz=timezone.utc) and str(
        raw
    ).strip() not in {
        "1970-01-01T00:00:00+00:00",
        "1970-01-01 00:00:00+00:00",
        "0",
    }:
        return str(raw)[:16].replace("T", ", ").replace(" ", ", ")
    return parsed.astimezone().strftime("%b %d, %H:%M")


def _coerce_utc(value: datetime) -> datetime:
    """Normalize one datetime into an aware UTC value."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

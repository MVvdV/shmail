"""Draft preview normalization helpers for markdown-rendered fidelity."""

from __future__ import annotations


def to_rendered_markdown_preview(text: str) -> str:
    """Normalize draft text for markdown rendering without escape artifacts.

    Behavior goals:
    - Preserve regular single-line breaks for non-empty lines.
    - Keep fenced code blocks untouched.
    - Allow markdown renderer to collapse excessive empty lines naturally.
    """

    lines = text.split("\n")
    if not lines:
        return ""

    output: list[str] = []
    in_fence = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            output.append(line)
            continue

        if in_fence:
            output.append(line)
            continue

        if line == "":
            output.append("")
            continue

        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if next_line is not None and next_line != "":
            output.append(f"{line}  ")
        else:
            output.append(line)

    return "\n".join(output)

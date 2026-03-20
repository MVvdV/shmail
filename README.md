## Shmail

Keyboard-first terminal email client built with Textual.

## Development

- Install deps: `uv sync`
- Run app: `uv run python -m shmail.app`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check shmail tests`
- Type check: `uv run pyright`

## Current foundations

- Gmail sync with local SQLite cache (WAL mode)
- Thread viewer with deterministic keyboard link traversal and strict accordion expansion
- HTML-first body conversion via `inscriptis`
- Canonical persisted `body_links` extracted from rendered markdown tokens (order-preserving, no collapse)
- Shared markdown parser contract between extraction and viewer rendering
- Active keyboard link marker rendered inline as `【↗ label 】`
- Long-message active-link traversal keeps selection visible via source-range scroll sync

## Shmail

Keyboard-first terminal email client built with Textual.

## Development

- Install deps: `uv sync`
- Run app: `uv run python -m shmail.app`
- Run tests: `uv run pytest`
- Lint: `uv run ruff check shmail tests`
- Type check: `uv run pyright`

## Configuration

- Config lives in `~/.config/shmail/config.toml`.
- On Omarchy systems, first-run defaults follow the active Omarchy theme from `~/.config/omarchy/current/theme/colors.toml` when available.
- Shmail ships preset support for the standard Omarchy themes: `catppuccin-latte`, `catppuccin`, `ethereal`, `everforest`, `flexoki-light`, `gruvbox`, `hackerman`, `kanagawa`, `lumon`, `matte-black`, `miasma`, `nord`, `osaka-jade`, `ristretto`, `rose-pine`, `tokyo-night`, `vantablack`, and `white`.
- `source = "directory"` searches a named theme folder in `theme.theme_directory` when provided, otherwise in Omarchy-compatible roots such as `~/.config/omarchy/themes` and `~/.local/share/omarchy/themes`.

Preset theme example:

```toml
[theme]
name = "tokyo-night"
source = "preset"
```

Follow the active Omarchy theme automatically:

```toml
[theme]
name = "tokyo-night"
source = "current"
```

Load a named compatible theme directory:

```toml
[theme]
name = "kanagawa"
source = "directory"
```

Load a custom Omarchy-style `colors.toml` and override only selected tokens:

```toml
[theme]
name = "my-theme"
source = "file"
colors_file = "/path/to/colors.toml"

[theme.ui]
warning = "#ffcc66"
panel = "#303446"
```

Keybindings are configurable in the same file:

```toml
[keybindings]
up = "k,up"
down = "j,down"
close = "q,escape"
compose = "c"
reply = "r"
reply_all = "a"
forward = "f"
delete_draft = "x"
first = "g"
last = "G"
pane_next = "tab"
pane_prev = "shift+tab"
resize_narrow = "["
resize_wide = "]"
thread_cycle_forward = "tab"
thread_cycle_backward = "shift+tab"
compose_preview_toggle = "f2"
```

## Engineering standards

- Deterministic keyboard UX is a product contract; focus, traversal, and modal behavior must remain explicit and test-covered.
- Blocking Gmail and SQLite work must run off the UI thread via Textual workers with safe UI-thread handoff.
- Persisted and ordering-critical timestamps must be UTC-aware and normalized through shared helpers.
- Local-first compose and draft flows must remain durable, deterministic, and race-tested.
- Canonical message rendering and `body_links` extraction must stay aligned through one shared markdown contract.
- Public modules, classes, and methods should use semantically correct PEP 257-style docstrings and precise domain naming.
- Dead config/runtime/documentation surfaces should be removed or wired during adjacent refactors.
- Theme styling should be driven by runtime theme variables and Omarchy-compatible palette inputs wherever practical.
- User-visible shortcut copy should derive from configured keybindings instead of diverging hardcoded labels.

## Current hardening priorities

- Fix expired-history fallback reconciliation so local cache truth cannot drift after sync recovery.
- Centralize timestamp normalization and display formatting to remove mixed naive/aware behavior.
- Unify draft/thread/sidebar refresh authority instead of duplicating redraw choreography across views.
- Align runtime theming with configured theme intent.
- Consolidate repeated footer, chooser, focus, and helper patterns to keep the UI layer lean.

## Current foundations

- Gmail sync with local SQLite cache (WAL mode)
- Thread viewer with deterministic keyboard link traversal and strict accordion expansion
- HTML-first body conversion via `inscriptis`
- Canonical persisted `body_links` extracted from rendered markdown tokens (order-preserving, no collapse)
- Shared markdown parser contract between extraction and viewer rendering
- Active keyboard link marker rendered inline as `【↗ label 】`

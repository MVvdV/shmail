# Shmail

Email for people who live on the keyboard.

Shmail is a terminal email client designed to feel focused, fast, and deliberate. It brings together the speed of a TUI, the readability of a modern mail app, and the reliability of local-first state so you can triage, read, and draft without fighting your tools.

This is not trying to be a nostalgic terminal clone. Shmail is aiming for a cleaner kind of terminal mail experience: structured, visually intentional, deterministic in behavior, and comfortable to use for long stretches of real work.

## Why Shmail

- Keyboard-first from the start. Labels, threads, messages, links, and drafts all support deliberate keyboard navigation.
- Calm thread reading. One active message, one clear focus target, one consistent interaction model.
- Local-first drafting. Compose feels immediate, autosaves locally, and gives you explicit control over save, discard, and delete behavior.
- Themeable without hacks. Shmail supports built-in presets, compatible palette files, and environment-aware theme sources.
- Built to feel like a product. The goal is not just capability - it is confidence, clarity, and polish.

## What it feels like

- Fast inbox triage from the terminal
- Predictable thread reading with keyboard link traversal
- Low-flicker updates instead of noisy redraws
- Offline-friendly drafting with durable local state
- A UI that can match your environment instead of forcing one look and feel

## Current scope

Shmail currently focuses on:

- Gmail sync into a local SQLite cache
- keyboard-first thread reading and triage
- local-first compose and draft workflows
- configurable themes and keybindings

Outbound mutation sync-back and broader provider support are planned, but still ahead on the roadmap.

## Get started

Requirements:

- Python `3.14+`
- `uv`

Install and run:

```bash
uv sync
uv run python -m shmail.app
```

## Configuration

Configuration lives in `~/.config/shmail/config.toml`.

### Themes

Shmail supports four theme source modes:

- `preset` - use a built-in named preset
- `current` - follow the active compatible system theme when available
- `directory` - load a named theme from a theme directory
- `file` - load a specific `colors.toml`

Shmail ships support for the standard Omarchy presets:
`catppuccin-latte`, `catppuccin`, `ethereal`, `everforest`, `flexoki-light`, `gruvbox`, `hackerman`, `kanagawa`, `lumon`, `matte-black`, `miasma`, `nord`, `osaka-jade`, `ristretto`, `rose-pine`, `tokyo-night`, `vantablack`, and `white`.

For `source = "directory"`, Shmail searches `theme.theme_directory` when provided, then compatible theme roots such as `~/.config/omarchy/themes` and `~/.local/share/omarchy/themes`.

Preset theme:

```toml
[theme]
name = "tokyo-night"
source = "preset"
```

Follow the active compatible system theme:

```toml
[theme]
name = "tokyo-night"
source = "current"
```

Load a named theme directory:

```toml
[theme]
name = "kanagawa"
source = "directory"
```

Load a direct palette file with partial overrides:

```toml
[theme]
name = "my-theme"
source = "file"
colors_file = "/path/to/colors.toml"

[theme.ui]
warning = "#ffcc66"
panel = "#303446"
```

### Keybindings

Keybindings are configurable in the same file.

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

## Need to know

For people who want the technical shape without reading the whole codebase:

- Storage uses SQLite with WAL mode for local caching.
- Blocking work is pushed off the UI thread through Textual workers.
- Drafts are local-first and follow explicit lifecycle rules for save, discard, restore, and delete.
- Time handling is normalized around UTC-aware timestamps.
- UI reads are being pushed behind query services so screens and widgets stay thinner and more deterministic.
- Theme resolution is runtime-driven and compatible with Omarchy-style palette files without making Omarchy a hard dependency.

## Development

```bash
uv run pytest
uv run ruff check shmail tests
uv run pyright
```

## Direction

Current work is focused on:

- deterministic UI behavior and low-flicker targeted updates
- stronger repository/service/query-service boundaries
- theme robustness and compatibility
- local-first compose and draft correctness
- outbound mutation and provider sync-back architecture

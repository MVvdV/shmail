# Agent Guide

This directory contains project-specific agent memory, rules, and operating contracts.

## Purpose

- `system.md` defines the active framework entrypoints and runtime expectations
- `context.md` captures architecture, boundaries, and project-level patterns
- `roadmap.md` is the session memory and handoff log
- `rules/` contains local engineering rules layered on top of shared global styles

## Startup order

When starting work in this repository, read these files in order:

1. `.agent/system.md`
2. `.agent/context.md`
3. `.agent/roadmap.md`

After reading them, report the current state and wait for explicit user direction before editing.

## Current architectural patterns

- `DatabaseRepository` owns storage primitives only
- domain services own workflow and mutation rules
- query services shape UI-facing reads
- UI should prefer `UI -> service/query service -> repository -> database`
- targeted low-flicker patches should flow through one shared state/update authority, not ad hoc widget logic

## Files in this directory

- `system.md`: framework/runtime contract
- `context.md`: architecture map and project boundaries
- `roadmap.md`: roadmap, session state, and handoff history
- `rules/python.md`: Python-specific project overrides
- `rules/textual.md`: Textual-specific project overrides

## Notes

- Keep user-facing project documentation in the repo root `README.md`
- Keep agent/process/governance guidance in `.agent/`
- When architecture changes materially, update both `context.md` and `roadmap.md`

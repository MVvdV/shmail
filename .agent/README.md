# Shmail Agent Runtime Guide

This file explains how agents should operate in this repository.

## Purpose
- Load project-specific laws and context quickly.
- Clarify where workflow, policy, and memory live.
- Prevent instruction drift during long sessions.

## Runtime Entry Order
1. Read `.agent/system.md`.
2. Read `.agent/context.md`.
3. Read `.agent/roadmap.md`.
4. Apply active role from `.agent/roles/`.

## Active Model
- **Primaries**: OpenCode built-in `plan`, built-in `build`, and custom `tutor`.
- **Workflows**: Slash commands in `.opencode/commands/`.
- **Subagents**: `@` agents in `.opencode/agents/` (`mode: subagent`).

## Core Files
- `system.md`: active laws, governance, routing.
- `context.md`: architecture, stack, and boundaries.
- `roadmap.md`: session memory and handoff log.
- `security.md`: security pointer and local constraints.
- `contracts/`: migration integrity and interaction standard.
- `catalog/workflows.md`: workflow command index.
- `catalog/subagents.md`: subagent index.

## Required Workflows
- `/start-session`: run entry audit and return status.
- `/list-framework`: show workflows/subagents and usage.
- `/upgrade-framework [target_scope] [target_path] [source_path]`: upgrade with preflight and discovery/harvest.
- `/close-session`: update session state and handoff.
- `/execute-changes`: Tier 2 governance gate.

## Governance Rules
- Tier 2 operations require `CONFIRM EXECUTE CHANGES`.
- `/upgrade-framework` must show inferred scope/source/target and allow edits before apply.
- `/upgrade-framework` must run discovery/harvest and require explicit import mode selection for discovered docs.
- Preserve roadmap history and project constraints during upgrades.
- Optional source config: set `.opencode/settings.json` key `framework.source`. Use `__AUTO__` for portable auto-detection.

## Project-Specific Guardrails
- Absolute git prohibition remains active unless explicitly directed by user.
- Respect boundaries in `.agent/context.md`.
- Do not delete historical entries from `.agent/roadmap.md`.

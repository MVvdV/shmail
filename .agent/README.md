# Project Agentic Structure
This folder contains the project framework registry and governance contracts.

## File Map
- `system.md`: Switchboard for active primaries, workflows, subagents, and contracts.
- `context.md`: Project architecture and boundaries.
- `roadmap.md`: Session memory and handoff history.
- `roles/`: Primary role instructions. Tutor is the active custom primary role.
- `rules/`: Technical standards inherited from `~/.agent/styles/`.
- `contracts/`: Universal migration and interaction standards.
- `catalog/`: Human-readable indexes for workflows and subagents.
- `security.md`: Local pointer to global security policy.

## Runtime Model
- **Primaries**: OpenCode built-in `plan` and `build`, plus custom `tutor`.
- **Workflows**: Invoked with `/` from `.opencode/commands/`.
- **Subagents**: Invoked with `@` from `.opencode/agents/` (`mode: subagent`).
- **Upgrade Command**: `/upgrade-framework [target_scope] [target_path] [source_path]` with required preflight confirmation.
- **Upgrade Harvesting**: `/upgrade-framework` includes discovery/harvest for non-standard instruction docs before mapping.

## Inheritance Logic
This project uses explicit pointers. Files in `roles/`, `rules/`, and `contracts/` may inherit from `~/.agent/` and then apply local overrides.

## Initialization
When an agent enters this project, first read `.agent/system.md`, then `.agent/context.md`, then `.agent/roadmap.md`, return state, and wait for explicit user instruction before any edits.

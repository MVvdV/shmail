# Workflow Catalog

## User-Facing Slash Commands
- `/list-framework`: Show available workflows/subagents, risk tiers, and usage examples.
- `/upgrade-framework [target_scope] [target_path] [source_path]`: Upgrade framework with inferred defaults and editable preflight.
- `/session-start`: Read-only startup intake (system/context/roadmap only) and 3-line state report.
- `/session-close`: Update roadmap holistically, verify by re-read, then close.
- `/execute-changes`: Apply Tier 2 governance updates after explicit confirmation.

## Invocation Notes
- Workflows are defined in `.opencode/commands/`.
- Use `@subagent-name` for direct specialist invocation.
- `/upgrade-framework` must display and confirm source/target before apply.
- `/upgrade-framework` must run discovery/harvest and require explicit import selection for discovered docs.

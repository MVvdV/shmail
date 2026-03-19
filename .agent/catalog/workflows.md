# Workflow Catalog

## User-Facing Slash Commands
- `/list-framework`: Show workflows/subagents, risk tiers, and examples.
- `/upgrade-framework [target_scope] [target_path] [source_path]`: Upgrade framework with inferred defaults and editable preflight.
- `/start-session`: Audit current project state and return 3-line status.
- `/close-session`: Update roadmap session state and append handoff entry.
- `/execute-changes`: Apply Tier 2 governance updates after explicit confirmation.

## Common Usage
- `@qa-auditor` for risk review of current ticket.
- `@test-strategist` for fast test planning before implementation.
- For `/upgrade-framework`, confirm inferred source/target before apply.
- For `/upgrade-framework`, review discovery/harvest candidates and choose import mode explicitly.

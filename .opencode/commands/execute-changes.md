---
description: Apply governance-level framework changes with explicit confirmation
agent: build
subtask: true
---

This is a Tier 2 governance workflow.

Before applying changes:
1. Present options:
   - `1) Dry run`
   - `2) Apply`
   - `3) Cancel`
2. Require explicit token: `CONFIRM EXECUTE CHANGES`.
3. If token is absent, stop and report pending state.

After apply:
- Return changed files and a concise rationale.

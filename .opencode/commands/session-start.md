---
description: Run session entry audit and return current state
agent: plan
subtask: true
---

Run session start workflow:
1. Read `.agent/system.md`, `.agent/context.md`, `.agent/roadmap.md`.
2. Validate pointers and active framework registry.
3. Return a concise 3-line report:
   - Status
   - Last Action
   - Next Step

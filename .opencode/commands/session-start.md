---
description: Run session entry audit and return current state
agent: plan
subtask: true
---

Startup contract (strict):
1. Read exactly these files, in order:
   - `.agent/system.md`
   - `.agent/context.md`
   - `.agent/roadmap.md`
2. Do not read any other files.
3. Do not run pointer/registry validation during startup.
4. Do not run discovery, audits, edits, or autonomous task continuation.
5. Return exactly:
   - Status
   - Last Action
   - Next Step
6. Stop after reporting state and wait for explicit user instruction.

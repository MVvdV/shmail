---
description: Run session handoff and update roadmap session state
agent: build
subtask: true
---

Session close sequence (required order):
1. Summarize agreed changes and completed work for this session.
2. Update `.agent/roadmap.md` holistically:
   - `Current Status` checkboxes
   - `Session State` (`Last Action`, `Next Step`, `Blockers`)
   - append one dated `Handoff Log` entry
3. Re-read `.agent/roadmap.md` and verify those updates are present.
4. Return the exact next step for the following session.
5. Only after successful verification, announce session closed.

Failure rule:
- If roadmap update or verification fails, return `pending close` with missing items and do not announce closure.

---
description: Upgrade framework into project or global target scope
agent: build
subtask: true
---

Run framework upgrade using this contract:
- `.agent/contracts/migration-integrity.md`
- `.agent/contracts/interaction-standard.md`

Arguments:
- `$1`: optional target scope (`project`, `global`)
- `$2`: optional target path
- `$3`: optional source path

Resolution rules:
1. Resolve target scope:
   - `$1` when provided
   - infer `project` when `.agent/system.md` exists
   - otherwise prompt user for `project|global`
2. Resolve source path (in order):
   - `$3` when provided
   - `.opencode/settings.json` key `framework.source` when non-empty and not `__AUTO__`
   - current repo root when framework source markers (`global/` + `project/`) exist
   - otherwise prompt user for source path
3. Resolve target path:
   - `$2` when provided
   - current repo root for `project`
   - `~/.agent` for `global`

Required preflight (before any write/audit):
- Show `target scope`, `source`, `target`, and planned writes.
- Offer choices:
  - `1) Proceed dry run`
  - `2) Change target scope`
  - `3) Change source path`
  - `4) Change target path`
  - `5) Cancel`

Discovery + harvest phase (after preflight, before migration mapping):
1. Discover candidate instruction files with flexible heuristics:
   - names: `*.md`, `*.txt`, `*.rst`, `AGENTS.md`, `CLAUDE.md`, `RULES*`, `PLAYBOOK*`
   - content keywords: `session`, `handoff`, `policy`, `guardrail`, `constraints`, `role`, `persona`, `workflow`, `security`, `must`, `never`
   - paths: repo root docs, `.github/`, `docs/`, config folders
2. Exclude generated/vendor paths (`node_modules`, caches, build artifacts).
3. Produce harvest proposal table:
   - candidate file
   - extracted themes
   - proposed destination (`.agent/system.md`, `.agent/context.md`, `.agent/contracts/*`, `.agent/catalog/*`, `.agent/roadmap.md`)
   - confidence
   - action (`import`, `review`, `ignore`)
4. Ask user selection:
   - `1) Import recommended only`
   - `2) Review each candidate`
   - `3) Ignore discovered extras`
   - `4) Add custom file path`
   - `5) Cancel`

Execution after preflight:
1. Run `instruction-auditor` then `migration-auditor`.
2. Return migration mapping, parity checklist, and unresolved items.
3. For apply (Tier 2), require explicit token: `CONFIRM EXECUTE CHANGES`.
4. Never auto-apply inferred values without explicit confirmation.
5. Never overwrite roadmap history; append only to handoff log.

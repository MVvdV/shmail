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

Invocation safety gates (fail fast):
1. Validate `$1` when provided:
   - allow only `project` or `global`
   - reject any other value and stop with correction guidance
2. Normalize paths before resolution:
   - trim wrapping quotes
   - expand `~`
   - resolve relative paths from invocation root (not transient shell cwd)
   - canonicalize to absolute paths
3. Validate resolved source path:
   - must exist and be readable directory
   - must contain framework markers: `global/` and `project/`
   - if markers are missing, stop and request explicit source override
4. Validate resolved target path:
   - must be absolute after normalization
   - parent directory must exist and be writable
   - for `global`, target must be `~/.agent` unless user explicitly overrides during preflight
5. Collision protection:
   - block apply when `source == target`
   - block apply when target is nested inside source or source nested inside target
   - allow dry run with warning for any collision scenario

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

Cross-directory behavior:
1. Resolve invocation root in this order:
   - nearest directory containing `.agent/system.md`
   - nearest git repo root
   - process cwd
2. Resolve all relative args (`$2`, `$3`) from invocation root.
3. Never infer source from target and never infer target from source.
4. If invocation root and target root differ, display both explicitly in preflight.

Required preflight (before any write/audit):
- Show `target scope`, `source`, `target`, and planned writes.
- Show validation results (`scope`, `source`, `target`, `collision`, `write access`).
- Offer choices:
   - `1) Proceed dry run`
   - `2) Change target scope`
   - `3) Change source path`
   - `4) Change target path`
   - `5) Cancel`

Validation failure contract:
- On any failed safety gate, return:
  - failing gate
  - offending value
  - exact expected format/value
  - single recommended fix
- Stop before discovery, audits, or writes.

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

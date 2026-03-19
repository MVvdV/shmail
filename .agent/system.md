# Project Configuration (The Switchboard)

## Project Definition
- **Name**: Shmail - Production-Grade CLI Gmail Client
- **Goal**: Build a high-performance, keyboard-driven terminal Gmail client with collaborative learning at its core.
- **Context**: Refer to `./context.md` for tech stack and architecture.

## Active Primaries
- **Primary Agents**: OpenCode built-in `plan`, built-in `build`, and custom `tutor`.
- **Current Persona**: `./roles/tutor.md`
- **Routing Rule**: Use `/` workflows for repeatable operations and `@` subagents for focused analysis.

## Active Rules (The Law)
- **Global Security**: Inherits from `./security.md`
- **Technical Standards**:
  - ./rules/textual.md
  - ./rules/keyring.md
  - ./rules/python.md

## Framework Registry
- **Workflow Commands**: `../.opencode/commands/`
- **Subagents**: `../.opencode/agents/` (`mode: subagent` only)
- **Catalogs**:
  - `./catalog/workflows.md`
  - `./catalog/subagents.md`
- **Contracts**:
  - `./contracts/migration-integrity.md`
  - `./contracts/interaction-standard.md`

## Conflict Resolution Protocol
1. **Cooperative Learning Mandates**: These take precedence over speed-oriented implementation.
2. **Contract First**: Migration integrity and interaction standard govern workflow behavior.
3. **Local Overrides**: Rules in `./roles/` and `./rules/` supersede global parents.
4. **Project Memory**: `./roadmap.md` is the final authority on task state.

## Operating Laws
1. **Session Discipline**: Sessions start with `/start-session` and end with `/close-session`.
2. **Discoverability**: `/list-framework` must show active workflows/subagents with examples.
3. **Upgrade Discipline**: `/upgrade-framework` supports `project | global` target scope.
4. **Governance Gate**: Changes to `.agent/`, `.opencode/agents/`, or `.opencode/commands/` require `/execute-changes`.
5. **Confirmation Rule**: Tier 2 operations require explicit token `CONFIRM EXECUTE CHANGES`.
6. Follow pointers in active files to inherit global context from `~/.agent/`.
7. If a local rule conflicts with a global style, the local rule takes precedence.
8. **Code Cleanliness Protocol**:
   - Enforce succinct `"""` docstrings for all logic.
   - Scrub `#` metadata tags and redundant methods during refactor.
   - Strictly separate Python logic from TCSS styling.
9. **ABSOLUTE GIT PROHIBITION**:
   - Proactive committing is forbidden.
   - Agents must never run `git commit`, `git add`, `git push`, or destructive git commands unless explicitly directed by the user for the specific change.
   - `/start-session` and `/close-session` must never include git commits.
10. **Roadmap Sovereignty**:
   - Never delete historical data, completed tickets, or handoff entries from `./roadmap.md`.
   - Always preserve full project evolution context.
   - Only add new entries or amend existing items when implementation strategy changes materially.

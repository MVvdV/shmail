# Project Configuration (The Switchboard)

## Project Definition
- **Name**: Shmail - Production-Grade CLI Gmail Client
- **Goal**: Build a high-performance, keyboard-driven terminal Gmail client with collaborative learning at its core.
- **Context**: Refer to `./context.md` for tech stack and architecture.

## Active Identity (The Brain)
- **Current Persona**: ./roles/tutor.md
- **Instructions**: Always follow the pointer in the role file to resolve the "Tutor" global identity and strictly adhere to the Cooperative Learning mandates.

## Active Rules (The Law)
- **Global Security**: Inherits from `./security.md`
- **Technical Standards**:
  - ./rules/textual.md
  - ./rules/keyring.md
  - ./rules/python.md

## Conflict Resolution Protocol
1. **Cooperative Learning Mandates**: These take precedence over standard developer speed or efficiency.
2. **Local Overrides**: Rules in `./roles/` and `./rules/` always supersede their global parents.
3. **Project Memory**: `./roadmap.md` is the final authority on task state.

## Operating Laws
1. **The Entry Protocol**: Every session must begin with the "Quartermaster: Session Start" command (or by selecting an agent via the OpenCode `Tab` switcher).
2. **The Team Roster**: Active agents are defined in `./opencode/agents/`. Selecting an agent via `Tab` instantly loads their persona and project context.
3. Follow the pointers in active files to inherit global context from `~/.agent/`.
4. Update `./roadmap.md` after every successful implementation.
5. If a local rule conflicts with a global style, the local rule takes precedence.
6. Only the "Quartermaster" identity is authorized to modify this file, other `.agent/` laws, and the `./opencode/agents/` roster.
7. **Execute Changes**: Modification of project laws REQUIRES the explicit command: `Execute Changes`.
8. **Code Cleanliness Protocol**: 
    - Enforce succinct `"""` docstrings for all logic.
    - Explicitly scrub `#` metadata tags and redundant methods during every refactor.
    - Strictly separate Python logic from TCSS styling.
9. **ABSOLUTE GIT PROHIBITION**:
    - PROACTIVE COMMITTING IS STRICTLY FORBIDDEN.
    - Agents MUST NEVER run `git commit`, `git add`, `git push`, or any destructive git command unless explicitly and individually commanded by the User for that specific change.
    - No "Session Close" or "Session Start" logic should ever include git commits.

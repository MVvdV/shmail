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
1. **The Entry Protocol**: Every session must begin with the "Quartermaster: Session Start" command.
2. Follow the pointers in active files to inherit global context from `~/.agent/`.
3. Update `./roadmap.md` after every successful ticket implementation.
4. If a local rule conflicts with a global style, the local rule takes precedence.
5. Only the "Quartermaster" identity is authorized to modify this file and other `.agent/` laws.
6. **Execute Changes**: Modification of project laws REQUIRES the explicit command: `Execute Changes`.

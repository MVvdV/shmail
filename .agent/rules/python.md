Inherits From: ~/.agent/styles/python-clean.md

# Project-Specific Overrides: Python
- **Language**: Python 3.13+.
- **Dependency Manager**: `uv` exclusively. Check for `uv.lock`.
- **Formatting**: `ruff check` and `ruff format` required.
- **Typing**: Strict `pyright` checking on Pydantic models.
- **Architecture**: Dependency Injection (DI) - services accept DB instances in constructor.
- **Concurrency**: `asyncio` loop or background threads with Textual Workers.

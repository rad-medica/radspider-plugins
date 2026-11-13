---
description: Run the repository checks (manifest validator and ruff) and report
allowed-tools: Bash(python tools/validate_plugins.py:*), Bash(ruff check:*)
---

Run `python tools/validate_plugins.py` and `ruff check .`. Report each result in one line; on failure list every error with file and what to change. Do not fix anything unless asked.

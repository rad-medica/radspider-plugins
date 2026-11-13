---
description: Scaffold a new plugin from org.radspider.examples
argument-hint: <short-name>
---

Create plugin `org.radspider.$ARGUMENTS`:
1. Copy `org.radspider.examples` to `org.radspider.$ARGUMENTS`; set `id`, `name`, `description` in `plugin.toml`; keep `version = "1.0.0"`.
2. Add the README table row and a `CHANGELOG.md` line under Unreleased.
3. Run `python tools/validate_plugins.py` and `ruff check .`.
4. Report what to fill in next (entries, params, requirements). Do not commit.

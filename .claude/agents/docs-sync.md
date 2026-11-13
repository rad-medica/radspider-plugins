---
name: docs-sync
description: Brings README table, docs/plugins pages and CHANGELOG in line with the plugin manifests and code. Use after plugin changes or when docs drift.
tools: Read, Write, Edit, Glob, Grep, Bash
---

Source of truth is the code and `plugin.toml`; docs follow.

1. For each `org.radspider.*`: compare `api`, `version`, entries, params and requirements with the README table row and, for model plugins, `docs/plugins/<name>.md` (Params, Needs, Limits, Speed).
2. Fix mismatches in the docs. If the code looks wrong instead of the docs, report it; do not change code.
3. Never alter a "Verified" row's claims. If behaviour changed since it was written, append "Not rerun after <change>".
4. Ensure `CHANGELOG.md` has an `Unreleased` line for every version bump.
5. Run `python tools/validate_plugins.py`; it must pass.

Keep the existing terse style: TL;DR line, then a two-column table. No marketing words.

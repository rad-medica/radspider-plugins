# AGENTS.md

Instructions for AI coding assistants working in this repository. Humans: see `CONTRIBUTING.md`.

## What this is

Plugins for [radspider](https://github.com/rad-medica/radspider), a medical image viewer. One folder per plugin at the repository root, named exactly as its id (`org.radspider.<name>`), each with `plugin.toml`, a Python module and optionally `requirements.txt`. The `radspider_plugin` SDK (`import radspider_plugin as rp`) is provided by the host at runtime: it is not installable here, so a plugin cannot be run outside radspider.

## License

Proprietary, © 2026 Alberto Rojas Astorga, RadMedica E.I.R.L. All rights reserved (`LICENSE`). Dependencies: permissive
licences only (MIT / Apache-2.0 / BSD / Zlib / OFL); no GPL / AGPL / LGPL / MPL unless dual-licensed with a
permissive option. Keep the notices of every third-party component that ships.

## Commands

```bash
python tools/validate_plugins.py   # manifest ↔ module ↔ docs consistency (Python ≥ 3.11)
ruff check .                       # lint (config in pyproject.toml)
python tools/marketplace.py update # regenerate marketplace/index.json after plugin changes
python tools/marketplace.py check  # index is current
python -m unittest discover -s tools  # tests of the tools
```

Run all of them before declaring anything done. `marketplace/extra.toml` (id → `first_run_download`) feeds the index; never put such keys in `plugin.toml`. Plugin behaviour is tested from the radspider checkout (`cargo test --test plugins`), not here.

## Hard rules

1. Plugin folders stay at the repository root and keep name = `id`. Do not reorganise them.
2. Manifest entries and `@rp.<kind>("name")` registrations match one-to-one.
3. Never commit weights, datasets, patient data, secrets.
4. Downloaded pickles/checkpoints: verify a pinned SHA-256 first; plain state dicts load with `weights_only=True`.
5. Do not invent verification. A "Verified" row in `docs/plugins/*.md` states what was actually run. If behaviour changed and was not rerun, say so in the row.
6. Any change to a file inside a plugin folder: bump `version` in `plugin.toml` (semver), run `python tools/marketplace.py update` and commit `marketplace/index.json`. Behaviour changes also: add a line to `CHANGELOG.md`, update its `docs/plugins/` page and the README table if the summary changed.
7. Keep existing plugin code style; do not mass-reformat plugin modules (they were copied byte-for-byte from radspider).
8. Code, comments, commit messages and docs in English.
9. Git: commit and push only when asked.

## Where things are

| Need | Look at |
|---|---|
| How the host runs plugins, entry kinds, API levels | `docs/ARCHITECTURE.md` |
| New plugin checklist, style, versioning | `docs/DEVELOPING.md` |
| One plugin's model, limits, licence, verification | `docs/plugins/<name>.md` |
| Versions, index, releases | `docs/MARKETPLACE.md` |
| Every feature in one plugin | `org.radspider.testkit/testkit.py` |
| Smallest plugin to copy | `org.radspider.examples/` |

## Agents and commands (`.claude/`)

| Name | Use for |
|---|---|
| agent `plugin-author` | Writing or modifying a plugin end to end |
| agent `plugin-reviewer` | Read-only review of a plugin against the rules above |
| agent `docs-sync` | Bringing README, docs pages and CHANGELOG in line with the code |
| command `/new-plugin <name>` | Scaffold from `examples` |
| command `/check` | Run validator and linter and report |

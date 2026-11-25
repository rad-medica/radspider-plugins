# AGENTS.md — how to work on radspider-plugins

Humans: see `CONTRIBUTING.md`.

## TL;DR

1. Python plugins for radspider, one folder per plugin id; the SDK exists only inside radspider.
2. Proprietary, © 2026 Alberto Rojas Astorga, RadMedica E.I.R.L. (`LICENSE`). Permissive deps only.
3. Less is more: reuse what exists, smallest diff that fully works, fewest tokens.
4. Test the minimum that proves the change. Never walk every translation through the GUI.
5. Run the five commands below before saying anything is done.

## What this is

Plugins for [radspider](https://github.com/rad-medica/radspider), a medical image viewer. One folder per plugin at the repository root, named exactly as its id (`org.radspider.<name>`), each with `plugin.toml`, a Python module and optionally `requirements.txt`. The `radspider_plugin` SDK (`import radspider_plugin as rp`) is provided by the host at runtime: it is not installable here, so a plugin cannot be run outside radspider.

## Shared rules (all radspider repositories)

| Rule | Meaning |
|---|---|
| Persona | Blunt, terse senior engineer, tired of dealing with idiots. No greetings, no filler, no flattery. Bad idea → say so in one sentence, then do it right |
| No verbosity | The user dislikes it. Short answers, tables and bullets; no recaps, no narration, no closing remarks |
| Less is more | Reuse existing functions, helpers and patterns before writing new ones. Smallest diff that solves the whole problem. No abstractions, options or "for later" code nobody asked for. Spend as few tokens as possible |
| Minimal testing | Run only what proves the change: the affected tests, one real-data check, one screenshot if the UI changed. Translations are checked by their file tests (keys present, placeholders match), never by switching the GUI through every language |
| Other repositories | Changing a sibling repository (radspider, radspider-web, radspider-chrome, radspider-plugins, jpegexp-rs, rad-parser, rad-renvol) is allowed, but ask the user first |
| No stubs | Complete and verified, or it does not exist. No `TODO`, placeholders, dead buttons |
| Claims match evidence | Say exactly what was run and on what data. Failed or skipped = say so |
| English in repo | Code, comments, commits, docs in English. Chat in the user's language |
| Git | Commit / push only when asked. "Review the code" = files on disk, not history |
| Docs move with code | Same change. TL;DR first, tables, one idea per section |
| Licences | No GPL / AGPL / LGPL / MPL unless dual-licensed with a permissive option. Keep third-party notices |

Full version: `radspider/AGENTS.md`.

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

## Where things are

| Need | Look at |
|---|---|
| How the host runs plugins, entry kinds, API levels | `docs/ARCHITECTURE.md` |
| New plugin checklist, style, versioning | `docs/DEVELOPING.md` |
| One plugin's model, limits, licence, verification | `docs/plugins/<name>.md` |
| Versions, index, releases | `docs/MARKETPLACE.md` |
| Every feature in one plugin | `org.radspider.testkit/testkit.py` |
| Smallest plugin to copy | `org.radspider.examples/` |

## Procedures

| Task | Steps |
|---|---|
| Write or change a plugin | Read `docs/ARCHITECTURE.md`, `docs/DEVELOPING.md` and the closest plugin (`examples` stdlib, `numpy-demo` numpy, `registration-demo` two volumes, `testkit` host features). Lowest `api` that has what it uses. Manifest and module together, entries one-to-one; every param has a `default` (`min`/`max` when meaningful); requirements with lower bounds; user-fixable errors say how to fix them. Then hard rule 6 and the five commands. A plugin cannot run here: never write a "Verified" row for what you did not run |
| New plugin | Copy `org.radspider.examples` to `org.radspider.<name>`; set `id`, `name`, `description`; `version = "1.0.0"`; README row and `CHANGELOG.md` line under Unreleased; run the commands; report what is left to fill in |
| Review a plugin (read-only) | Files on disk. In order: manifest ↔ module (names, kinds, every `ctx.params["x"]` has a default, `api` high enough: ROIs / segments / windows → 2, `ctx.other` → 3); safety (unpinned downloads, `torch.load` without `weights_only=True` or a prior hash check, `eval` / `exec`, shell calls, writes outside the cache dir, patient data in logs); edges (NaN, empty volume, anisotropic spacing, non-HU units, slice order, memory on 512²×300, cancel, progress); docs honesty; housekeeping (bounded requirements, README row, CHANGELOG line, semver bump, `marketplace/index.json`). Include the validator and ruff results. Blocking issues first, one line each |
| Sync docs with code | Code and `plugin.toml` are the truth. Compare `api`, `version`, entries, params, requirements with the README row and `docs/plugins/<name>.md`; fix the docs, report (don't change) code that looks wrong; never alter a "Verified" claim, append "Not rerun after <change>"; every version bump has an Unreleased CHANGELOG line; validator passes |
| Check | Run the five commands; one line each; on failure every error with file and fix. Fix nothing unless asked |

# Contributing

## TL;DR

- Proprietary: contributions only with a written agreement with the owner.
- One plugin per PR; before pushing: `python tools/validate_plugins.py`, `ruff check .`, `marketplace.py update`.
- Any change inside a plugin folder bumps its `version`; CI fails otherwise.
- No weights, data or secrets in git; docs claim only what you ran.

Proprietary repository (see `LICENSE`): contributions come from people with a written agreement with the owner.

## Workflow

1. Branch from `main`: `feat/<plugin>-<what>`, `fix/<plugin>-<what>`, `docs/<what>`, `ci/<what>`.
2. One plugin per pull request unless the change is repository-wide.
3. Before pushing:

```bash
python tools/validate_plugins.py
ruff check .
python tools/marketplace.py update   # when any file inside a plugin folder changed; commit marketplace/index.json
```

4. Open the PR; CI must be green. Fill the PR template: it asks what you ran and on what, because that is what the docs' "Verified" rows are made of.

## Rules

| Rule | Why |
|---|---|
| Plugin folder name = `id` in `plugin.toml` | radspider resolves plugins by it |
| Plugin folders stay at the repository root | radspider's tests resolve `../radspider-plugins/<id>` |
| No model weights, data or secrets in git | Size, licences, patient data. `.gitignore` is not a safety net |
| Pin a SHA-256 for every downloaded pickle/checkpoint | Loading a pickle is code execution |
| Manifest and module declare the same entries | The validator fails the build otherwise |
| Any change inside a plugin folder bumps its `version`; CI compares against the base branch and fails otherwise | The marketplace updates clients by version, so identical versions must mean identical files |
| Behaviour changes bump the plugin's `version` and add a `CHANGELOG.md` line | Users install from folders; the version is how they tell |
| Claims in docs are things you ran. Say what you did not run | A "Verified" row that is wrong is worse than none |
| Code, comments, commits and docs in English | Shared with the radspider repository |

## Commits

Imperative, one line that says what changed and where: `sam-slices: clip propagated mask to the neighbour grown by 6 mm`. Body explains why when it is not obvious.

## Reporting a problem

Open an issue with the plugin id and version, radspider version, OS, the full error text shown by the viewer, and the plugin log. For a security issue see [SECURITY.md](SECURITY.md).

# Developing a plugin

## Start from the examples

- `org.radspider.examples`: stdlib only, one entry of each kind, 40 lines. Copy it.
- `org.radspider.numpy-demo`: the same with numpy and a `requirements.txt`.
- `org.radspider.registration-demo`: two-volume tool (api 3).
- `org.radspider.testkit`: every feature, as a reference for progress, cancel, charts, ROIs, windows.

## New plugin checklist

1. `cp -r org.radspider.examples org.radspider.<name>` and edit. Folder name = `id`.
2. `plugin.toml`: `id`, `name`, `version = "1.0.0"`, `api` (lowest that has what you use), `description`, `requirements` if any.
3. Declare every entry with `name`, `label`, `description` and `params` (each with a `default`; bounds when they mean something).
4. Register the same names in the module with `@rp.<kind>("name")`.
5. `requirements.txt`: lower-bound every package (`numpy>=1.26`). Heavy one-time dependencies get a comment saying so. A package with no usable PyPI release may be a git URL pinned to a full commit (`name @ git+https://…@<40 hex>`), with a comment saying why.
6. Model plugin: add `docs/plugins/<name>.md` (copy the structure of `sam-slices.md`). No weights in git; pin a SHA-256 for anything unpickled.
7. Add the row to the README table and a line to `CHANGELOG.md`.
8. Run the checks and regenerate the index:

```bash
python tools/validate_plugins.py
ruff check .
python tools/marketplace.py update
```

9. Install it in radspider (Settings → Modules → *Install folder…*) and run it once. Say in the docs what you ran it on, and what you did not.

## Style

- Python ≥ 3.10 syntax, 120 columns, `ruff` clean. stdout goes to the plugin log: fine for diagnostics, never for control flow.
- Errors that the user can fix raise with a message that says how ("No Probe measurements: place at least one"). The viewer shows it verbatim.
- Do not catch broad exceptions to hide failures. Cancel and error paths are the host's job.
- Prefer numpy over Python loops for anything per-voxel: pure Python on a 512×512×300 CT takes minutes.
- Comments explain why (a deviation from the reference implementation, a unit assumption), not what.

## Versioning

Every change to a file inside a plugin folder needs a higher `version` and a regenerated `marketplace/index.json` (`python tools/marketplace.py update`). CI enforces it ([MARKETPLACE.md](MARKETPLACE.md)). Docs-only changes under `docs/` do not.

- `version` in `plugin.toml` is semver per plugin. Behaviour change that alters results → minor; breaking param or entry rename → major; fix → patch.
- Raising `api` is a compatibility break for older radspider builds: say so in `CHANGELOG.md`.

# Architecture

What this repository relies on from radspider. The authority is `docs/PLUGINS.md` in the radspider repository; if the two disagree, radspider wins and this file is the bug.

## Layout

```
radspider-plugins/
├── org.radspider.<name>/      one folder per plugin; the folder name IS the plugin id
│   ├── plugin.toml            manifest: id, name, version, api, entries, params
│   ├── plugin.py              module (or the file named by `module = "…"`)
│   └── requirements.txt       optional; installed into the plugin's own venv
├── docs/                      this documentation
├── tools/validate_plugins.py  manifest ↔ module consistency checks
└── .github/workflows/         CI
```

The plugin folders sit at the repository root because radspider's integration tests and `RADSPIDER_PLUGIN_EXAMPLES` resolve `<checkout>/<id>`. Do not move them under a subdirectory without changing radspider first.

## Runtime model

1. radspider copies the plugin folder to `<config>/plugins/<id>/` and creates a venv for it.
2. `requirements.txt` is `pip install`ed into that venv, so plugins never share dependencies and a heavy one (torch) never leaks into another.
3. radspider runs the module in a separate process and talks to it through the `radspider_plugin` SDK, imported as `rp`. The SDK is provided by the host: it is not on PyPI and not in this repository.
4. The process is isolated: a crash, an error result or a cancel ends that run, not the viewer.

## Entry kinds

| Manifest table | Decorator | Receives | Returns |
|---|---|---|---|
| `[[synth_node]]` | `@rp.synth_node("name")` | `volume`, `ctx` | new voxel values (series builder node) |
| `[[segmentation]]` | `@rp.segmentation("name")` | `volume`, `ctx` | `(labels, names)` |
| `[[tool]]` | `@rp.tool("name")` | `volume`, `ctx` | `rp.Result(table=…, …)` |

- `ctx.params` holds the values of the manifest `params` (`name`, optional `label`, `default`, `min`, `max`).
- `ctx.progress(fraction, message)` reports progress; cancel is cooperative.
- `volume` exposes `values`, `dims`, `spacing`, `origin`, `row`, `col`, `normal`, `unit`, `numpy()`.
- API level: 1 = the three kinds; 2 = + reading and editing ROIs and segments, interactive windows; 3 = + `second_volume` tools (`ctx.other`).
- The manifest and the module must declare the same entry names. `tools/validate_plugins.py` enforces it.

## Conventions between plugins

| Topic | Rule |
|---|---|
| Weights | Never in the repository. Downloaded on first run into a cache; an `RADSPIDER_<NAME>_…` environment variable points to a local file for offline use |
| Integrity | A downloaded pickle/checkpoint is verified (pinned SHA-256) before it is loaded; `torch.load(weights_only=True)` whenever the file is a plain state dict |
| Units | Plugins that need HU refuse other units instead of guessing |
| Memory | Large volumes are processed in bands along z; document the RAM cost in the plugin's page |
| Docs | Every model plugin has a page in `docs/plugins/` with Model, Pipeline, Limits, Speed, Licence and a **Verified** row that says what was and was not run |

## Test layers

| Layer | Where | Covers |
|---|---|---|
| Static | `tools/validate_plugins.py`, `ruff` (CI, every push) | Manifest ↔ module, requirements, docs, syntax, pyflakes |
| Integration | radspider `tests/plugins.rs` (CI job, needs a token) | `examples`, `numpy-demo`, `testkit`, `registration-demo` end to end |
| By hand | the plugin page's "Verified" row | Model plugins: weights and minutes of CPU make CI impractical |

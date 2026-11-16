# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Plugin versions live in each `plugin.toml`; note a plugin bump here.

## [Unreleased]

### Added
- Repository tooling: `tools/validate_plugins.py`, ruff config, GitHub Actions CI, editorconfig.
- Docs: `docs/ARCHITECTURE.md`, `docs/DEVELOPING.md`, one page per model plugin under `docs/plugins/`.
- Contributor and AI-assistant instructions: `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `.claude/` agents and commands.

- New plugin `org.radspider.radiomics` 1.0.0: pyradiomics features of the series' segments. Run on synthetic data outside the viewer only; see its "Verified" row.
- Requirement lint: one exception to "no URLs", `name @ git+https://github.com/<owner>/<repo>@<40-hex commit>`, for a package with no usable PyPI release (pyradiomics on Python >= 3.10). `SECURITY.md` says what it costs.
- New plugin `org.radspider.cads` 1.0.0: CADS whole-body CT segmentation (167 structures, nine task groups). Run outside the viewer on one public CT with the upstream weights; see its "Verified" row.
- New plugins, 1.0.0 each, run on synthetic data outside the viewer only (see each page's "Verified" row): `org.radspider.lung-ct-analyzer`, `org.radspider.density-lung-segmentation`, `org.radspider.roi-tools`, `org.radspider.volume-tools`.
- New plugin `org.radspider.skeletal-radiology` 1.0.0: automatic and hybrid interactive skeletal radiography measurements (spine, lower-limb alignment, hip/pelvis, diaphyseal cortical morphometry, foot/hand goniometry) and bone silhouette segmentation. Not run in radspider; see its "Verified" row.
- Marketplace: `marketplace/index.json`, `tools/marketplace.py` (deterministic packages, version rules), release workflow publishing `<id>-v<version>` GitHub releases, `docs/MARKETPLACE.md`.

- Marketplace index: optional `second_volume` (bool) and `first_run_download` (text from the new `marketplace/extra.toml`) per plugin; schema stays 1, no plugin version changes.
- `docs/MARKETPLACE.md`: *Client contract* (the four GitHub requests, headers, ETag, redirect without the token, error mapping); *Limits* corrected (a client authenticates against the API, it does not mirror).
- `tools/validate_plugins.py`: a `requirements.txt` line must be a plain pip requirement; options (`-r`, `-e`, `--index-url`, `--extra-index-url`, `--find-links`), URLs and local paths are rejected. Semver check follows semver.org exactly (no leading zeros).
- `tools/semver_vectors.json` (precedence cases shared with radspider) and `tools/test_tools.py`, run in CI.
- `SECURITY.md`: how to create, scope and rotate the read-only fine-grained token for the marketplace.
- CI: `radspider-integration.yml` runs radspider's `cargo test --test marketplace_index` with `RADSPIDER_REQUIRE_INDEX=1` against `marketplace/index.json`, so an index radspider cannot parse (or that disagrees with a plugin folder) fails here. Needs the radspider commit that adds the test to be on GitHub.

- `org.radspider.testkit` 1.2.0 (api 6): plugin icon `flask`, entry icons (Phosphor `chart-bar` and `app-window`, PNG `icons/testkit.png`), Spanish catalog `lang/es.toml` and translators' template `lang/template.toml` (`python -m radspider_plugin template`), tool `windows_demo` (form first, reused window, three windows: row / table / section, tabs, a kept log; a checkbox closes one window and a button reopens it). 1.1.0 (the API 5 entries) was never published here: 1.2.0 does not contain those entries. Run headless by radspider `tests/plugins.rs::testkit_plugin_runs_every_entry`; GUI check see `docs/plugins/testkit.md`. Not released: `marketplace/index.json` still lists 1.0.0 (no 1.2.0 package exists); only its `icon` was added by hand.
- Marketplace index: optional `icon` (a Phosphor name; a PNG icon is left out). `tools/marketplace.py` writes it.
- `tools/validate_plugins.py`: `api` 1 to 6; `icon` and `window` need api 6; a PNG icon must be a file inside the plugin folder.

### Changed
- Every plugin moved to plugin API 6, version 1.1.0 (testkit stays 1.2.0): `org.radspider.examples`, `numpy-demo`, `registration-demo`, `monai-wholebody`, `totalsegmentator`, `sam-med3d`, `sam-slices`, `density-lung-segmentation`, `radiomics`, `cads`, `lung-ct-analyzer`, `volume-tools`, `roi-tools`, `skeletal-radiology`. Each gets Phosphor icons (plugin and entries), user-visible texts marked with `rp.tr` / `rp.trc` / `rp.trn`, `lang/template.toml` and a Spanish catalog `lang/es.toml`. Segment, label and ROI names stay untranslated (study data); raised error messages stay English (the SDK sends them as plain text).
- Typed parameters (API 5) where a number encoded a flag, a pick or a count. Renamed or retyped, so values saved for 1.0.0 fall back to the defaults: `registration-demo` `subvoxel` → bool; `monai-wholebody` `highres` → choice `resolution` (`3 mm` / `1.5 mm`); `cads` `research_weights` → choice `weights`; `roi-tools` `all_on_slice`, `outlines` → bool, `sectors`, `layers` → integer, `mode` → choice; `skeletal-radiology` `view_mode` → choice. See each page under `docs/plugins/`.
- Verified per plugin: manifest validation, catalogs match their regenerated templates, Python compiles; the numpy / scipy plugins ran on synthetic data outside the viewer; the model plugins (torch, ONNX, MONAI, CADS, SAM) were not run. Nothing checked in the radspider GUI.
- Per-plugin sections moved from `README.md` to `docs/plugins/` (text unchanged).

## [0.1.0]

- Plugins moved out of radspider: examples, numpy demo, test kit, SAM-Med3D, MONAI whole body, SAM slices, TotalSegmentator, registration demo.

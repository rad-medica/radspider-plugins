# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Plugin versions live in each `plugin.toml`; note a plugin bump here.

## [Unreleased]

### Added
- Repository tooling: `tools/validate_plugins.py`, ruff config, GitHub Actions CI, editorconfig.
- Docs: `docs/ARCHITECTURE.md`, `docs/DEVELOPING.md`, one page per model plugin under `docs/plugins/`.
- Contributor and AI-assistant instructions: `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `.claude/` agents and commands.

- Marketplace: `marketplace/index.json`, `tools/marketplace.py` (deterministic packages, version rules), release workflow publishing `<id>-v<version>` GitHub releases, `docs/MARKETPLACE.md`.

- Marketplace index: optional `second_volume` (bool) and `first_run_download` (text from the new `marketplace/extra.toml`) per plugin; schema stays 1, no plugin version changes.
- `docs/MARKETPLACE.md`: *Client contract* (the four GitHub requests, headers, ETag, redirect without the token, error mapping); *Limits* corrected (a client authenticates against the API, it does not mirror).
- `tools/validate_plugins.py`: a `requirements.txt` line must be a plain pip requirement; options (`-r`, `-e`, `--index-url`, `--extra-index-url`, `--find-links`), URLs and local paths are rejected. Semver check follows semver.org exactly (no leading zeros).
- `tools/semver_vectors.json` (precedence cases shared with radspider) and `tools/test_tools.py`, run in CI.
- `SECURITY.md`: how to create, scope and rotate the read-only fine-grained token for the marketplace.
- CI: `radspider-integration.yml` runs radspider's `cargo test --test marketplace_index` with `RADSPIDER_REQUIRE_INDEX=1` against `marketplace/index.json`, so an index radspider cannot parse (or that disagrees with a plugin folder) fails here. Needs the radspider commit that adds the test to be on GitHub.

### Changed
- Per-plugin sections moved from `README.md` to `docs/plugins/` (text unchanged).

## [0.1.0]

- Plugins moved out of radspider: examples, numpy demo, test kit, SAM-Med3D, MONAI whole body, SAM slices, TotalSegmentator, registration demo.

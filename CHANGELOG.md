# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Plugin versions live in each `plugin.toml`; note a plugin bump here.

## [Unreleased]

### Added
- Repository tooling: `tools/validate_plugins.py`, ruff config, GitHub Actions CI, editorconfig.
- Docs: `docs/ARCHITECTURE.md`, `docs/DEVELOPING.md`, one page per model plugin under `docs/plugins/`.
- Contributor and AI-assistant instructions: `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `.claude/` agents and commands.

- New plugins, 1.0.0 each, run on synthetic data outside the viewer only (see each page's "Verified" row): `org.radspider.lung-ct-analyzer`, `org.radspider.density-lung-segmentation`, `org.radspider.radiomics`, `org.radspider.roi-tools`, `org.radspider.volume-tools`.
- `tools/validate_plugins.py` accepts a requirement that is a git URL pinned to a full commit (`name @ git+https://…@<40 hex>`), for packages with no usable PyPI release.
- Marketplace: `marketplace/index.json`, `tools/marketplace.py` (deterministic packages, version rules), release workflow publishing `<id>-v<version>` GitHub releases, `docs/MARKETPLACE.md`.

### Changed
- Per-plugin sections moved from `README.md` to `docs/plugins/` (text unchanged).

## [0.1.0]

- Plugins moved out of radspider: examples, numpy demo, test kit, SAM-Med3D, MONAI whole body, SAM slices, TotalSegmentator, registration demo.

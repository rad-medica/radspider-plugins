# radspider-plugins

Python plugins for [radspider](https://github.com/rad-medica/radspider): examples to start from, the test kit, AI segmentation and registration.
Proprietary, all rights reserved (`LICENSE`).

## TL;DR

- One folder per plugin, named exactly as its id: `plugin.toml` + a Python module (+ `requirements.txt`).
- Install one: copy its folder into `<config>/plugins/` (beside `settings.toml`) or in radspider Settings → Modules → *Install folder…* (or *Install .zip…* of the folder). radspider makes the venv and pip-installs `requirements.txt`.
- How plugins work (manifest, SDK, protocol, API 1-6): `docs/PLUGINS.md` in the radspider repository. Summary of what this repo relies on: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Plugin folders stay at the repository root on purpose: radspider's `tests/plugins.rs` resolves `../radspider-plugins/<id>`.

## Plugins

| Folder | API | Needs | What | Docs |
|---|---|---|---|---|
| `org.radspider.examples` | 6 | stdlib | One entry of each kind (node, segmentation, tool). Start here | [DEVELOPING](docs/DEVELOPING.md) |
| `org.radspider.numpy-demo` | 6 | numpy | The same three kinds, vectorised | [DEVELOPING](docs/DEVELOPING.md) |
| `org.radspider.testkit` | 6 | numpy | Every feature: 4 nodes, 4 segmentations, 9 tools (params, units, progress, messages, empty result, error, cancel, charts, pictures, ROIs and segments in and out, an interactive window, icons, a Spanish catalog, several windows per run, an image tool) | [testkit](docs/plugins/testkit.md) |
| `org.radspider.sam-med3d` | 6 | torch, medim | Click-prompted 3D segmentation, SAM-Med3D turbo checkpoint | [sam-med3d](docs/plugins/sam-med3d.md) |
| `org.radspider.sam-slices` | 6 | onnxruntime | OHIF 3.10's AI on SAM ViT-B ONNX: click prompts, slice propagation, bidirectional measurement | [sam-slices](docs/plugins/sam-slices.md) |
| `org.radspider.auto-segmentation` | 6 | torch, monai, onnxruntime, numpy, scipy | Automatic CT segmentation with a choice of model: TotalSegmentator v2 3 mm (117 structures, ONNX Runtime), MONAI `wholeBody_ct_segmentation` (104, 3 or 1.5 mm), CADS (167 in nine groups, open weights by default); a window that downloads (in the background, several at once) and deletes the weights. Replaces `totalsegmentator`, `monai-wholebody` and `cads` | [auto-segmentation](docs/plugins/auto-segmentation.md) |
| `org.radspider.registration-demo` | 6 | numpy | The smallest two-volume tool: translation-only registration | [registration-demo](docs/plugins/registration-demo.md) |
| `org.radspider.lung-ct-analyzer` | 6 | numpy, scipy | Lung CT analysis by HU range (emphysema, inflated, infiltrated, collapsed) per lung, and a threshold lung segmentation. After Slicer's LungCTAnalyzer | [lung-ct-analyzer](docs/plugins/lung-ct-analyzer.md) |
| `org.radspider.density-lung-segmentation` | 6 | numpy, scipy | Lung density classes from a 5-component Gaussian mixture, and their volumes. After Slicer's DensityLungSegmentation | [density-lung-segmentation](docs/plugins/density-lung-segmentation.md) |
| `org.radspider.radiomics` | 6 | pyradiomics (from GitHub, compiled: needs git and a C compiler), SimpleITK | pyradiomics features of the series' segments in an interactive window. After SlicerRadiomics | [radiomics](docs/plugins/radiomics.md) |
| `org.radspider.roi-tools` | 6 | numpy, scipy | Ten measurement tools: Cobb angle, ROI export, rotation, point interpolation, sphere volumes, ROIs to segments, sector statistics, point counts, region growing, calcium score | [roi-tools](docs/plugins/roi-tools.md) |
| `org.radspider.volume-tools` | 6 | numpy, scipy | Invert and scale nodes, normalize to a ROI, ΔR2 map, tag-grid merge, rigid registration by mutual information | [volume-tools](docs/plugins/volume-tools.md) |
| `org.radspider.skeletal-radiology` | 6 | numpy, scipy | Automatic and hybrid interactive skeletal radiography measurements: spine (Cobb, balance, wedging), lower-limb alignment (HKA, MAD, mLDFA, MPTA, JLCA, LLD), hip/pelvis (LCEA, Tönnis, CCD), diaphyseal cortical morphometry and foot/hand goniometry | [skeletal-radiology](docs/plugins/skeletal-radiology.md) |

Model weights are downloaded on first run (see each plugin's page); none are in this repository. Check each model's licence before shipping it inside a product.

## Versions and marketplace

Each plugin has its own semver `version` in `plugin.toml`. `marketplace/index.json` lists every plugin with its version, `api`, requirements and a package (`<id>-<version>.zip`, GitHub release `<id>-v<version>`) with its SHA-256. A client compares the installed version with the index and updates when the index is higher; the SHA-256 is what it verifies after download. Details, rules and the contract a client follows: [docs/MARKETPLACE.md](docs/MARKETPLACE.md). The repository is private: a client reads it with a read-only fine-grained token, created as described in [SECURITY.md](SECURITY.md#token-for-the-marketplace).

## Repository map

| Path | What |
|---|---|
| `org.radspider.*/` | The plugins. Installable as-is |
| `org.radspider.series-identifier` | 6 | numpy, onnxruntime | Says what the image on screen is: series kind, plane or projection, region, laterality, contrast, each with its evidence and a plain explanation (English, Spanish). Rules for every modality; on MR a second opinion from the dcm-classifier ONNX. Educational aid | [series-identifier](docs/plugins/series-identifier.md) |
| `docs/` | Architecture, development guide, one page per model plugin (limits, licences, "Verified" rows) |
| `tools/validate_plugins.py` | Static checks of every manifest against its module (stdlib only) |
| `tools/marketplace.py`, `marketplace/index.json`, `marketplace/extra.toml` | Package builder, the version index, and the index facts `plugin.toml` cannot carry (`first_run_download`) |
| `tools/semver_vectors.json`, `tools/test_tools.py` | Semver precedence cases shared with radspider, and the tests of the tools |
| `.github/workflows/` | CI: lint + validation on every push; radspider integration tests when a token is configured |
| `.claude/`, `AGENTS.md` | Instructions and agents for AI coding assistants |

## Checks (local)

```bash
python tools/validate_plugins.py      # manifests vs modules, requirements, docs (Python ≥ 3.11)
python tools/marketplace.py update    # after any plugin file change: regenerate the index, then commit it
python tools/marketplace.py check     # index is current
python -m unittest discover -s tools  # tests of the tools (semver vectors, requirements lint, index fields)
pip install ruff && ruff check .      # lint
```

## Tests (from the radspider checkout)

```bash
cargo test --test plugins                                              # manifests, stdlib example (needs a Python ≥ 3.10 on PATH or RADSPIDER_PYTHON)
RADSPIDER_PLUGIN_PIP=1 cargo test --test plugins                       # + pip install numpy: numpy demo, test kit (study, window), registration demo
```

Check this repo out beside radspider (`../radspider-plugins`) or point `RADSPIDER_PLUGIN_EXAMPLES` at it; the tests skip without it.
The model plugins are not run by the tests (weights, minutes of CPU). Their "Verified" rows in `docs/plugins/` say what was run by hand and on what.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules on adding or changing a plugin.

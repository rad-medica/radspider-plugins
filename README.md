# radspider-plugins

Python plugins for [radspider](https://github.com/rad-medica/radspider): examples and the test kit, AI segmentation, lung and radiomics analysis, measurement tools, volume tools with registration, a measurement reference and structured reports (BI-RADS, PI-RADS, LI-RADS, Lung-RADS, TI-RADS).
Proprietary, © 2026 Alberto Rojas Astorga, RadMedica E.I.R.L. All rights reserved (`LICENSE`).

## TL;DR

- One folder per plugin, named exactly as its id: `plugin.toml` + a Python module (+ `requirements.txt`), or, for a native plugin, Rust source and its executables in `bin/<os>-<arch>/`.
- Install one: copy its folder into `<config>/plugins/` (beside `settings.toml`) or in radspider Settings → Modules → *Install folder…* (or *Install .zip…* of the folder). radspider makes the venv and pip-installs `requirements.txt`.
- How plugins work (manifest, SDK, protocol, API 1-6): `docs/PLUGINS.md` in the radspider repository. Summary of what this repo relies on: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Plugin folders stay at the repository root on purpose: radspider's `tests/plugins.rs` resolves `../radspider-plugins/<id>`.

## Plugins

| Folder | API | Needs | What | Docs |
|---|---|---|---|---|
| `org.radspider.examples` | 6 | stdlib | One entry of each kind (node, segmentation, tool). Start here | [README](org.radspider.examples/README.md) |
| `org.radspider.rust-example` | 6 | none (native) | The same three kinds in Rust: a native plugin, executables for Windows, Linux and macOS in `bin/` | [README](org.radspider.rust-example/README.md) |
| `org.radspider.numpy-demo` | 6 | numpy | The same three kinds, vectorised | [README](org.radspider.numpy-demo/README.md) |
| `org.radspider.testkit` | 6 | numpy | Every feature: 4 nodes, 4 segmentations, 9 tools (params, units, progress, messages, empty result, error, cancel, charts, pictures, ROIs and segments in and out, an interactive window, icons, a Spanish catalog, several windows per run, an image tool) | [README](org.radspider.testkit/README.md) |
| `org.radspider.sam` | 6 | onnxruntime, torch, medim | Click-prompted segmentation: SAM ViT-B ONNX on slices as OHIF 3.10 (click prompts, slice propagation, bidirectional measurement) and SAM-Med3D in 3D. Replaces `sam-slices` and `sam-med3d` | [README](org.radspider.sam/README.md) |
| `org.radspider.auto-segmentation` | 6 | torch, monai, onnxruntime, numpy, scipy | Automatic CT segmentation with a choice of model: TotalSegmentator v2 3 mm (117 structures, ONNX Runtime), MONAI `wholeBody_ct_segmentation` (104, 3 or 1.5 mm), CADS (167 in nine groups, open weights by default); a window that downloads (in the background, several at once) and deletes the weights. Replaces `totalsegmentator`, `monai-wholebody` and `cads` | [README](org.radspider.auto-segmentation/README.md) |
| `org.radspider.lung-ct-analyzer` | 6 | numpy, scipy | Lung CT analysis by HU range (emphysema, inflated, infiltrated, collapsed) per lung, a threshold lung segmentation, and five density classes of a Gaussian mixture with their volumes. After Slicer's LungCTAnalyzer and DensityLungSegmentation; replaces `density-lung-segmentation` | [README](org.radspider.lung-ct-analyzer/README.md) |
| `org.radspider.radiomics` | 6 | pyradiomics (from GitHub, compiled: needs git and a C compiler), SimpleITK | pyradiomics features of the series' segments in an interactive window. After SlicerRadiomics | [README](org.radspider.radiomics/README.md) |
| `org.radspider.roi-tools` | 6 | numpy, scipy | Eight measurement tools: ROI export, rotation, point interpolation, sphere volumes, ROIs to segments, sector statistics, point counts, region growing | [README](org.radspider.roi-tools/README.md) |
| `org.radspider.volume-tools` | 6 | numpy, scipy | Invert and scale nodes, normalize to a ROI, ΔR2 map, tag-grid merge, rigid registration by mutual information | [README](org.radspider.volume-tools/README.md) |
| `org.radspider.skeletal-radiology` | 6 | numpy, scipy | Automatic and hybrid interactive skeletal radiography measurements: spine (Cobb, balance, wedging), lower-limb alignment (HKA, MAD, mLDFA, MPTA, JLCA, LLD), hip/pelvis (LCEA, Tönnis, CCD), diaphyseal cortical morphometry and foot/hand goniometry | [README](org.radspider.skeletal-radiology/README.md) |
| `org.radspider.measurement-reference` | 6 | Pillow | Searchable guide of radiological measurements (71 entries: how to draw each, reference values, source, a picture). Entries are Markdown files; the user adds or replaces them in `~/radspider-references` | [README](org.radspider.measurement-reference/README.md) |
| `org.radspider.series-identifier` | 6 | numpy, onnxruntime | Says what the image on screen is: series kind, plane or projection, region, laterality, contrast, each with its evidence and a plain explanation (English, Spanish). Rules for every modality; on MR a second opinion from the dcm-classifier ONNX. Educational aid | [README](org.radspider.series-identifier/README.md) |
| `org.radspider.birads` | 8 | stdlib | Structured breast report on a drawable schematic of both breasts: BI-RADS lexicon per finding (mammography, ultrasound, MRI), breast and clock position from the drawing, the reader's categories, ACR hierarchy for the overall assessment (English, Spanish) | [README](org.radspider.birads/README.md) |
| `org.radspider.pirads` | 8 | stdlib | Structured prostate MRI report on a drawable sector map: volume and PSA density, lesions with T2W / DWI / DCE scores, PI-RADS v2.1 category computed per lesion, local staging (English, Spanish) | [README](org.radspider.pirads/README.md) |
| `org.radspider.lirads` | 8 | stdlib | Structured liver CT/MRI report on a drawable Couinaud schematic: observations through the LI-RADS v2018 diagnostic table and ancillary features, or the reader's LR-NC / TIV / 1 / 2 / M, management (English, Spanish) | [README](org.radspider.lirads/README.md) |
| `org.radspider.lungrads` | 8 | stdlib | Structured lung cancer screening CT report on a drawable lung schematic: Lung-RADS v2022 category per nodule or atypical cyst (computed, or assigned where the rules give none), 4X / S / 0, exam management (English, Spanish) | [README](org.radspider.lungrads/README.md) |
| `org.radspider.tirads` | 8 | stdlib | Structured thyroid ultrasound report on a drawable neck schematic: ACR TI-RADS points, level and FNA / follow-up per nodule, lymph nodes per level with ETA 2013 features, optional AJCC 8 clinical TNM of differentiated carcinoma (English, Spanish) | [README](org.radspider.tirads/README.md) |

Model weights are downloaded on first run (see each plugin's `README.md`); none are in this repository. Check each model's licence before shipping it inside a product.

## Versions and marketplace

Each plugin has its own semver `version` in `plugin.toml`. `marketplace/index.json` lists every plugin with its version, `api`, requirements and a package (`<id>-<version>.zip`, GitHub release `<id>-v<version>`) with its SHA-256. A client compares the installed version with the index and updates when the index is higher; the SHA-256 is what it verifies after download. Details, rules and the contract a client follows: [docs/MARKETPLACE.md](docs/MARKETPLACE.md). The repository is private: a client reads it with a read-only fine-grained token, created as described in [SECURITY.md](SECURITY.md#token-for-the-marketplace).

## Repository map

| Path | What |
|---|---|
| `org.radspider.*/` | The plugins. Installable as-is |
| `org.radspider.*/README.md` | One page per plugin: entries, model, limits, licences, "Verified" rows |
| `docs/` | Architecture, development guide, marketplace |
| `tools/validate_plugins.py` | Static checks of every manifest against its module (stdlib only) |
| `tools/marketplace.py`, `marketplace/index.json`, `marketplace/extra.toml` | Package builder, the version index, and the index facts `plugin.toml` cannot carry (`first_run_download`) |
| `tools/semver_vectors.json`, `tools/test_tools.py` | Semver precedence cases shared with radspider, and the tests of the tools |
| `.github/workflows/` | CI: lint + validation on every push; radspider integration tests when a token is configured; `native-plugins.yml` builds and commits the native plugins' executables |
| `AGENTS.md` | The only instructions for AI coding assistants |

## Checks (local)

```bash
python tools/validate_plugins.py      # manifests vs modules, requirements, READMEs (Python ≥ 3.11)
python tools/marketplace.py update    # after any plugin file change: regenerate the index, then commit it
python tools/marketplace.py check     # index is current
python -m unittest discover -s tools  # tests of the tools (semver vectors, requirements lint, index fields)
pip install ruff && ruff check .      # lint
```

## Tests (from the radspider checkout)

```bash
cargo test --test plugins                                              # manifests, stdlib example (needs a Python ≥ 3.10 on PATH or RADSPIDER_PYTHON)
RADSPIDER_PLUGIN_PIP=1 cargo test --test plugins                       # + pip install numpy: numpy demo, test kit (study, window)
```

Check this repo out beside radspider (`../radspider-plugins`) or point `RADSPIDER_PLUGIN_EXAMPLES` at it; the tests skip without it.
The model plugins are not run by the tests (weights, minutes of CPU). Their "Verified" rows in each plugin's `README.md` say what was run by hand and on what.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules on adding or changing a plugin.

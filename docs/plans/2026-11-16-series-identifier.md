# org.radspider.series-identifier 1.0.0 — Implementation Plan

**Goal:** A tool that names the series, the plane or projection, region, laterality and contrast of the image on screen in every modality, explains each in plain words (English + Spanish), and adds dcm-classifier's opinion on MR.

**Architecture:** Three modules in the plugin folder. `seriesid_rules.py` (pure Python, no `radspider_plugin`, no numpy): rules, plane, explanations, dcm-classifier feature vector. `seriesid_model.py` (numpy + onnxruntime, no `radspider_plugin`): download, SHA-256, ONNX session, prediction. `seriesid.py`: the `rp` layer that reads `volume` / `ctx`, calls both, builds the window. Unit tests in `tools/` load the first two by path.

**Tech Stack:** Python ≥ 3.10 syntax (runtime 3.13), `numpy>=1.26`, `onnxruntime>=1.20`, radspider plugin API 6 with `input = "image"`.

**Spec:** `docs/specs/2026-11-16-series-identifier.md`. **Depends on** radspider plan `docs/plans/2026-11-16-plugin-image-input.md` (Tasks 1–6 at least) being in the radspider checkout used for verification.

## Global Constraints

- Plugin id/folder `org.radspider.series-identifier`, version `1.0.0`, `api = 6`, icon `identification-card`, module `seriesid`, one tool `identify`, `input = "image"`, `window = { title = "Series identifier", width = 520, height = 560, reuse = true }`.
- Exactly the 32 tags of spec §1, lower-case `gggg,eeee`.
- Model URL `https://raw.githubusercontent.com/BRAINSia/dcm-classifier/5dcb37384572416da806db69c90bbabcec9819c9/src/dcm_classifier/models/ova_rf_classifier.onnx`, SHA-256 `808fcd58e237ecc3fa657942d325c12ddbbaaf496cc1f849913e99248cba13e0`, 312 427 bytes; env `RADSPIDER_SERIES_ID_MODEL` (a file); cache `RADSPIDER_SERIES_ID_DIR` or `~/.cache/radspider/series-identifier` (same pattern as `org.radspider.cads` `cache_dir`).
- Model classes (index order): `t1w, gret2star, t2w, flair, b0, tracew, adc, fa, eadc, dwig`; low-probability threshold 0.4; missing value −12345.
- Nothing committed that is a weight. AGENTS.md rules 1–9 apply (version, index, CHANGELOG, docs page, README row, English).
- Every UI text through `rp.tr` / `rp.trn`; evidence and tag values unmarked. Footer text exactly: `Educational aid; not for diagnosis.`
- Commit only when the owner asks (stage at the end of each task).

## Review Focus

1. **Every tag `None`** (an anonymised or minimal file): every row answers "not determined: <tag> missing", no exception. (Task 2 test `all_tags_missing`.)
2. **Tag values of unexpected type**: a number where text is expected (e.g. `SeriesDescription` numeric), a list where one number is expected (`ImageType` already joined by `\`, multi-valued `PixelSpacing`), lower-case or padded codes (`"cc "`, `"mlo"`). (Task 2 test `odd_value_types`.)
3. **Offline first run / corrupted cache file / onnxruntime import failure** → rules answer, model row says why; corrupted file deleted. (Task 3 tests.)
4. **Oblique and tilted planes** (normal 45° between axes, gantry tilt 20°) → "oblique, closest to …" with the angle; exactly-on-axis with float noise (1e-7) → the axis. (Task 1 test `plane_classification`.)
5. **Modality missing in `ctx.series`** (older host or no tag) → falls back to inferring from the tags present (MR fields → MR; ViewPosition → projection radiography) and says it inferred. (Task 2 test `modality_inferred`.)

---

### Task 1: Rules core — plane, value helpers, evidence

**Files:**
- Create: `org.radspider.series-identifier/seriesid_rules.py`
- Test: `tools/test_series_identifier.py` (loads the module with `importlib.util.spec_from_file_location`)

**Interfaces:**
- Produces:
  - `Finding = dataclass(frozen=True)(item: str, result: str, evidence: str, explain: tuple[str, ...])` — `item` ∈ `"series", "plane", "projection", "region", "laterality", "contrast", "model"`; `result` and `explain` are English message ids (translated by the rp layer); `evidence` free text (data).
  - `text(v) -> str | None` (str/number/list → stripped upper-case text, `\`-joined lists; `None`/empty → `None`), `number(v) -> float | None`, `numbers(v) -> list[float] | None`.
  - `plane(row, col) -> tuple[str, float, str]` → `(name, degrees_off_axis, nearest)` with `name ∈ {"axial","coronal","sagittal","oblique"}`; within 10.0° of an axis = that axis; `None` vectors → `("unknown", nan, "")`.
- [ ] **Step 1: Failing tests**:
  ```python
  def test_plane_classification(self):
      self.assertEqual(R.plane((1,0,0),(0,1,0))[0], "axial")
      self.assertEqual(R.plane((1,0,0),(0,0,-1))[0], "coronal")
      self.assertEqual(R.plane((0,1,0),(0,0,-1))[0], "sagittal")
      self.assertEqual(R.plane((1,0,1e-7),(0,1,0))[0], "axial")
      name, deg, near = R.plane((1,0,0),(0,0.7071068,-0.7071068))
      self.assertEqual((name, near), ("oblique", "axial")); self.assertAlmostEqual(deg, 45.0, places=3)
      self.assertEqual(R.plane(None, None)[0], "unknown")
  def test_value_helpers(self):
      self.assertEqual(R.text(" mlo "), "MLO"); self.assertEqual(R.text(12.0), "12"); self.assertIsNone(R.text(""))
      self.assertEqual(R.numbers([0.5, 0.5]), [0.5, 0.5]); self.assertIsNone(R.number("x"))
  ```
- [ ] **Step 2:** `python -m unittest tools.test_series_identifier -v` → fails (module missing).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Pass; `ruff check .` clean.
- [ ] **Step 5:** Stage.

### Task 2: Rules per modality

**Files:**
- Modify: `org.radspider.series-identifier/seriesid_rules.py`
- Test: `tools/test_series_identifier.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `identify(tags: dict[str, object], series: dict | None, row, col, color: bool) -> list[Finding]` — `tags` keyed `"gggg,eeee"`; `series` = the `ctx.series` fields as a dict (`modality, images, frames, phases, phase_axis, b_values, gradient_directions, image_types`) or `None`. Data tables as module constants: `CT_KERNELS` (manufacturer → regex → family `bone|lung|soft|brain|other`), `CT_PHASE_WORDS`, `MR_WORDS`, `XR_VIEWS` (ViewPosition code → id), `MG_VIEWS`, `NM_KINDS`; each with a comment naming its source (DICOM PS3.3 C.8.11.5 / C.8.11.7 for views, PS3.16 CID 4014 for mammography views, vendor kernel docs). `EXPLAIN: dict[str, str]` English id → English paragraph (1–3 sentences, spec §5); every `Finding.result` and `explain` id is a key.
- [ ] **Step 1: Failing tests** (one per row of spec §2 at least):
  - `ct_portal`: `{0008,0060 via series "CT", 0018,0010 "OMNIPAQUE", 0008,103e "ABD PORTAL 3mm", 0018,1210 "B30f", 0008,0070 "SIEMENS"}`, axial → series result contains `"Contrast-enhanced CT, portal venous phase"`, kernel family `soft`, plane `axial`.
  - `ct_localizer`: ImageType `ORIGINAL\PRIMARY\LOCALIZER`, row/col of a lateral topogram → series `"CT localizer (scout)"`, projection `"lateral"`.
  - `mr_flair`: TR 9000, TE 120, TI 2500, ScanningSequence `SE\IR` → `"T2 FLAIR"`; `mr_t1_post`: TR 500, TE 10, ContrastBolusAgent `GADOVIST` → `"T1-weighted, post-contrast"`; `mr_dwi_series`: `series.b_values [0, 1000]`, `gradient_directions 3`, ImageType contains `DIFFUSION` → `"Diffusion-weighted (trace)"`; ImageType `ADC` → `"ADC map"`.
  - `pet_ac`: `series.modality "PT"`, Units `BQML`, ImageType `ORIGINAL\PRIMARY`, SeriesDescription `PET AC` → `"PET, attenuation corrected"`; Units `CNTS` without AC → `"PET, not attenuation corrected"`.
  - `cxr_pa`: `CR`, ViewPosition `PA`, BodyPartExamined `CHEST` → projection `"PA"`, region `"Chest"`; `xr_patient_orientation_only`: ViewPosition `None`, PatientOrientation `L\F` → projection `"frontal (from Patient Orientation)"`; `xr_nothing` → `"not determined: ViewPosition and Patient Orientation missing"`.
  - `mg_lmlo`: `MG`, ViewPosition `MLO`, ImageLaterality `L` → `"Left MLO"`; ViewPosition `XCCL` → `"Exaggerated CC (laterally)"`.
  - `xa_lao_cranial`: PrimaryAngle 30, SecondaryAngle 20 → `"LAO 30°, cranial 20°"`; −15 / −10 → `"RAO 15°, caudal 10°"`.
  - `us_colour`: `US`, `color=True` → series `"Ultrasound, colour (Doppler or colour map)"`, projection `"not determined: ultrasound views are not in the header"`.
  - `nm_wholebody`: ImageType `ORIGINAL\PRIMARY\WHOLE BODY\EMISSION` → `"NM whole body"`.
  - `other_modality`: `SR` → `"No rules for modality SR"`.
  - `all_tags_missing`, `odd_value_types`, `modality_inferred` from the Review Focus.
  - `explain_complete`: every id returned by `identify` across all tests above is a key of `EXPLAIN`.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Implement. MR thresholds (TR/TE/TI ranges) as a commented table citing the source (e.g. a standard MR physics text) — no unsourced magic numbers.
- [ ] **Step 4:** Pass; `ruff check .`.
- [ ] **Step 5:** Stage.

### Task 3: dcm-classifier features and model

**Files:**
- Modify: `org.radspider.series-identifier/seriesid_rules.py` (features)
- Create: `org.radspider.series-identifier/seriesid_model.py`
- Create (scratch only, not committed): a parity script in the session scratchpad
- Test: `tools/test_series_identifier.py`

**Interfaces:**
- Produces:
  - `seriesid_rules.FEATURES: tuple[str, ...]` = the 28 names in the order of `dicom_config.py` `inference_features` at commit `5dcb3738…` (`Diffusionb-valueBool, EchoTime, EchoTrainLength, FlipAngle, HasDiffusionGradientOrientation, ImageType_ADC, ImageType_DERIVED, ImageType_DIFFUSION, ImageType_EADC, ImageType_FA, ImageType_ORIGINAL, ImageType_TRACEW, ImagingFrequency, InversionTime, Manufacturer_siemens, NumberOfAverages, PixelBandwidth, RepetitionTime, SAR, ScanningSequence_GR, ScanningSequence_IR, ScanningSequence_SE, SequenceVariant_MP, SequenceVariant_SP, dBdt, has_b0, has_pos_b0, likely_diffusion`).
  - `seriesid_rules.features(tags: dict, has_geometry: bool, has_spacing: bool) -> tuple[list[float] | None, str | None]` → `(vector, None)` or `(None, "<Keyword> missing")` per spec §3 required fields; quirks exactly as spec §3 (substring tests on lower-cased text, `"UnknownScanningSequence"` default, b rounded with Python `round(b/10)*10`, b > 5000 → missing, gradient valid only with 3 components and |‖g‖−1| ≤ 0.01).
  - `seriesid_rules.series_class(label: str, series: dict | None) -> str` — the reference's diffusion update (b > 0 and non-diffusion class → `dwig` if `gradient_directions >= 3` else `tracew`).
  - `seriesid_model.model_path(progress) -> str` (env file → cache file with matching SHA → download with `urllib.request.urlopen(timeout=60)` to `<cache>/ova_rf_classifier.onnx.part`, SHA check, rename; mismatch deletes and raises `ValueError` naming expected/actual hash and `RADSPIDER_SERIES_ID_MODEL`).
  - `seriesid_model.predict(vector: list[float]) -> list[tuple[str, float]]` sorted by probability descending (reads `output_probability[0]` map).
  - `seriesid_model.Unavailable(Exception)` raised (with a user-facing reason) for import failure, download failure, hash mismatch.
- [ ] **Step 1: Failing tests**:
  - `feature_order`: `len(R.FEATURES) == 28` and equals the tuple above.
  - `features_t1`: a Siemens T1 dict (TE 10, TR 500, FA 90, PixelBandwidth 200, ScanningSequence `SE`, SequenceVariant `SP`, ImageType `ORIGINAL\PRIMARY\M\ND`, everything else missing) → `ImageType_ORIGINAL 1`, `Manufacturer_siemens 1`, `ScanningSequence_SE 1`, `SequenceVariant_SP 1`, `InversionTime −12345`, `has_b0 0`, `likely_diffusion 0`.
  - `missing_scanning_sequence_quirk`: ScanningSequence `None` → `ScanningSequence_SE == 1`, `_GR == 0`, `_IR == 0`.
  - `bvalue_rules`: b 1004 → 1000 and `has_pos_b0 1`; b 0 → `has_b0 1`; b 6000 → missing (`Diffusionb-valueBool 0`); gradient `[0, 0.6, 0.8]` valid, `[0, 0.6, 0.9]` invalid.
  - `adc_eadc`: ImageType `DERIVED\PRIMARY\EADC` → `EADC 1, ADC 0`; `...\ADC` → `ADC 1, EADC 0`.
  - `required_missing`: no PixelBandwidth → `(None, "PixelBandwidth missing")`; no geometry → `(None, "Image Orientation missing")`.
  - `series_update`: `series_class("t2w", {"b_values":[0,1000],"gradient_directions":6})` → `"dwig"`; with 1 direction → `"tracew"`; `"adc"` unchanged.
  - model (skipped unless `onnxruntime` imports **and** `RADSPIDER_SERIES_ID_MODEL` points to the file): `predict` on the `features_t1` vector returns 10 pairs summing to 1 ± 1e-5.
  - `hash_mismatch_deletes`: a fake 10-byte file in a temp cache dir (via `RADSPIDER_SERIES_ID_DIR`) and a monkeypatched `urlopen` serving wrong bytes → `Unavailable`, `.part` and file gone; no network.
- [ ] **Step 2:** Run → fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Pass.
- [ ] **Step 5: Parity (scratch).** In a scratch venv install `dcm-classifier` at commit `5dcb3738…` (`pip install "git+https://github.com/BRAINSia/dcm-classifier@5dcb37384572416da806db69c90bbabcec9819c9"`, needs owner OK for the download as it pulls itk/gdcm), run it on `../radspider/test_data/pydicom/MR_small.dcm`, `MR2_UNCR.dcm`, `emri_small.dcm`; dump its 28-vector and class; build ours from the same files' tag values (read with pydicom in the scratch script into our `tags` dict format, applying the host's §2.1 lookup by hand for `emri_small`); compare. Record the result (equal / which feature differs) for the Verified row. If not run, the Verified row says "parity not checked".
- [ ] **Step 6:** Stage.

### Task 4: Plugin shell — manifest, rp layer, translations

**Files:**
- Create: `org.radspider.series-identifier/{plugin.toml, seriesid.py, requirements.txt, NOTICE, lang/es.toml, lang/template.toml}`

**Interfaces:**
- Consumes: `identify`, `features`, `series_class`, `EXPLAIN` (Tasks 2–3), `model_path`, `predict`, `Unavailable` (Task 3); host SDK: `volume.tags`, `volume.tag_source`, `volume.slice_rows/slice_cols`, `volume.spacing_source`, `volume.rgb()`, `ctx.series`, `ctx.image`, `ctx.event`.
- Produces: `@rp.tool("identify") def identify(volume, ctx)` returning `rp.Result(windows=[rp.Window("main", None, blocks)])` with blocks in this order: `rp.Row([rp.Label(<modality · region>), rp.Button("refresh", rp.tr("Refresh"), icon="arrow-clockwise")])`; `rp.Table([[rp.tr("Item"), rp.tr("Result"), rp.tr("Evidence")], …])`; `rp.Section(rp.tr("What this means"), [rp.Label(rp.tr(id)) …], open=True)`; `rp.Section(rp.tr("Model detail"), [top-3 table, 28-feature table with `tag_source`], open=False)` only for MR; `rp.Section(rp.tr("Tags read"), [table], open=False)`; `rp.Label(rp.tr("Educational aid; not for diagnosis."), weak=True)`.
  - Model row: agrees / disagrees with the rules (`"agrees"`, `"differs from the rules"`), `"unreliable: no standard b-value"` when rules say diffusion and `0018,9087` is `None` (no probability shown), `"low probability"` < 0.4, `"model not run: <reason>"` for `features` refusals and `Unavailable`.
  - `ctx.progress(0.2, rp.tr("Downloading the MR model (305 KB)…"))` around the first download.
  - `requirements.txt`: `numpy>=1.26` and `onnxruntime>=1.20  # dcm-classifier's random forest; no torch`.
  - `NOTICE`: dcm-classifier, Apache-2.0, Copyright 2024 Michal Brzus and Hans J. Johnson, the URL and commit, "feature construction reimplemented from dicom_volume.py / utility_functions.py at that commit".
  - `lang/es.toml`: every manifest text, every `rp.tr` id incl. all `EXPLAIN` keys and finding results; `lang/template.toml` regenerated with `python -m radspider_plugin template org.radspider.series-identifier` (SDK `../radspider/assets/python` on `PYTHONPATH`).
- [ ] **Step 1:** Write the files.
- [ ] **Step 2:** `python tools/validate_plugins.py` → clean (manifest ↔ module, `input` accepted after host plan Task 8 changed the validator); `ruff check .` clean.
- [ ] **Step 3:** Template has no warnings about non-literal ids; every key of `template.toml` has a non-empty value in `es.toml` (one-off check: `python -c` comparing the two with `tomllib`).
- [ ] **Step 4:** Stage.

### Task 5: Docs, marketplace, verification in radspider

**Files:**
- Create: `docs/plugins/series-identifier.md` (structure of `docs/plugins/sam-slices.md`: Model, Pipeline, Limits, Speed, Licence, Verified)
- Modify: `README.md` (table row), `CHANGELOG.md` (line), `marketplace/extra.toml` (`"org.radspider.series-identifier" = "Downloads the 305 KB dcm-classifier ONNX model (MR only) from GitHub on first run; everything else works offline."`), `marketplace/index.json` (generated), spec Status
- [ ] **Step 1:** Write docs. Limits must list: 32-tag ceiling (no room for more tags), private b-values unread (classic Siemens/GE/Philips DWI), US projection not in headers, chest view without ViewPosition not determined (no licensed model), MR model provenance (brain MR, enhanced MR training not stated), MPR planes not accepted, educational use only.
- [ ] **Step 2:** `python tools/validate_plugins.py`, `ruff check .`, `python tools/marketplace.py update`, `python tools/marketplace.py check`, `python -m unittest discover -s tools` → all clean.
- [ ] **Step 3:** In radspider (host plan merged into the checkout): Settings → Modules → *Install folder…* this folder; run on `ct-abdomen-portal`, `petct-rider-lung` (PET and CT), `pydicom/MR_small.dcm`, `emri_small.dcm`, `US1_UNCR.dcm`, the CR/DX and MG files the host plan found; once offline (`RADSPIDER_SERIES_ID_MODEL` unset, network off) and once with the model; Spanish once. Write in the Verified row exactly what ran, what each showed, and what did not run.
- [ ] **Step 4:** Stage; report to the owner for commit.

# org.radspider.series-identifier — what series, which plane or projection, in plain words

## TL;DR

- **What:** a tool that looks at the image on screen and says what the series is (CT phase and kernel, MR
  sequence, PET/NM type, radiograph, mammogram, ultrasound, angiography run…), which plane or projection it is (axial /
  coronal / sagittal / oblique; PA / AP / lateral / oblique; CC / MLO / ML…; LAO / RAO cranial / caudal), and a short
  explanation of each in the user's language. Every modality.
- **How:** deterministic rules over DICOM tags and image geometry, for every modality. For MR, a second opinion from
  **dcm-classifier** (BRAINSia, Apache-2.0), a 305 KB random-forest ONNX model over 28 header features, run with
  `onnxruntime`. No pixels are classified: no free model with a usable licence exists for that (research below).
- **Needs:** radspider with plugin API 6 **including** `input = "image"` and `ctx.series`
  (radspider `docs/specs/2026-11-16-plugin-image-input.md`). That lands first.
- **Not:** a diagnostic device. It labels acquisitions; it never reads findings. Unknown stays "not determined" with
  the missing tag named; it never guesses silently.

## Status

| | |
|---|---|
| State | Implemented 2026-11-16 on branch `series-identifier` (plan `docs/plans/2026-11-16-series-identifier.md`), plugin 1.0.0. Where the build differs from this design, the sections below say so. Parity with the reference and the radspider GUI pass were not run at the time of writing; see the Verified row of `docs/plugins/series-identifier.md` |
| Owner's input | "Identify the series and projection in every modality, with a brief explanation; use the new API being merged"; host change over accepting the radiography gap; "Rules + dcm-classifier" over rules only |
| Research (2026-11-16) | dcm-classifier: Apache-2.0, ONNX shipped, header-only, MR only — **used**. TotalSegmentator `totalseg_get_phase`: CT phase, but needs a full segmentation (minutes, torch) — not used, belongs in the TotalSegmentator plugin. `ianpan/chest-x-ray-basic` (AP/PA/lateral): **no licence** — not usable. DICOM-Imaging-Router: weights not published. CardiSort, HD-SEQ-ID, Helm et al.: no weights found. Nothing for MG, US, NM, PET, XA |
| ONNX checked | Downloaded at commit `5dcb37384572416da806db69c90bbabcec9819c9`, 312 427 bytes, SHA-256 `808fcd58e237ecc3fa657942d325c12ddbbaaf496cc1f849913e99248cba13e0`. skl2onnx 1.16.0, opsets ai.onnx 19 + ai.onnx.ml 1, no metadata. Input `float_input` float `[N, 28]`; outputs `output_label` int64 `[N]`, `output_probability` seq(map(int64 → float)), classes 0–9. Ran on onnxruntime 1.32.0, Python 3.13.17 |

## Calls made (owner may overrule)

| # | Call | Why |
|---|---|---|
| 1 | Do **not** depend on the `dcm-classifier` package; reimplement its feature builder (≈ 100 lines) and load its ONNX | The package pulls itk, python-gdcm, pandas, pyarrow, pydicom and reads DICOM files; the plugin gets tag values, not files |
| 2 | The ONNX is **downloaded on first run**, never committed | Repository rule 3 (no weights). URL pinned to the commit above, SHA-256 pinned and checked before loading; `RADSPIDER_SERIES_ID_MODEL=<file>` for offline use; `marketplace/extra.toml` states the download |
| 3 | Without the model (offline, hash mismatch, onnxruntime missing) the tool still answers from the rules and says why the model is absent | Rules are the product; the model is a second opinion |
| 4 | The model result is shown next to the rules, never replacing them; disagreement is flagged | A random forest trained on brain MR from a few sites is not ground truth |
| 5 | On diffusion images whose b-value is only in private tags (classic Siemens / GE / Philips), the model output is shown as *unreliable (no standard b-value)* without a probability | The host reads (0018,9087) only and private tags are refused; four of the 28 features are blind there |
| 6 | Explanations are static texts in the plugin, marked with `rp.tr`, translated in `lang/es.toml` | No network, no LLM; reviewable text |
| 7 | Rules and feature building live in `seriesid_rules.py` with **no** `radspider_plugin` import; `seriesid.py` is the thin rp layer | Lets `tools/` unit-test the logic with plain dicts (`python -m unittest discover -s tools`), since a plugin cannot run outside radspider |
| 8 | One tool, `identify`, `window = { reuse = true }`, a *Refresh* button | The user scrolls to another image or series and refreshes the same window: an image tool follows the active viewport on every run (host spec call 6). On an MPR plane the tool is grey (host call 7) |

## 1. Manifest

```toml
id = "org.radspider.series-identifier"
name = "Series identifier"
version = "1.0.0"
api = 6
icon = "identification-card"
description = "Says what the series on screen is, its plane or projection, and explains both. Rules over DICOM tags for every modality; dcm-classifier (Apache-2.0) as a second opinion on MR."
module = "seriesid"
requirements = "requirements.txt"     # numpy>=1.26, onnxruntime>=1.20

[[tool]]
name = "identify"
label = "Identify series"
input = "image"
window = { title = "Series identifier", width = 520, height = 560, reuse = true }
tags = [ … the 32 below … ]
```

### Tags (32, the API maximum: no headroom)

| Group | Tags |
|---|---|
| All modalities | ImageType 0008,0008 · Manufacturer 0008,0070 · SeriesDescription 0008,103E · ProtocolName 0018,1030 · BodyPartExamined 0018,0015 · SliceThickness 0018,0050 · ContrastBolusAgent 0018,0010 |
| Projection | ViewPosition 0018,5101 · Laterality 0020,0060 · ImageLaterality 0020,0062 · PatientOrientation 0020,0020 · PositionerPrimaryAngle 0018,1510 · PositionerSecondaryAngle 0018,1511 |
| CT | ConvolutionKernel 0018,1210 |
| PET / NM | SeriesType 0054,1000 · Units 0054,1001 |
| MR rules + model | ScanningSequence 0018,0020 · SequenceVariant 0018,0021 · SequenceName 0018,0024 · MRAcquisitionType 0018,0023 · RepetitionTime 0018,0080 · EchoTime 0018,0081 · InversionTime 0018,0082 · NumberOfAverages 0018,0083 · ImagingFrequency 0018,0084 · EchoTrainLength 0018,0091 · PixelBandwidth 0018,0095 · FlipAngle 0018,1314 · SAR 0018,1316 · dBdt 0018,1318 · DiffusionBValue 0018,9087 · DiffusionGradientOrientation 0018,9089 |

All checked against radspider `src/plugins/tags.rs` `denied` and `src/dicom/tag_table.rs`: none refused. Modality,
series counts and series b-values come from `ctx.series`, not tags.

## 2. Rules

Order: modality (`ctx.series.modality`) → series kind → plane / projection → region and laterality → contrast. Each
answer row carries **evidence**: the tag values that decided it.

| Modality | Series kind | Plane / projection |
|---|---|---|
| CT | Localizer (ImageType LOCALIZER) · derived MPR / MIP / MinIP / VRT (ImageType DERIVED + keyword) · non-contrast vs contrast (ContrastBolusAgent; description keywords: arterial, portal, venous, delayed, nephro, angio / CTA, native, sin contraste, …) · kernel family: bone / lung / soft tissue / brain from ConvolutionKernel tables per manufacturer (Siemens Bxx/Ixx/Hr, GE BONE/LUNG/STANDARD/SOFT, Philips letters, Canon FCxx) · dual-energy / mono keV from ImageType | Localizer: frontal / lateral from ImageOrientation; else plane |
| MR | T1, T2, PD, FLAIR, STIR, T2*/SWI, DWI (trace / b-value / directions), ADC, eADC, FA, perfusion, MRA (TOF / PC / CE), 3D vs 2D, fat suppressed (SequenceVariant / ScanOptions-free keywords), post-contrast; from TR / TE / TI / flip angle / ScanningSequence / SequenceVariant / SequenceName / ImageType / description; **plus model** | Plane |
| PT | Attenuation corrected or not (ImageType, description), static / dynamic / gated (SeriesType), SUV vs counts (Units) | Plane (MIP when ImageType says so) |
| NM | Static / whole body / dynamic / gated / tomo (ImageType value 3, the one after PRIMARY / ORIGINAL) | ANT / POST / lateral from description and PatientOrientation |
| CR, DX, RF, PX, IO | Radiograph; region from BodyPartExamined | ViewPosition (AP, PA, LL, RL, LAT, OBL, …) with laterality; else PatientOrientation pair (e.g. `L\F` frontal); else *not determined: ViewPosition empty* |
| MG | Screening view, tomosynthesis (description / ImageType), synthetic 2D | ViewPosition CC / MLO / ML / LM / XCCL / XCCM / AT / SIO … + ImageLaterality → "Left MLO" |
| US | Ultrasound; region from BodyPartExamined / description; colour Doppler if the frame is colour | Not determined from headers; says so |
| XA | Angiography / fluoroscopy run | LAO / RAO from PositionerPrimaryAngle sign, cranial / caudal from Secondary, with degrees |
| Other (OT, SC, SR…) | Modality named, "no rules for this modality" | — |

Plane from `volume.slice_rows` / `slice_cols` (normal = row × col): axial / coronal / sagittal when the normal is
within 10° of an axis, else oblique with the nearest one ("oblique, closest to coronal, 23°"). No geometry → *not
determined: no Image Orientation*.

The exact keyword lists, kernel tables and thresholds (e.g. TR < 800 ms and TE < 30 ms → T1-like) are the builder's,
written as data tables in `seriesid_rules.py` with a comment naming the source of each threshold.

## 3. MR model (dcm-classifier)

- Feature vector: the 28 columns of `inference_features` at the pinned commit, in that order, built exactly as
  `dicom_volume.py` / `utility_functions.py` do there, including: missing value `-12345`; substring tests on lower-cased
  ImageType, ScanningSequence, SequenceVariant, Manufacturer; the `"UnknownScanningSequence"` default (which makes
  `ScanningSequence_SE = 1` when the tag is missing); b-value rounded to 10 and `> 5000` → missing; gradient valid
  only when it has 3 components and |norm − 1| ≤ 0.01. Private-tag branches are dropped (not readable).
- Enhanced MR: the host reads the functional groups and aliases EchoTime / InversionTime (host spec §2.1), so the
  model runs; ScanningSequence stays `None` there, which feeds the reference's own `SE = 1` default. The *Model
  detail* section shows each feature's `volume.tag_source`, and the docs Limits say that whether the model saw
  enhanced MR in training is not stated by its authors.
- **As built:** a missing or empty EchoTime / RepetitionTime does **not** stop the model: both become `-12345` and it
  runs, as the reference does (`utility_functions.py:460-470`). Only FlipAngle, PixelBandwidth, Image Orientation,
  Pixel Spacing and SliceThickness missing give *model not run: <tag> missing* (the reference marks the volume INVALID).
  A kind for which the model has no class (e.g. MRA, perfusion) gets the verdict `no_class` ("no model class") instead
  of *differs*.
- Classes 0–9: `t1w, gret2star, t2w, flair, b0, tracew, adc, fa, eadc, dwig`. Below 0.4 → *low probability*.
- Series step as the reference: when `ctx.series.b_values` has a value > 0 and the class is not a diffusion class,
  ≥ 3 `gradient_directions` → `dwig`, else `tracew`.
- Plane is **not** taken from the model (rules already do it, with oblique).
- Download: `https://raw.githubusercontent.com/BRAINSia/dcm-classifier/5dcb37384572416da806db69c90bbabcec9819c9/src/dcm_classifier/models/ova_rf_classifier.onnx`
  to the plugin's cache folder (same convention as the other downloading plugins), SHA-256 checked before
  `InferenceSession`; a mismatch deletes the file and reports it.
- Licence: Apache-2.0, copyright 2024 Michal Brzus and Hans J. Johnson; attribution in the docs page and in a
  `NOTICE` file in the plugin folder.

## 4. Window

```
┌ Series identifier · image 12/40 ───────────────────────┐
│ MR · Brain                                [↻ Refresh]  │
│ ┌──────────────┬──────────────────────┬──────────────┐ │
│ │ Series       │ T2 FLAIR, 3D         │ TI 2500 · …  │ │
│ │ Plane        │ Sagittal             │ IOP …        │ │
│ │ Contrast     │ No                   │ (0018,0010)… │ │
│ │ Model (MR)   │ flair 0.91 · agrees  │ dcm-classif. │ │
│ └──────────────┴──────────────────────┴──────────────┘ │
│ ▾ What this means                                      │
│   FLAIR: T2-weighted with the fluid signal nulled …    │
│   Sagittal: slices from left to right …                │
│ ▸ Model detail (top 3, features)                       │
│ ▸ Tags read                                            │
│ Educational aid; not for diagnosis.                    │
└────────────────────────────────────────────────────────┘
```

Table columns: *Item · Result · Evidence*. Sections: *What this means* (one paragraph per identified item, open),
*Model detail* (top-3 probabilities and the 28 features; closed), *Tags read* (closed). Every label marked with
`rp.tr`; evidence and tag values unmarked (data).

## 5. Explanations

One entry per identifiable item (≈ 70: each CT phase and kernel family, each MR class and modifier, PET/NM kinds,
each radiographic and mammographic view, XA angulations, each plane, "not determined" reasons). 1–3 sentences,
what it is and what it is typically used for, no findings, no dosing, no clinical advice. English ids in
`seriesid_rules.py`; Spanish in `lang/es.toml`; `lang/template.toml` is regenerated with `python tools/series_identifier_template.py` (which runs the SDK's generator and appends the table-driven ids it cannot see, because the plugin translates them through an alias). Result ids that are not of the "<tag> missing" form (reasons, ranges such as TR / TE cut-offs) are also translatable ids.

## 6. Tests and verification

| Layer | What |
|---|---|
| Unit (`tools/test_series_identifier.py`) | Rules per modality on tag dicts; plane and oblique; the 28-vector for representative MR dicts including every default quirk; model absent / offline / hash mismatch paths (no network: a fake file) |
| Parity | In a scratch venv, run the reference `dcm-classifier` at the pinned commit on the MR files of radspider `test_data/pydicom` and compare its 28-vector and class with ours. Not run → the Verified row says so |
| radspider | Install the folder, run on CT (`test_data/ct-abdomen-portal`), PET (`petct-rider-lung`), and the DX / MG / US / MR files the host plan finds; Spanish |
| Repo checks | `validate_plugins.py`, `ruff`, `marketplace.py update` / `check`, `unittest` |

`docs/plugins/series-identifier.md` with Model, Pipeline, Limits (32-tag ceiling; private b-values; US projection;
model trained on brain MR), Speed, Licence, Verified. README row, CHANGELOG line, `marketplace/extra.toml` line.

## Left to the builder

Keyword lists and thresholds (as data, sourced); explanation wording; Python layout inside the two modules; cache
path helper; which test files to use.

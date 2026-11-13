# radspider-plugins

Python plugins for [radspider](https://github.com/rad-medica/radspider): examples to start from, the test kit, AI segmentation and registration.
Proprietary, all rights reserved (`LICENSE`).

## TL;DR

- One folder per plugin, named exactly as its id: `plugin.toml` + a Python module (+ `requirements.txt`).
- Install one: copy its folder into `<config>/plugins/` (beside `settings.toml`) or in radspider Settings → Modules → *Install folder…* (or *Install .zip…* of the folder). radspider makes the venv and pip-installs `requirements.txt`.
- How plugins work (manifest, SDK, protocol, API 1-3): `docs/PLUGINS.md` in the radspider repository.
- radspider's `tests/plugins.rs` runs these plugins end to end. Check this repo out beside radspider (`../radspider-plugins`) or point `RADSPIDER_PLUGIN_EXAMPLES` at it; the tests skip without it.

## Plugins

| Folder | API | Needs | What |
|---|---|---|---|
| `org.radspider.examples` | 1 | stdlib | One entry of each kind (node, segmentation, tool). Start here |
| `org.radspider.numpy-demo` | 1 | numpy | The same three kinds, vectorised |
| `org.radspider.testkit` | 2 | numpy | Every feature: 4 nodes, 4 segmentations, 7 tools (params, units, progress, messages, empty result, error, cancel, charts, pictures, ROIs and segments in and out, an interactive window) |
| `org.radspider.sam-med3d` | 2 | torch, medim | Click-prompted 3D segmentation, SAM-Med3D turbo checkpoint |
| `org.radspider.monai-wholebody` | 2 | torch, monai | 104 CT structures, MONAI `wholeBody_ct_segmentation` bundle |
| `org.radspider.sam-slices` | 2 | onnxruntime | OHIF 3.10's AI on SAM ViT-B ONNX: click prompts, slice propagation, bidirectional measurement |
| `org.radspider.totalsegmentator` | 2 | onnxruntime (torch once) | 117 CT structures, TotalSegmentator v2 3 mm on ONNX Runtime |
| `org.radspider.registration-demo` | 3 | numpy | The smallest two-volume tool: translation-only registration |

Model weights are downloaded on first run (see each plugin's section); none are in this repository. Check each model's licence before shipping it inside a product.

## Tests (from the radspider checkout)

```bash
cargo test --test plugins                                              # manifests, stdlib example (needs a Python ≥ 3.10 on PATH or RADSPIDER_PYTHON)
RADSPIDER_PLUGIN_PIP=1 cargo test --test plugins                       # + pip install numpy: numpy demo, test kit (study, window), registration demo
```

The model plugins are not run by the tests (weights, minutes of CPU). Their "Verified" rows below say what was run by hand and on what.

## SAM-Med3D plugin

TL;DR: put **Probe** measurements on the object (MPR open on the series), *Segment → Plugins → SAM-Med3D*, get a segment.

| Item | |
|---|---|
| Model | [SAM-Med3D](https://github.com/uni-medical/SAM-Med3D) turbo checkpoint (Apache-2.0 code), downloaded on first run from Hugging Face `blueyo0/SAM-Med3D` (~400 MB, cached by `huggingface_hub`). `RADSPIDER_SAMMED3D_CKPT=<file>` uses a local file instead (offline) |
| Prompts | Probe = positive click; Text measurement reading `-` = negative click. No Probe → the run fails and says so |
| Params | *separate* 1 = one segment per Probe, 0 = all Probes one object; *iterations* decoder passes feeding back the low-res mask; *threshold* of the probability |
| Pipeline | 128³ window at 1.5 mm centred on the clicks, RAS axes (x, y flipped from DICOM LPS), z-normalised over voxels > 0, as upstream `utils/infer_utils.py`; mask resampled back to the volume's grid |
| Limits | One object must fit in 192 mm (clicks further apart fail; negative clicks outside the window are ignored). Assumes slices run inferior → superior. Trained mostly on CT/MR: no PET or ultrasound guarantees |
| Speed | CPU ~6 s per object on a 120×110×90 volume (after model load); uses CUDA if the plugin's torch has it. Requirements: `torch` (default pip wheel: CUDA build on Linux, CPU on Windows/macOS), `medim`, `huggingface_hub` |
| Weights licence | Check the checkpoint's terms on its Hugging Face page before shipping it inside a product |
| Verified | Real turbo checkpoint, CPU, synthetic sphere (anisotropic 1.5 × 1.5 × 2 mm, off-centre click): Dice 0.97, centroid within 0.03 voxel. Not run on a real CT/MR, not run through the viewer GUI |

## MONAI whole body plugin

TL;DR: open MPR on a CT, *Segment → Plugins → MONAI: whole body CT*, get up to 104 segments (organs, vertebrae, ribs, heart,
vessels, bones, muscles). Names: `plugin.py` `NAMES`, same order as the bundle's `metadata.json`.

| Item | |
|---|---|
| Model | MONAI model zoo bundle [`MONAI/wholeBody_ct_segmentation`](https://huggingface.co/MONAI/wholeBody_ct_segmentation) v0.2.7 (SegResNet, Apache-2.0). Weights downloaded on first run (71 MB per resolution, `huggingface_hub` cache); `RADSPIDER_MONAI_WHOLEBODY_WEIGHTS=<file>` for offline. Loaded with `weights_only=True` (plain state dict) |
| Pipeline | `configs/inference.json` rebuilt by hand: RAS, resample 1.5 mm (*highres* 1) or 3 mm (0, default), `NormalizeIntensity(nonzero)`, `ScaleIntensity(-1, 1)`, 96³ Gaussian window, softmax + argmax, nearest back to the series grid. The window keeps one 96-slice band of logits (MONAI's inferer keeps 105 channels of the whole volume: ~20 GB on a body CT at 1.5 mm) |
| Limits | CT in HU only (other units are refused). 1.5 mm needs a few GB of RAM per 100 slices of a body CT (band of fp32, fp16 above 3 GB). Training data: TotalSegmentator dataset (CC BY 4.0, `docs/data_license.txt` of the bundle): keep its notices if shipped |
| Speed | CPU, 3 mm, 122×101×112 voxels: 19 s; 1.5 mm: 79 s. A full body CT takes minutes on CPU; CUDA is used when the plugin's torch has it |
| Verified | Real CT (TotalSegmentator test file `example_ct.nii.gz`, 3 mm, 122×101×112): 3 mm and 1.5 mm runs agree (liver 39-44k voxels, centroids within 3 mm); sides, vertebra order L5→T12 and organ positions anatomically right. **No Dice**: the only reference mask available belongs to a 30-slice crop on which the model is poor. Not run through the viewer GUI |

## SAM slices plugin

TL;DR: the AI part of OHIF 3.10 (Cornerstone3D `packages/ai`) is Meta's **SAM ViT-B**, 2D, as ONNX, plus a geometric
bidirectional measurement. This plugin reproduces the three tools with `onnxruntime`.

| Entry | Does | OHIF equivalent |
|---|---|---|
| segmentation *prompt* | Probe = include marker, Text `-` = exclude marker; each slice holding a Probe is segmented on that slice | Prompt-based segmentation |
| segmentation *propagate* | From a segment, adds slices beyond its first and last: 5 random points of the neighbour's mask prompt SAM | Labelmap Assist |
| tool *bidirectional* | Per segment: slice of largest area, longest diameter, longest chord perpendicular to it, as a `bidimensional` measurement and a table (mm) | Generate Bidirectional Measurement for Segments |

| Item | |
|---|---|
| Models | `sam_vit_b_01ec64.encoder-fp16.onnx` (171 MB) and `sam_vit_b_01ec64.decoder.onnx` (15 MB) from Hugging Face `schmuell/sam-b-fp16`, the files OHIF loads. SAM is Apache-2.0 (Meta); that repo states no licence of its own. Offline: `RADSPIDER_SAM_ENCODER`, `RADSPIDER_SAM_DECODER` |
| Differences from OHIF | (1) The slice keeps its aspect ratio and is zero-padded to 1024², as in Meta's pipeline (OHIF squashes it). (2) Input uses SAM's mean / std; feeding plain [0, 1] (what OHIF's `Tensor.fromImage` call appears to send) gave worse masks in the check below. (3) Propagation clips each new mask to the neighbour's mask grown by 6 mm: without it SAM flooded neighbouring organs |
| Window | SAM sees an 8-bit picture, so *center* / *width* decide what it can separate. Result depends on them (check below: 0.43 with 40/400, 0.93 with 60/350) |
| Limits | 2D only, no memory between slices. 1024² encode on CPU is seconds per slice (CUDA used when onnxruntime has it). Any modality, but the window params are in the series' unit |
| Verified | Real CT (TotalSegmentator `example_ct.nii.gz`, 3 mm, 122×101 slices; MONAI whole-body liver as reference, not a manual mask). *prompt*: one click, Dice 0.93 (60/350) and 0.85 with an extra exclude click; 0.43 with window 40/400. *propagate*: liver from 3 slices, 6 slices each way, Dice 0.50 → 0.87 near the seed, 0.68-0.76 further away, and over-segments. *bidirectional*: checked on synthetic masks (anisotropic spacing) and on that liver (230 × 118 mm). Not run through the viewer GUI. 3 mm slices are about the worst case for SAM; thin-slice, high-resolution CT was not tried |

## TotalSegmentator plugin

TL;DR: open MPR on a CT, *Segment → Plugins → TotalSegmentator*, get up to 117 segments. Inference is ONNX Runtime; PyTorch is
used once, to convert the official weights.

| Item | |
|---|---|
| Model | TotalSegmentator v2 task 297 (`total`, 3 mm, nnU-Net `PlainConvUNet`), code and weights Apache-2.0 per the project. Other TotalSegmentator tasks (1.5 mm parts, MR, commercial ones) are **not** included |
| First run | Downloads `Dataset297_…total_3mm_1559subj.zip` (135 MB) from the GitHub release `v2.0.0-weights`, **checks its SHA-256 against the value pinned in `plugin.py`** (a mismatch deletes the file and stops), loads the checkpoint (a pickle: `weights_only=False`, only after that check) and exports `total_3mm_v2.0.0.onnx` (65 MB) to `~/.cache/radspider/totalsegmentator` (`RADSPIDER_TOTALSEG_DIR`). Later runs never import PyTorch. `RADSPIDER_TOTALSEG_ONNX=<file>` skips all of it |
| Pipeline | As nnU-Net v2 for this trainer (no mirroring): clip to [-1004, 1588], z-score (−50.39 / 503.39), resample to 3 mm, 112×112×128 window, step 0.5, Gaussian weights, argmax of summed logits, banded along z so memory stays bounded. Differences: linear resampling in (nnU-Net: spline order 3) and labels go back to the series grid by nearest neighbour (nnU-Net resamples the logits). *Window step* param trades speed for overlap |
| Limits | CT in HU only. Assumes slices run inferior → superior. 3 mm resolution: small structures (adrenals, small vessels) are coarse |
| Speed | CPU, 122×101×112 voxels: 5.6 s once converted (28.7 s the first time, which includes download and conversion) |
| Verified | Real CT (TotalSegmentator `example_ct_sm.nii.gz`, 30 slices, shorter than the window so the padding path runs) against the project's own `example_seg.nii.gz`: Dice 0.93-0.98 on spleen, kidneys, gallbladder, liver, stomach, lungs, colon, vertebrae; 0.79 pancreas, 0.89 aorta; mean 0.895 over 41 labels. Full `example_ct.nii.gz`: liver Dice 0.97 against the independent MONAI model, organ centroids where expected. SHA-256 mismatch tested (file removed). Not run on a full-body clinical CT, not run through the viewer GUI |

## Registration demo plugin

TL;DR: open two series of the same kind (e.g. two CTs), make the one to keep still the active one, *Plugin tools…* →
*Registration demo · Translation registration* → *Second series* → *Run*. A *Registered (translation)* series
appears; the window shows the offset and the match before and after.

| Item | |
|---|---|
| What it is | The reference for the two-volume API, numpy only. **Translation only**: no rotation, no scaling, no deformation. Not a clinical registration |
| Method | (1) Second series resampled onto the fixed grid through patient coordinates (trilinear) when the grids differ. (2) Peak of the FFT cross-correlation on a coarse copy (≤ 4 M voxels) → whole-voxel shift. (3) Three more passes on a central 128³ block, the last with a parabola through the peak for the fraction. (4) The shifted image (linear, NaN outside) is returned |
| Table | Offset of the second series' content in mm and voxels along the fixed grid's x, y, slice axes; correlation and mean absolute difference before and after; voxels compared |
| Param | *Sub-voxel shift* 1 / 0 |
| Limits | A shift beyond half the volume wraps and is wrong. Cross-correlation needs the same kind of image twice: CT ↔ MR or PET ↔ CT will not work. Different Frames of Reference: the search starts from the coordinates as stored, so it only works when those happen to be close |
| Licence | Own code, numpy (BSD-3-Clause) from pip |
| Verified | `tests/plugins.rs::registration_demo_finds_a_known_translation` (real Python, numpy from pip): six Gaussian blobs moved by (3, −2, 4) mm, once on the fixed grid (40×36×24, 1×1×2 mm) and once on another grid (34×30×22, 1.5×1.5×2.5 mm, other origin): offset within 0.25 mm, correlation < 0.85 → > 0.995, returned voxels compared with the fixed image. Linux GUI (Xvfb, llvmpipe) on the synthetic library's CT and its prior study (128×128×48, 2.5 mm slices, other Frame of Reference, anatomy 45 mm along z): offset 45.7 mm found (0.7 mm off, a quarter of a slice), correlation 0.917 → 0.999, series added and shown. **Not** run on real patient data (no `test_data/` in the cloud container), not on Windows, not on a 512² CT (speed and memory unmeasured) |

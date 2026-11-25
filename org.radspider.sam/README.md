# SAM

Plugin id: `org.radspider.sam` (1.0.0 replaces `org.radspider.sam-slices` and `org.radspider.sam-med3d`; saved parameters of
those do not carry over)

TL;DR: click-prompted segmentation with two models. **SAM ViT-B** (2D, ONNX) reproduces the AI tools of OHIF 3.10
(Cornerstone3D `packages/ai`); **SAM-Med3D** segments one object in 3D. Probe = include / positive click, Text `-` =
exclude / negative click, for both. Requirements are those of both: `onnxruntime` and `torch`, so installing the plugin
installs torch even if only the 2D entries are used.

## SAM on slices (`prompt`, `propagate`, `bidirectional`)

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
| Params | *prompt*: *separate* is a checkbox (off) since 1.1.0 (was a number 0 / 1); *propagate*: *segment* (1 to 64) and *slices* (1 to 200) are whole numbers. *center* and *width* stay decimals |
| API 6 | `api = 6`. Icons (Phosphor): plugin `magic-wand`, *prompt* `cursor-click`, *propagate* `stack-plus`, *bidirectional* `ruler`. Spanish catalog `lang/es.toml` (28 texts with SAM-Med3D's; `lang/template.toml` made with `python -m radspider_plugin template`, SDK on `PYTHONPATH`; regenerate it after changing texts). Error messages (`raise`) are not translated: the protocol has no marked error text |
| Limits | 2D only, no memory between slices. 1024² encode on CPU is seconds per slice (CUDA used when onnxruntime has it). Any modality, but the window params are in the series' unit |
| Verified | Real CT (TotalSegmentator `example_ct.nii.gz`, 3 mm, 122×101 slices; MONAI whole-body liver as reference, not a manual mask). *prompt*: one click, Dice 0.93 (60/350) and 0.85 with an extra exclude click; 0.43 with window 40/400. *propagate*: liver from 3 slices, 6 slices each way, Dice 0.50 → 0.87 near the seed, 0.68-0.76 further away, and over-segments. *bidirectional*: checked on synthetic masks (anisotropic spacing) and on that liver (230 × 118 mm). Not run through the viewer GUI. 3 mm slices are about the worst case for SAM; thin-slice, high-resolution CT was not tried. Run as `org.radspider.sam-slices` 1.1.0; not rerun after the merge into `org.radspider.sam` (module moved unchanged) |

## SAM-Med3D (`segment_3d`)

Put **Probe** measurements on the object (MPR open on the series), run *SAM-Med3D: segment from clicks (3D)*, get a segment. Module `sam_med3d.py`.

| Item | |
|---|---|
| Model | [SAM-Med3D](https://github.com/uni-medical/SAM-Med3D) turbo checkpoint (Apache-2.0 code), downloaded on first run from Hugging Face `blueyo0/SAM-Med3D` (~400 MB, cached by `huggingface_hub`). `RADSPIDER_SAMMED3D_CKPT=<file>` uses a local file instead (offline) |
| Prompts | Probe = positive click; Text measurement reading `-` = negative click. No Probe → the run fails and says so |
| Params | *separate* (checkbox, off) = one segment per Probe, off = all Probes one object; *iterations* (whole number 1 to 5) decoder passes feeding back the low-res mask; *threshold* of the probability. Before 1.1.0 *separate* was a number 0 / 1 and *iterations* a decimal |
| Entry | `segment_3d` (was `segment` in `org.radspider.sam-med3d`), icon `crosshair` |
| Pipeline | 128³ window at 1.5 mm centred on the clicks, RAS axes (x, y flipped from DICOM LPS), z-normalised over voxels > 0, as upstream `utils/infer_utils.py`; mask resampled back to the volume's grid |
| Limits | One object must fit in 192 mm (clicks further apart fail; negative clicks outside the window are ignored). Assumes slices run inferior → superior. Trained mostly on CT/MR: no PET or ultrasound guarantees |
| Speed | CPU ~6 s per object on a 120×110×90 volume (after model load); uses CUDA if the plugin's torch has it. Requirements: `torch` (default pip wheel: CUDA build on Linux, CPU on Windows/macOS), `medim`, `huggingface_hub` |
| Weights licence | Check the checkpoint's terms on its Hugging Face page before shipping it inside a product |
| Verified | Real turbo checkpoint, CPU, synthetic sphere (anisotropic 1.5 × 1.5 × 2 mm, off-centre click): Dice 0.97, centroid within 0.03 voxel. Not run on a real CT/MR, not run through the viewer GUI. Run as `org.radspider.sam-med3d` 1.1.0; not rerun after the merge (module moved unchanged) |

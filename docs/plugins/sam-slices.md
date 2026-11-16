# SAM slices

Plugin id: `org.radspider.sam-slices` · folder: [`../../org.radspider.sam-slices`](../../org.radspider.sam-slices)

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
| Params | *prompt*: *separate* is a checkbox (off) since 1.1.0 (was a number 0 / 1); *propagate*: *segment* (1 to 64) and *slices* (1 to 200) are whole numbers. *center* and *width* stay decimals |
| API 6 (1.1.0) | `api = 6`. Icons (Phosphor): plugin `magic-wand`, *prompt* `cursor-click`, *propagate* `stack-plus`, *bidirectional* `ruler`. Spanish catalog `lang/es.toml` (21 texts; `lang/template.toml` made with `python -m radspider_plugin template`, SDK on `PYTHONPATH`; regenerate it after changing texts). Error messages (`raise`) are not translated: the protocol has no marked error text |
| Limits | 2D only, no memory between slices. 1024² encode on CPU is seconds per slice (CUDA used when onnxruntime has it). Any modality, but the window params are in the series' unit |
| Verified | Real CT (TotalSegmentator `example_ct.nii.gz`, 3 mm, 122×101 slices; MONAI whole-body liver as reference, not a manual mask). *prompt*: one click, Dice 0.93 (60/350) and 0.85 with an extra exclude click; 0.43 with window 40/400. *propagate*: liver from 3 slices, 6 slices each way, Dice 0.50 → 0.87 near the seed, 0.68-0.76 further away, and over-segments. *bidirectional*: checked on synthetic masks (anisotropic spacing) and on that liver (230 × 118 mm). Not run through the viewer GUI. 3 mm slices are about the worst case for SAM; thin-slice, high-resolution CT was not tried |

# SAM-Med3D

Plugin id: `org.radspider.sam-med3d` · folder: [`../../org.radspider.sam-med3d`](../../org.radspider.sam-med3d)

TL;DR: put **Probe** measurements on the object (MPR open on the series), *Segment → Plugins → SAM-Med3D*, get a segment.

| Item | |
|---|---|
| Model | [SAM-Med3D](https://github.com/uni-medical/SAM-Med3D) turbo checkpoint (Apache-2.0 code), downloaded on first run from Hugging Face `blueyo0/SAM-Med3D` (~400 MB, cached by `huggingface_hub`). `RADSPIDER_SAMMED3D_CKPT=<file>` uses a local file instead (offline) |
| Prompts | Probe = positive click; Text measurement reading `-` = negative click. No Probe → the run fails and says so |
| Params | *separate* (checkbox, off) = one segment per Probe, off = all Probes one object; *iterations* (whole number 1 to 5) decoder passes feeding back the low-res mask; *threshold* of the probability. Before 1.1.0 *separate* was a number 0 / 1 and *iterations* a decimal |
| API 6 (1.1.0) | `api = 6`. Icons (Phosphor): plugin `cube`, *segment* `crosshair`. Spanish catalog `lang/es.toml` (9 texts; `lang/template.toml` made with `python -m radspider_plugin template`, SDK on `PYTHONPATH`; regenerate it after changing texts). Error messages (`raise`) are not translated: the protocol has no marked error text |
| Pipeline | 128³ window at 1.5 mm centred on the clicks, RAS axes (x, y flipped from DICOM LPS), z-normalised over voxels > 0, as upstream `utils/infer_utils.py`; mask resampled back to the volume's grid |
| Limits | One object must fit in 192 mm (clicks further apart fail; negative clicks outside the window are ignored). Assumes slices run inferior → superior. Trained mostly on CT/MR: no PET or ultrasound guarantees |
| Speed | CPU ~6 s per object on a 120×110×90 volume (after model load); uses CUDA if the plugin's torch has it. Requirements: `torch` (default pip wheel: CUDA build on Linux, CPU on Windows/macOS), `medim`, `huggingface_hub` |
| Weights licence | Check the checkpoint's terms on its Hugging Face page before shipping it inside a product |
| Verified | Real turbo checkpoint, CPU, synthetic sphere (anisotropic 1.5 × 1.5 × 2 mm, off-centre click): Dice 0.97, centroid within 0.03 voxel. Not run on a real CT/MR, not run through the viewer GUI |

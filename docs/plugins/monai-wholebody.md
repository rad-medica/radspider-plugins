# MONAI whole body

Plugin id: `org.radspider.monai-wholebody` · folder: [`../../org.radspider.monai-wholebody`](../../org.radspider.monai-wholebody)

TL;DR: open MPR on a CT, *Segment → Plugins → MONAI: whole body CT*, get up to 104 segments (organs, vertebrae, ribs, heart,
vessels, bones, muscles). Names: `plugin.py` `NAMES`, same order as the bundle's `metadata.json`.

| Item | |
|---|---|
| Model | MONAI model zoo bundle [`MONAI/wholeBody_ct_segmentation`](https://huggingface.co/MONAI/wholeBody_ct_segmentation) v0.2.7 (SegResNet, Apache-2.0). Weights downloaded on first run (71 MB per resolution, `huggingface_hub` cache); `RADSPIDER_MONAI_WHOLEBODY_WEIGHTS=<file>` for offline. Loaded with `weights_only=True` (plain state dict) |
| Pipeline | `configs/inference.json` rebuilt by hand: RAS, resample 1.5 mm (*highres* 1) or 3 mm (0, default), `NormalizeIntensity(nonzero)`, `ScaleIntensity(-1, 1)`, 96³ Gaussian window, softmax + argmax, nearest back to the series grid. The window keeps one 96-slice band of logits (MONAI's inferer keeps 105 channels of the whole volume: ~20 GB on a body CT at 1.5 mm) |
| Limits | CT in HU only (other units are refused). 1.5 mm needs a few GB of RAM per 100 slices of a body CT (band of fp32, fp16 above 3 GB). Training data: TotalSegmentator dataset (CC BY 4.0, `docs/data_license.txt` of the bundle): keep its notices if shipped |
| Speed | CPU, 3 mm, 122×101×112 voxels: 19 s; 1.5 mm: 79 s. A full body CT takes minutes on CPU; CUDA is used when the plugin's torch has it |
| Verified | Real CT (TotalSegmentator test file `example_ct.nii.gz`, 3 mm, 122×101×112): 3 mm and 1.5 mm runs agree (liver 39-44k voxels, centroids within 3 mm); sides, vertebra order L5→T12 and organ positions anatomically right. **No Dice**: the only reference mask available belongs to a 30-slice crop on which the model is poor. Not run through the viewer GUI |

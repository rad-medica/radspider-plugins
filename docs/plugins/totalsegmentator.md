# TotalSegmentator

Plugin id: `org.radspider.totalsegmentator` · folder: [`../../org.radspider.totalsegmentator`](../../org.radspider.totalsegmentator)

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

## API 6 (1.1.0)

| Feature | Where |
|---|---|
| Icons | Plugin and entry: `bone` (Phosphor) |
| Spanish | `lang/es.toml`: every manifest text and every progress message. `lang/template.toml`: `python -m radspider_plugin template org.radspider.totalsegmentator` (SDK on `PYTHONPATH`) |
| Params | `overlap_step` stays a number (a fraction, not a count or a pick) |

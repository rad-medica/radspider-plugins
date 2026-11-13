# Registration demo

Plugin id: `org.radspider.registration-demo` · folder: [`../../org.radspider.registration-demo`](../../org.radspider.registration-demo)

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

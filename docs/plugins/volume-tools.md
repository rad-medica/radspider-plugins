# Volume tools

Plugin id: `org.radspider.volume-tools` · folder: [`../../org.radspider.volume-tools`](../../org.radspider.volume-tools)

TL;DR: six entries that reproduce the behaviour of five plugins of the Horos / OsiriX plugin collection (*Invert
Data*, *Normalize*, *T2 Ratio Map*, *Cardiac Tagging MRI*, *PetSpectFusion*) with numpy and scipy. Two are series
builder nodes, one is a one-series tool, three are two-volume tools (*Plugin tools…* → *Second series* → *Run*):
the active series is the first / fixed one, the result is a new series on its grid.

| Entry | Kind | Does | Original |
|---|---|---|---|
| *Invert Data* `invert` | node | x → −x | Invert Data |
| *Scale* `scale` | node | x → factor · x | Normalize, step 2 |
| *Normalize* `normalize` | tool | Mean inside a closed measurement or a segment, and factor = target / mean | Normalize, step 1 |
| *T2 Ratio Map* `delta_r2_map` | two-volume tool | ΔR2 = −(factor / TE) · ln(second / active), map + statistics + histogram | T2 Ratio Map |
| *Cardiac Tagging MRI* `merge_tag_grids` | two-volume tool | Product of two tagged series, slice maxima equalised | Cardiac Tagging MRI |
| *PetSpectFusion* `rigid_register` | two-volume tool | 6-parameter rigid registration by mutual information, multi-resolution | PetSpectFusion |

## Invert Data

| Item | |
|---|---|
| Formula | `out = −x`. Plain negation, as the original does to grey images: **not** `max + min − x`. NaN (no data) stays NaN |
| Unit | `none`: a negated HU value is not a HU value |
| Differences | The original changes the open series in place and flips the window level; a node makes a new series and the window is the viewer's. Its RGB branch (`255 − x`) has no counterpart: a node gets one value per voxel |

## Normalize (tool) + Scale (node)

| Item | |
|---|---|
| Original | One dialog: mean of the selected ROI on the image on screen, target ↔ factor, OK multiplies every voxel of the series by the factor |
| Here | **Two steps**, because a node gets only the volume (no ROIs, no segments) and a one-series tool cannot return a series. (1) Run *Normalize*: it reports mean, SD, min, max, voxel count, `factor = target / mean` and the series builder text `plugin("org.radspider.volume-tools/scale", x, <factor>)`. (2) In the series builder, add *Volume tools · Scale* with that factor |
| Region | *Segment number* 0: a closed measurement (polygon or ellipse; voxels whose centre lies inside). ≥ 1: that segment, counted from the top of the Segments panel |
| Which measurement | The viewer passes neither the selection nor the drawing time. Used: the last closed measurement listed on the slice on screen, else the last one listed (order: by image, then as listed on the image). The table names the one used: check it, or keep one closed measurement on the series |
| No cleaner way | Looked for one: a two-volume tool could return the scaled series, but the *Second series* list holds only *other* series, so the same series cannot be given twice. One click needs R12 (below) |
| Errors | No closed measurement, no segmentation, segment number too high, region without data, mean 0: each says what to do |

## T2 Ratio Map

| Item | |
|---|---|
| Series | Active = pre-contrast (v1), second = post-contrast (v2), as in the original (post dropped on pre) |
| Formula | `ΔR2 = −(factor / TE) · (ln v2 − ln v1)`. The original's *K* field is the echo time **TE in ms** (default 20) and it multiplies by a *Multiplication Factor* (default 1000): the defaults give ΔR2 in 1/s |
| Where | Both series above *Intensity threshold* (default 1). Region 0 = automatic: inside the closed measurements when the series has any (each on its own slice; slices without one are empty), else inside the visible segments, else everywhere. −1 = whole volume, n = segment n |
| Second series | Used as is on an identical grid. On another grid: resampled onto the active grid through patient coordinates (trilinear, z bands of ≤ 4 M voxels), **only** when the two share a Frame of Reference; otherwise refused with what to do (register first) |
| Output | Series *Delta R2 map (TE … ms)*, unit `none`; table: mean, SD, minimum, maximum, voxel count; histogram of 64 bins between the 0.5th and 99.5th percentile |
| Differences | (1) The original tests `v1 > threshold` and a fixed floor `v1 > 1`, `v2 > 1`; here one threshold applies to both series, default 1, so the defaults agree. (2) Voxels not computed are no data (stored as 0 by the host), where the original writes 0, and the smallest map value outside the ROI. (3) The original needs equal image counts and pairs images by index; here voxels are paired by position. (4) ROI mode there = the ROIs named like the selected one; here every closed measurement, or segments. (5) Statistics and histogram are additions |

## Cardiac Tagging MRI

| Item | |
|---|---|
| Combination | **Product** (not minimum, not mean): `slice = v1 · v2 ÷ (max − min of the v1 slice)`, then, with *Equalize* 1 (as the original), every slice is multiplied by `largest slice maximum ÷ its own maximum` |
| Series | The original takes **one** stack and multiplies its first half by its second half, image by image. Here the two halves must be **two series**: active = one tag direction, second = the other, same slices. A volume is one phase of a cine: run it per phase |
| Second series | Same rule as the ratio map: identical grid, or same Frame of Reference (resampled), else refused |
| Differences | The original stores each slice maximum as an integer before dividing (truncation); here it is not truncated. A slice whose maximum is not above 0 is left unscaled (the original divides by 0). Output unit `none` |

## PetSpectFusion (rigid registration)

| Item | |
|---|---|
| Transform | Fixed → moving patient position: `q = R (p − c) + c + t`, `R = Rz · Ry · Rx` (angles about the patient x, y, z axes, degrees), `t` in mm, `c` = centre of the active series. The table gives the three angles, `t`, `c` |
| Metric | Mutual information (nats) of a joint histogram, *Histogram bins* per image over the 0.5th–99.5th percentile, each sample spread linearly over the two nearest bins of both images (first-order Parzen window). Samples: voxels of the fixed copy, at most *Samples per level* (a fixed-seed random subset). Poses leaving < 25 % of the samples inside the moving image are not scored |
| Pyramid | *Pyramid levels* copies by block means; the finest has voxels of max(smallest fixed voxel, ∛(volume / 2 M)) mm, each coarser level twice that. Work is on these copies, never on the full volume |
| Search | `scipy.optimize.minimize(method="Powell")` per level, ≤ 500 evaluations, parameters scaled so one unit moves the image edge by one voxel of the level. Progress per level |
| Start | Same Frame of Reference: identity (patient coordinates). Otherwise, or *Start* 1: centres of mass laid on each other |
| Output | Series *Registered (rigid)*: the second series on the active grid (trilinear, NaN outside, z bands), unit of the second series (`keep`). Table: angles, translation, MI before and after on the finest copies, coverage, one row per level |
| Differences | The original runs ITK: Mattes MI with B-spline Parzen windows (75 bins, 70 % of voxels), versor rigid transform, regular-step gradient descent (≤ 250 iterations), multi-resolution optional (3 levels from shrink 8), start from the geometric centres, and manual nudging of the transform in its window. Here: linear Parzen windows, Euler angles, Powell, multi-resolution always, start from patient coordinates or centres of mass, no manual nudging. Results are not numerically comparable with ITK's |
| Limits | Rigid only: no scaling, no deformation. A start more than about a quarter of the image away or rotated by tens of degrees is not found. Accuracy is bounded by the finest copy (2.7 mm voxels on a 512 × 512 × 300, 0.7 mm CT). `spacing[2]` is the mean slice step: gantry-tilted or uneven stacks are approximate. NaN in the moving image grows by one voxel when resampled |

## Not possible in API 3

| Original | Why not |
|---|---|
| Reduce Series | Output has fewer voxels than the input |
| Resample Data | Output has another matrix and spacing |
| Orthogonal Reslice | Output lies on another grid (other axes) |

A node and a two-volume tool return exactly one value per voxel of the input grid; a one-series tool returns no
series. All three need requirement **R12** (*volumes out, on any grid, from any tool*) of radspider
`docs/superpowers/specs/2026-11-13-plugin-api-requirements.md`. They are not faked here.

## Facts

| Item | |
|---|---|
| Memory | Both volumes and the result in RAM as float32, plus z bands of ≤ 4 M voxels: 1.3 GB peak measured for 512 × 512 × 300 + 256 × 256 × 150 |
| Speed | Synthetic 512 × 512 × 300 ← 256 × 256 × 150 on a cloud Linux CPU: registration 27 s, ratio map with resampling 9 s |
| Licence / origin | Own code, written from the observed behaviour of the plugins named above in the Horos / OsiriX plugin collection (GPL or all rights reserved): nothing translated or copied. numpy and scipy (BSD-3-Clause) from pip |
| Verified | **Synthetic data only, outside the viewer**: a throw-away script driving the real SDK request path (`radspider_plugin._handle`: request, files, reply) with numpy 2.5.4, scipy 1.18.1, Python 3.13, Linux. **Not run in radspider, no real data, not on Windows.** *invert*: −x exact, NaN kept, round trip bit-identical. *normalize* + *scale*: polygon of 12 voxels, mean 2303.5 = hand value, factor 0.043412199, ROI mean after *scale* 99.999997; ellipse 13 voxels; segment 6 voxels; the two refusals. *delta_r2_map*: constants 200 → 100, TE 20 ms, × 1000: 34.65736 everywhere (= 50 ln 2); second series on a finer shifted grid: the 1700 covered voxels exactly, NaN outside; polygon, segment and threshold regions; other Frame of Reference refused on another grid, accepted on the identical one. *merge_tag_grids*: 2 × 2 × 2 against hand values. *rigid_register*: 14-Gaussian phantom, 96 × 96 × 64 at 1.5 × 1.5 × 2.5 mm against a moving copy on another grid (84 × 80 × 56, 2 × 2 × 3 mm) with inverted non-linear contrast, moved by (4, −3, 6)° and (7, −5, 6) mm: rotation error 0.013°, blob-centre error ≤ 0.021 mm, MI 0.473 → 1.250; with noise (σ 0.05): 0.18°, ≤ 0.24 mm; other Frame of Reference, (−5, 4, 8)° and (30, −22, 18) mm from centres of mass: 0.019°, ≤ 0.031 mm. Smooth synthetic 512 × 512 × 300: 0.08°, 0.03 mm. Noise-free phantoms flatter the figures: PET ↔ CT, MR ↔ CT and partial fields of view were not tried |

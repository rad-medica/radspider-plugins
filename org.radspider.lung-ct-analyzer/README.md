# Lung CT analyzer

Plugin id: `org.radspider.lung-ct-analyzer`

TL;DR: the analysis of the 3D Slicer extension **LungCTAnalyzer** (R. Bumm,
[rbumm/SlicerLungCTAnalyzer](https://github.com/rbumm/SlicerLungCTAnalyzer), read at commit `e2f23da`): inside a
right and a left lung mask every voxel gets one of five classes by its Hounsfield value, and the volumes are
reported per lung. Re-implemented with numpy and scipy; no code of the extension is in the plugin. CT in HU only.
**Not clinically evaluated** (upstream says the same of its own results).

Since 1.2.0 it also holds the density classes of **DensityLungSegmentation** (entries *gmm*, *gmm_averaged*, *volumes*,
module `lung_density.py`; see *Density classes* below). They replace `org.radspider.density-lung-segmentation`, with the
same entry names and parameters; they keep their own lung mask (threshold −155 HU, 30 / 20 voxel closing), not the one
of *lungs*.

| Entry | Does | Slicer equivalent |
|---|---|---|
| tool *analyze* | Classes inside the lung masks, table in ml and %, two charts, one segment per class and lung; interactive | Lung CT Analyzer |
| segmentation *lungs* | Right lung, left lung, trachea by thresholding and connected components | Lung CT Segmenter without AI (there: 13 hand-placed seeds + grow from seeds; here: no seeds) |

| Class (segment `<name> right` / `<name> left`) | HU, defaults | Param |
|---|---|---|
| Emphysema | below −950 | `emphysema_max` |
| Inflated | −950 … −750 | `inflated_max` |
| Infiltration | −750 … −400 | `infiltrated_max` |
| Collapsed | −400 … 0 | `collapsed_max` |
| Vessels | 0 and above | |

A limit belongs to the class above it (`lower <= HU < upper`). Source of the defaults:
`LungCTAnalyzer/LungCTAnalyzer.py`, `LungCTAnalyzerLogic.__init__`, `defaultThresholds` (−1050, −950, −750, −400, 0,
3000) and `segmentProperties`; applied in `createThresholdedSegments`.

| Item | |
|---|---|
| Method | No model. HU thresholds inside lung masks; voxel count × voxel volume |
| Lung masks | (1) From the series' segments when it has them, by name, case and `_` ignored: a side word (`right` / `left`) plus `lung` or `lobe`: `Right lung`, `left lung mask` (upstream's names), `lung_upper_lobe_left` (TotalSegmentator, MONAI whole body), `right upper lobe`; lobes of a side are joined. One segment named `lung` / `lungs` is split in two. Names holding `vessel`, `nodule`, `trachea`, `airway`, a class name … are ignored. (2) Otherwise made as the *lungs* entry does, with its defaults. The window's status line says which |
| Pipeline, *analyze* | Masks → class per voxel → table: per area (total, right, left, and each lobe segment found) *Total* = emphysema + inflated + infiltrated + collapsed (vessels are **not** part of the lung volume, as upstream), *Functional* = inflated + emphysema, *Affected* = infiltrated + collapsed, each in ml and % of *Total*, plus vessels in ml and AF-Q. Charts: ml per class and lung (bars); density inside the masks (10 HU bins). Source: `calculateStatistics`, `createCovidResultsTable` |
| Window | Four sliders (the class limits, kept in rising order), *Count emphysema as affected* (upstream's `countBullae`: emphysema moves from functional to affected; off by default as there), *Add segments*. Segments are returned on the first run and on that button, not on slider moves |
| AF-Q | Affected / functional. Upstream's help text names a "CovidQ" and `versionhistory.txt` says "COVID-Q renamed to AF-Q", but the source read here holds **no formula** for it: this ratio is our reading of the name, not upstream's code |
| Pipeline, *lungs* | (1) Per slice: body = largest piece of tissue (HU ≥ threshold) with its holes filled; air inside it. (2) 3D: largest piece of that air, and the second if ≥ 20 % of it; under 100 ml → error. (3) Trachea: from the cranial end, a compact piece of 30–1200 mm² within 15 % of the lungs' width from their middle, followed slice by slice while the overlapping pieces stay below 3× its area (≤ 1500 mm²) and for at least 20 mm; it ends where the bronchi open into the lungs. (4) Right / left: two large pieces as they are; one piece is eroded 1–8 mm until it falls apart and regrown; else cut at the thinnest column near the middle. (5) Closing with a 12 mm kernel (6 mm ball, fills vessels), Gaussian SD 2 mm, cut at 0.5. Threshold −400 HU, 12 mm and 2 mm are upstream's (`LungCTSegmenter/LungCTSegmenter.py`: `setDefaultParameters`, `applySegmentation`) |
| Differences from upstream | (1) No seeds: upstream grows from 6 + 6 + 1 points the user places; steps 1–4 above are ours. (2) Percentages with one decimal (upstream rounds functional / affected to whole numbers). (3) Upstream's code slips are not copied: `np.logical_and` with three arguments (the upper limit is taken as the output array, so the 3000 HU vessel limit has no effect; the result is the same as here since classes are written in rising order), `functionalTotalVolume` without emphysema while the per-lung figures include it, `Emphysema right` used for the left lung in the lobe figures. (4) The lower emphysema limit is the volume's minimum, as upstream sets it at run time. (5) The trachea is not closed or smoothed |
| Not reproduced | Regional analysis (ventral / dorsal / upper / middle / lower thirds), PDF report, volume rendering of the masked volume, batch processing, the AI engines of Lung CT Segmenter (lungmask, TotalSegmentator, MONAI: use `org.radspider.totalsegmentator` or `org.radspider.monai-wholebody`, whose lobe segments *analyze* picks up), detailed airways, vessel masks |
| Orientation | Right / left from the volume's row, column and slice vectors; without them (never the case for a series in the viewer) a standard axial image is assumed, columns growing to the patient's left. Trachea needs axial slices; the cranial end comes from the slice vector, or both ends are tried |
| Limits | Units: a series that is not in HU is refused (also one with no unit). Threshold lung masks miss what is denser than the threshold at the lung surface: consolidation or effusion against the pleura is left out, so infiltrated and collapsed volumes are **under-estimated** with these masks; use AI lung masks for diseased lungs. Bronchial air inside the masks counts as emphysema. Kernel, slice thickness and contrast change HU and so the classes. Lungs joined over a long stretch may be split in the wrong place. Bowel gas larger than 20 % of the lungs would be taken for a lung |
| Speed | Synthetic 512 × 512 × 300 volume (0.7 × 0.7 × 1 mm, lungs of 6.0 and 5.2 M voxels), 4 CPU cores: *lungs* 28 s, *analyze* without segments 29 s, peak memory 2.6 GB. *analyze* with masks from segments: under a second on the small phantom, not timed on the large one |
| Licence | Plugin: own code. Upstream LungCTAnalyzer: **Apache-2.0** (`LICENSE` in its repository); used here for behaviour, names and default limits only, no source copied. numpy, scipy: BSD-3-Clause, from pip |
| Verified | **Synthetic volumes only, entries called through the SDK's request handler (`radspider_plugin._handle`) in a plain Python 3.13 venv (numpy 2.5.4, scipy 1.18.1) outside the viewer. Not run in radspider, not on real CT, not compared with 3D Slicer's output.** Phantom: 160 × 120 × 80 voxels of 1 × 1 × 2 mm, body ellipsoid at 40 HU, two ellipsoid lungs at −850 HU (111 049 and 89 913 voxels) with box patches at −980, −600, −200 and +50 HU of known voxel counts, a −1000 HU trachea cylinder (6 895 voxels) joined to both lungs by a bar. *analyze* with segments `Right lung` / `left lung mask`: voxel count of each of the 10 labels equals the known counts, every table cell (ml, %, AF-Q) of the three rows equals the hand-computed value to the rounding, bars equal the counts, decoy segments `Emphysema right` and `Healthy lungs` ignored. Re-runs with controls: moved limit, emphysema as affected, segments only on first run and button, limits forced into rising order. Lobe segments with TotalSegmentator names, one lung only, one `Lungs` segment split in two. *lungs* without closing and smoothing: trachea = the cylinder exactly, lungs = all other enclosed air, each ellipsoid wholly on its side, nothing outside the body; same result with slices reversed, columns mirrored, no placement; lungs joined by a thin bridge still split; a volume without air raises the "No lungs found" error. *lungs* with defaults: Dice 0.995 and 0.995 against the ellipsoids, the −200 and +50 HU patches filled. *analyze* without segments: table equals the HU classes inside those masks, total within 3 % of the phantom. Every entry refuses `SUVbw` and no unit |

## API 6 (1.1.0)

| Item | |
|---|---|
| API | `api = 6` (was 2): icons, Spanish catalog. Algorithms and outputs are those of 1.0.0 |
| Icons | Plugin and *lungs*: `wind`. *analyze*: `chart-bar` |
| Parameters | `trachea` (0 / 1) is now a `bool` (default on). The limits and the two millimetre values stay numbers |
| Translations | `lang/es.toml` (52 texts in 1.1.0; 79 with the density entries since 1.2.0): manifest, progress messages, table headers and row labels (*Total lungs*, *Right lung*, *Left lung*), chart titles, axis labels and series names, the window's controls, the result message. Not marked, on purpose: the names of the segments it creates and the names of the series' own segments (study data), error texts. `lang/template.toml`: `python -m radspider_plugin template org.radspider.lung-ct-analyzer` |

## Density classes (*gmm*, *gmm_averaged*, *volumes*)

The *Lung CT GMM Segmentation* module of the 3D Slicer extension **DensityLungSegmentation** (P. Zaffino et
al., [pzaffino/SlicerDensityLungSegmentation](https://github.com/pzaffino/SlicerDensityLungSegmentation), read at
commit `cd207de`): a lung mask by threshold and morphology, then each voxel inside gets the most likely of five
density classes of a **fixed** Gaussian mixture fitted on COVID-19 CTs. Re-implemented with numpy and scipy. CT in HU
only. **Not clinically evaluated.**

| Entry | Does | Slicer equivalent |
|---|---|---|
| segmentation *gmm* | Five segments, one class per voxel | Output segmentation |
| segmentation *gmm_averaged* | The same after a 4 × 4 × 4 voxel median of the labels | Averaged output segmentation |
| tool *volumes* | The same (param *averaged*, a checkbox) with volume in ml, share of the lung mask and mean HU per class, a bar chart and the segments | — (ours) |

| Label | Segment | Mixture: weight, mean HU, SD HU | Wins for HU |
|---|---|---|---|
| 1 | Air | 0.339, −950.4, 44.0 | below −893.5 |
| 2 | Healthy lungs | 0.362, −829.0, 58.4 | −893.5 … −721 |
| 3 | Ground glass opacity | 0.139, −652.3, 94.5 | −721 … −472 |
| 4 | Consolidation | 0.055, −337.0, 156.7 | −472 … −235 |
| 5 | Other denser tissues | 0.106, −12.5, 194.0 | −235 and above |

The mixture parameters are the `weights_`, `means_` and `covariances_` stored in upstream's
`LungCTGMMSegmentation/Resources/GMM_parameters_COVID-19.joblib` (a scikit-learn `GaussianMixture`, 5 components,
1 feature; SHA-256 `05297ccedfc8e4d9750a2d4e56a2e077b521c54367b8a48e713e0e19082adc12`), read out of the file without
unpickling it and kept as constants in `lung_density.py`. The "wins for" limits follow from them (computed in 0.5 HU
steps); upstream has no explicit thresholds for the classes.

| Item | |
|---|---|
| Model | The fixed mixture above; nothing is fitted to the series, nothing is downloaded, no pickle is loaded, scikit-learn and joblib are not needed. Paper: Zaffino et al., "An Open-Source COVID-19 CT Dataset with Automatic Lung Tissue Classification for Radiomics", Bioengineering 8(2):26, 2021 |
| Pipeline | As `LungCTGMMSegmentationLogic.run` in `LungCTGMMSegmentation/LungCTGMMSegmentation.py`: (1) HU below −1000 set to −1000. (2) Air = HU < **−155**, binary opening, 3 iterations (`threshold_image`). (3) 3D islands of at least **500 000 voxels** whose bounding box does not reach the first or last row or column are lung; the rest (the air around the patient, small pockets) is dropped (`extract_only_lungs_islands`). (4) Closing with a ball of **30** then **20 voxels** on the lungs' bounding box (`close_lungs_mask`); 1000 voxels or fewer → error. (5) Most likely mixture component per voxel of the mask, labels 1–5 by rising mean. (6) Averaged output: median filter of size **4** on the labels |
| Params | *Lung threshold* (−155 HU) and *Smallest lung island* (500 000 voxels, a whole number since 1.1.0) are upstream's constants made adjustable: the island size is in voxels, so a thick-slice or small series needs a lower one, and the error says so. *Averaged labels* of *volumes* is a checkbox (was a number 0 / 1) |
| Icons | *gmm* `wind`, *gmm_averaged* `waves`, *volumes* `chart-bar` |
| Translated | The class names in the table's first column, the headers, chart title and labels, the message and the progress texts. The segment names stay English: they are study data |
| Differences from upstream | (1) Closing by two Euclidean distance transforms instead of SimpleITK's kernel: the same operation with an exact ball, whereas ITK's ball element is a slightly different digital ball, so the mask edge can differ by a voxel. (2) Upstream's island loop runs `range(nb_labels)` over labels `0 … nb_labels` and so never looks at the last island; here every island is looked at. (3) Upstream's bounding box drops the last slice, row and column of the lungs (exclusive slice end); not copied. (4) The median runs on the box around the mask (4 voxel margin) instead of the whole volume: same result, less time. (5) No data (NaN) is treated as −1000 HU |
| Limits | Units: a series that is not in HU is refused (also one with no unit). The closing radii are in **voxels**, not mm, so the mask depends on the voxel size; at 30 voxels it bridges the two lungs and holds hila, vessels, part of the mediastinum and of the chest wall between lung concavities: those are class 5, which is why upstream calls it "other denser tissues", and its volume is not a lung finding. The opening removes thin lung parts (tips, a few voxels thick), the closing does not bring them all back. Lung that is consolidated up to the pleura is not air below −155 HU: it is in the mask only if the closing happens to cover it. Mixture fitted on COVID-19 CTs of one dataset: kernel, slice thickness and contrast shift the classes. "Air" (below −893.5 HU) is airways and over-inflated or emphysematous lung alike |
| Speed | Synthetic 512 × 512 × 300 volume (lungs of 6.0 and 5.2 M voxels), 4 CPU cores: *gmm* 29 s, *gmm_averaged* 34 s, peak memory 3.2 GB (the distance transforms on the lungs' box are float64) |
| Licence | Plugin: own code. Upstream DensityLungSegmentation: **Apache-2.0** (`LICENSE` and README in its repository; no `NOTICE` file). No upstream source is copied; the 15 mixture parameters are taken from its Apache-2.0 model file, credited here and in `lung_density.py`. numpy, scipy: BSD-3-Clause, from pip |
| Verified | **Synthetic volumes only, entries called through the SDK's request handler (`radspider_plugin._handle`) in a plain Python 3.13 venv (numpy 2.5.4, scipy 1.18.1) outside the viewer. Not run in radspider, not on real CT, not compared with 3D Slicer's output.** Phantom: 260 × 200 × 100 voxels of 0.8 × 0.8 × 2 mm, body ellipsoid at 40 HU in −1000 HU air, two ellipsoid lungs at −850 HU (over 500 000 voxels each) with box patches at −980, −600, −300 and 0 HU and one isolated −300 HU voxel. *gmm* with defaults: inside the lungs the voxel count of classes 1, 3, 4, 5 equals the known patch counts (4000, 7500, 2561, 1152) and every patch voxel has its class; class 2 is all other lung voxels except 276 at the ellipsoids' tips that the opening removes (checked to be exactly such voxels); nothing outside the body is labelled; the closed mask adds 66 435 voxels of 40 HU tissue between the lungs, all class 5. *gmm_averaged*: the isolated voxel becomes class 2, patch cores keep their class. *volumes*: table cells, bars and segments equal those label volumes, mean HU of the patches as built. Small phantom (160 × 120 × 80): refused at 500 000 voxels with the hint, segmented at 20 000. Mixture classification compared with scikit-learn's `GaussianMixture.predict` (model rebuilt from the constants, not unpickled) on 216 000 values from −1000 to 3000 HU: identical; the variances agree with the `precisions_cholesky_` stored in the file. Every entry refuses `SUVbw` and no unit. Run as `org.radspider.density-lung-segmentation` 1.1.0; not rerun after the merge into this plugin (module moved unchanged but for the registrations) |

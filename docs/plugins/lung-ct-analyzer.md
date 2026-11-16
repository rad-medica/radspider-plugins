# Lung CT analyzer

Plugin id: `org.radspider.lung-ct-analyzer` · folder: [`../../org.radspider.lung-ct-analyzer`](../../org.radspider.lung-ct-analyzer)

TL;DR: the analysis of the 3D Slicer extension **LungCTAnalyzer** (R. Bumm,
[rbumm/SlicerLungCTAnalyzer](https://github.com/rbumm/SlicerLungCTAnalyzer), read at commit `e2f23da`): inside a
right and a left lung mask every voxel gets one of five classes by its Hounsfield value, and the volumes are
reported per lung. Re-implemented with numpy and scipy; no code of the extension is in the plugin. CT in HU only.
**Not clinically evaluated** (upstream says the same of its own results).

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
| Translations | `lang/es.toml` (52 texts): manifest, progress messages, table headers and row labels (*Total lungs*, *Right lung*, *Left lung*), chart titles, axis labels and series names, the window's controls, the result message. Not marked, on purpose: the names of the segments it creates and the names of the series' own segments (study data), error texts. `lang/template.toml`: `python -m radspider_plugin template org.radspider.lung-ct-analyzer` |

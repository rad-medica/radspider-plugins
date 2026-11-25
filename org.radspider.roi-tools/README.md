# ROI tools

Plugin id: `org.radspider.roi-tools`

TL;DR: nine tools that work on what the user drew (lines, probes, text notes, polygons, ellipses): they measure,
export, edit the measurements, or turn them into segments. Each reproduces the behaviour of one plugin of the
Horos / OsiriX plugin collection; the Python is written from that behaviour, not from its code. `api = 6` (2.0.0), numpy + scipy. 2.0.0 removed `cobb_angle`: the Cobb angle is `spine` of `org.radspider.skeletal-radiology` (two drawn lines override its endplates, but it needs to detect bone first). Plugin icon `ruler`, one Phosphor icon per tool, Spanish catalog `lang/es.toml`.

| Tool (`name`) | Ribbon | Needs | Gives | After |
|---|---|---|---|---|
| Export ROIs (`export_rois`) | yes | any measurement | one table for CSV | ExportROIs |
| Rotate ROI (`rotate_roi`) | no | polygon or line on the slice on screen | the ROI rotated (`replace_rois`) | ROIRotation |
| Points to line (`points_to_line`) | no | probes on ≥ 2 slices | probes on the slices in between | PointsToLine |
| Sphere volumes (`sphere_volumes`) | yes | 2 lines | table | Volume Calculator |
| ROIs to segments (`rois_to_labels`) | yes | polygons / ellipses | segments, table | VoxelVolume |
| Sector statistics (`sector_statistics`) | no | 2 polygons on the slice on screen | table, chart, sector outlines | CardiacStatistics |
| Count points (`count_points`) | no | probes / text notes | table, chart | SpineCounter |
| Grow from probe (`grow_from_seed`) | yes | a probe | one segment, table | NMSegmentation |
| Calcium score (`calcium_score`) | no | CT in HU, ideally segments | table | CalciumScore |

Nine ribbon buttons is too many: the five without one (`button = false`) need parameters or are rare, and run from
*Plugin tools…*. `calcium_score` has none because radspider has a native calcium tool; this is the plugin equivalent.

## Shared rules

| Topic | Rule |
|---|---|
| Geometry | In mm: point (x, y) of a slice is at (x · spacing x, y · spacing y). Lengths, angles, areas and rotations are right on non-square pixels |
| Slice on screen | `ctx.slice`. Tables show slices 1-based (*Image*), as the viewer counts |
| Most recent | The last one on its slice in `ctx.rois` (the host lists a slice's measurements in the order they were made). Across slices there is no time order: the tools that need one say which slice they take |
| Pixels of a shape | A pixel is inside when its centre is (even-odd rule; a pixel centre exactly on an edge belongs to the shape on its right / below). Ellipse: `((x−cx)/a)² + ((y−cy)/b)² ≤ 1` |
| Names | The API gives a text only for `text` notes: polygons, ellipses and probes arrive unnamed |
| Statistics | Over the pixels with data (NaN left out); SD is the population SD |
| Errors | What the user can fix is raised with how: "No polygon or line on the slice on screen: draw one, or scroll to its image, and run again" |

## The tools

### Export ROIs

| | |
|---|---|
| Input | Every measurement of the series |
| Columns | Id, Image, Kind, Text, Points, Length mm (`line`), Area mm² and Perimeter mm (`polygon`: shoelace and edge sum; `ellipse`: π·a·b and Ramanujan's second approximation), Centre x/y/z in patient mm (polygon: area centroid; others: mean of the points), Pixels, Mean, SD, Min, Max, Total (`polygon`, `ellipse`), all points as `x y z` in voxels and in patient mm (`volume.to_patient`) separated by `;` |
| Output | One table: *Save as CSV…* in the tool's window writes it |
| Original | Writes CSV or XML itself, with the points as a variable number of trailing columns, and statistics for every ROI type. Here the file is written by the viewer, points are two text cells (a table has a fixed width), perimeter is added, XML is not offered, and statistics are given for closed shapes only |

### Rotate ROI

| | |
|---|---|
| Input | The most recent `polygon` or `line` on the slice on screen; *All on the slice* = 1 takes every polygon and line of that slice |
| Params | `angle_deg` (default 90, −360…360), `all_on_slice` (bool, default off) |
| Formula | Each ROI turns about its own centre (polygon: area centroid; line: midpoint) in mm, then goes back to voxels: a square stays a square on 0.5 × 1.0 mm pixels. Positive = counter-clockwise as seen on screen |
| Output | `replace_rois`; each is one `Ctrl+Z` step |
| Original | Rotates the selected ROIs about their centroid by a typed angle or a dial. Its rotation itself is in the viewer's ROI class, which is not part of the plugin source: its sign convention and centroid definition could not be checked. Ellipses are not rotated (an ellipse here is an axis-aligned box) |

### Points to line

| | |
|---|---|
| Input | `probe` measurements on at least two different slices |
| Does | Orders them by slice and joins each consecutive pair: every slice strictly between gets a probe at the linearly interpolated (x, y). Linear in voxel indices is a straight line in the patient because the grid is regular. Table: every point with its patient mm; the message gives the 3D path length |
| Repeat | Running it again adds nothing: every slice in between already has its probe |
| Original | Takes only the first two points, walks the 3D line between them in 1 mm steps and adds a point named "generated" at each step (so several per slice when the slices are more than 1 mm apart; the walk stops within 2 mm of the end). Here: one point per slice, any number of placed points |

### Sphere volumes

| | |
|---|---|
| Input | Two `line` measurements: the two most recent on the slice on screen when it has two, otherwise the last two of the series in slice order. The earlier is diameter 1 |
| Formula | `V = π·d³ / 6`. Table: d1, d2 (mm), V1, V2 (ml), change (ml and `100·V2/V1 − 100` %), ratio `V2/V1`, doublings `log2(V2/V1)` |
| Original | Shows exactly d1, d2, V1, V2, the signed % change and the ratio as "×". It takes one line from each of two viewer windows (two studies, ordered by date) and updates live. Here: one series, so both lines are on it; ml instead of mm³; the doublings row is an addition. It is not a doubling *time*: the API gives no dates |

### ROIs to segments

| | |
|---|---|
| Input | Every `polygon` and `ellipse` of the series |
| Naming | One segment per distinct name. Name of a shape = the text of a `text` note placed inside it on the same slice, else its kind (`Polygon`, `Ellipse`) |
| Does | Rasterises each shape on its slice; where shapes with different names overlap the later one wins. Names without a single pixel are dropped. Table: shapes, slices, voxels and ml (`voxels · spacing x · y · slice step / 1000`) per segment and in total |
| Output | `labels`: needs MPR open on the series |
| Original | Labels by ROI name, writes the mask as a new DICOM series and reports one total volume, summing slice by slice with the measured distance to the next slice. Here: segments instead of a series, a volume per name, and the mean slice step (`spacing[2]`), which is the same on an evenly spaced stack |

### Sector statistics

| | |
|---|---|
| Input | Two `polygon` measurements on the slice on screen: the larger area is the epicardial contour, the smaller the endocardial one |
| Params | `sectors` (integer, default 6, 2–36), `layers` (integer, default 1, 1–4), `reference_deg` (default 0), `outlines` (bool, default on) |
| Geometry | Centre = area centroid of the endocardial contour. An angle is measured counter-clockwise on screen, 0° = towards +x (right). Sector *k* covers `reference + (k−1)·360/N … reference + k·360/N`. Wall = pixels inside the epicardial and outside the endocardial polygon. Layer = `floor(L · (r − r_endo) / (r_epi − r_endo))` along the ray from the centre, 1 = innermost; the two radii are found by ray casting at 0.5° steps (outermost crossing) |
| Output | Table per sector and layer (mean, SD, min, max, area mm², pixels) plus the whole wall; a bar chart of the sector means (one series per layer); with `outlines` the N × L sector outlines as polygons (5° arc steps) and a note `S1…SN` outside each sector |
| Order | Same as the original: sectors are numbered counter-clockwise on screen starting at the reference (the original builds them clockwise and names them N…1, which is the same numbering) |
| Running again | Earlier outlines are polygons too. With more than two polygons on the slice, the epicardial contour is the largest and the endocardial one the largest of those surrounding its centroid (an outline lies in the wall and does not). Outlines are added again on every run: undo them or set `outlines` = 0 |
| Original | The reference is a line the user draws from the LV centre to the RV insertion: centre and start angle both come from it. Here the centre is the endocardial centroid and the start a parameter. The original picks contour points within 4° of each ray and takes statistics of the sector polygons it drew; here every wall pixel is assigned by its own angle and depth. Contours that are not star-shaped about the centre are handled approximately in both |

### Count points

| | |
|---|---|
| Input | `probe` and `text` measurements; `line` measurements for the density |
| Does | Type = a note's text; probes count as `Probe`. Table per image and type, per image over all types, and totals: count, length of the lines on that image (sum when several), count per mm and per 10 mm. Totals use the lines of all images. Chart: totals by type |
| Original | Counts dendritic spines: ROIs are named with a number and type letters, hotkeys cycle a spine's type and increment the default name, and it exports per spine its type, the length of the line with the same number and its distance along an open polygon named "Axis". Not possible here: hotkeys, renaming and ROI names for anything but notes (the API has none), so there is no per-spine matching and no distance along an axis. What is reproduced: counts by type and density along a measured length |

### Grow from probe

| | |
|---|---|
| Input | The most recent `probe` on the slice on screen; when it has none, the last probe of the series. Seed = nearest voxel |
| Params | `mode` (choice: *Seed value ± range*, *Absolute bounds*, *% of local maximum*), `lower`, `upper`, `search_mm` |
| Mode *Seed value ± range* (was 0) | Values in `[seed − lower, seed + upper]` (default ± 50) |
| Mode *Absolute bounds* (was 1) | Values in `[lower, upper]` as absolute values |
| Mode *% of local maximum* (was 2) | `lower` is a percentage: values in `[lower % · max, max]`, max = the maximum in a box of `search_mm` (default 70) around the seed. The original's cut-off mode (its default: 45 % within 70 mm), made for PET / SPECT uptake |
| Does | Thresholds the volume and keeps the 6-connected (face neighbours) region holding the seed: `scipy.ndimage.label`. Table: seed, range, voxels, volume ml, mean, SD, min, max |
| Output | One segment (`labels`: needs MPR open on the series) |
| Original | Four ITK algorithms. Reproduced: *Connected Threshold* with manual bounds (mode 1) and with the cut-off (mode 2). Mode 0 is an addition. Not reproduced: *Neighborhood Connected*, *Confidence Connected*, *Gradient Thresholding*, growing on a second registered series, the seed by mouse click (a probe instead), the ROI colour |
| RAM | The label array is 4 bytes per voxel: about 300 MB on 512 × 512 × 300, on top of the volume |

### Calcium score

| | |
|---|---|
| Input | A non-contrast cardiac CT in HU; any other unit is refused. Existing segments restrict the score to their voxels |
| Param | `min_area_mm2` (default 1) |
| Formula | Agatston AS, Janowitz WR, Hildner FJ, et al. *Quantification of coronary artery calcium using ultrafast computed tomography.* J Am Coll Cardiol 1990;15:827–32. Per slice, a lesion is a connected group (8 neighbours) of pixels ≥ 130 HU with area ≥ `min_area_mm2`. Its weight comes from its peak HU: 130–199 → 1, 200–299 → 2, 300–399 → 3, ≥ 400 → 4. **Score = Σ area (mm²) · weight · slice step / 3 mm** (the paper scored 3 mm slices; the factor is the conventional scaling to other spacings). Volume score = scored voxels · voxel volume (mm³) |
| Table | Per segment and *Total*: Agatston score, volume mm³, lesions per slice (what the score sums), lesions in 3D (26-connected groups of the scored voxels), peak HU. *Total* is computed on the union of the segments, so overlapping segments are not counted twice |
| No segments | The whole volume is scored and the message says so: bone, contrast and metal ≥ 130 HU are counted and the number is not a coronary score. Segment the coronaries first |
| Thickness | The API gives the slice step, not the slice thickness: the step is used. For overlapping reconstructions that is the right factor; for gapped ones it overestimates |
| Original | A one-line launcher: the scoring is in the viewer's own source, which was not available, so nothing was compared. There the user outlines each lesion per vessel; here segments play that part |
| RAM | Slices are labelled in bands of 32; the scored-voxel mask is 1 byte per voxel and the 3D count 4 bytes per voxel |

## Limits

| | |
|---|---|
| Selection | The API has no "selected ROI": tools take the most recent, or all |
| Other kinds | `angle`, `bidimensional`, `perpendicular`, … are exported with their points only; no tool edits them |
| Volumes | `spacing[2]` is the mean slice step: exact on an even, untilted stack |
| Not clinical | Nothing here is validated for diagnosis |

## Licence and origin

| | |
|---|---|
| Origin | Behaviour of nine (ten up to 1.1.0, with Cobb Angle) plugins of the Horos / OsiriX plugin collection (`horosplugins`): Cobb Angle, ExportROIs, ROIRotation, PointsToLine, Volume Calculator, VoxelVolume, CardiacStatistics, SpineCounter, NMSegmentation, CalciumScore |
| Their licences | GPL or "all rights reserved", per plugin |
| This plugin | Written from the behaviour (what each computes and shows), in Python, without translating or copying their code; formulas are the public ones stated above. Licence: this repository's `LICENSE` |
| Dependencies | numpy (BSD-3-Clause), scipy (BSD-3-Clause) |

## Verified

| | |
|---|---|
| Verified | **Not run in radspider.** Run outside the viewer on synthetic volumes through the SDK's own request handler (`radspider_plugin._handle`: files on disk, one JSON request per call, the reply checked as JSON), numpy 2.5.4, scipy 1.18.1, Python 3.13: 73 assertions, all passed. *Cobb*: lines at 30° in mm on 0.5 × 1.0 mm pixels → 30.0° / 150.0°; perpendicular → 90°. *Export*: 10 × 10 px square on 0.5 × 2 mm pixels of an x-ramp → 100 mm², 50 mm, 100 px, mean 14.5, SD 2.872, min 10, max 19, patient coordinates with a rotated orientation; ellipse 157.08 mm², 48.442 mm. *Rotate*: 90° and 45° on 0.5 × 1.0 mm pixels keep edge lengths, diagonal and centroid; 360° is the identity. *Points*: probes on slices 2, 6, 8 → 4 interpolated probes, path 56.0 mm, a second run adds nothing. *Sphere*: 10 and 20 mm → 0.5236 and 4.1888 ml, +700 %, ×8. *Segments*: two squares and an ellipse → 3 named segments, 100 voxels = 0.3 ml each square. *Sectors*: ring of radii 10 and 20 mm on 0.5 × 1.0 mm pixels painted 100·sector + 10·layer → means within 1.5 (boundary pixels), areas within 5 % of the analytic ones, wall area within 1 %, numbering direction, outline area = table area within 3 %, same table with earlier outlines present. *Count*: counts and densities over a 10 mm line. *Grow*: a radius-5 ball (515 voxels, 1.030 ml on 1 × 1 × 2 mm) recovered exactly in the three modes; a second ball and an edge-touching voxel left out. *Calcium*: phantom of three lesions → 15.0 at 3 mm, 7.5 at 1.5 mm, 16.0 with the 0.25 mm² pixel allowed, per-slice scoring of a two-slice lesion, per-segment rows and the union total. Every tool's "nothing to work on" error was raised. Timing on 512 × 512 × 120 noise: calcium 4.8 s, grow 0.6 s. **Not checked:** the viewer drawing the `cobb` measurement, `replace_rois` and `labels` being applied, whether probes and polygons keep a `text`, real patient data, RAM on a full CT, and the originals' numbers (they need macOS; CalciumScore's and ROIRotation's maths are not in the plugin sources) |
| Verified (1.1.0) | **1.1.0 (API 6), not run on real data and not run in the viewer.** Python 3.13 with numpy and scipy from another plugin's venv, the SDK from radspider `assets/python`: every entry ran on synthetic images or volumes and its reply was built with the SDK's own reply code (marked texts, controls, charts, pictures, ROIs, edits) without an exception; `lang/template.toml` regenerates byte-identical; `lang/es.toml` has exactly the template's keys; `python -I tools/validate_plugins.py`; `ruff check`; radspider `radspider-check --plugin-template` parsed the manifest. Measured numbers were not compared with 1.0.0 on real data; `tests/plugins.rs` does not load this plugin. |
| Verified (2.0.0) | `cobb_angle` removed (code, manifest, catalog). The other nine tools are unchanged and were not rerun |

## API 6 (1.1.0)

| | |
|---|---|
| `api` | 6 (was 2): icons, translations, typed parameters |
| Icons | Plugin `ruler`; `export_rois` `file-csv`, `rotate_roi` `arrow-clockwise`, `points_to_line` `line-segments`, `sphere_volumes` `sphere`, `rois_to_labels` `polygon`, `sector_statistics` `chart-pie-slice`, `count_points` `hash`, `grow_from_seed` `plant`, `calcium_score` `heartbeat` |
| Spanish | `lang/es.toml`: every manifest text and every marked text (table headers and label cells, messages, progress, chart titles, axis labels, series names). `lang/template.toml`: `python -m radspider_plugin template org.radspider.roi-tools` (SDK on `PYTHONPATH`) |
| Retyped parameters | `all_on_slice` and `outlines`: `bool` (were 0 / 1 numbers); `sectors`, `layers`: `integer`; `mode`: `choice` (was 0 / 1 / 2) |
| Not translated | ROI text, segment names (study data) and the text of a raised error (an exception carries a plain string) |

# Skeletal radiology

Plugin id: `org.radspider.skeletal-radiology` · folder: [`../../org.radspider.skeletal-radiology`](../../org.radspider.skeletal-radiology)

TL;DR: automatic and hybrid interactive measurements on 2D skeletal radiographs (or the active slice of a stack) with
`numpy` and `scipy`: spine (Cobb angle, coronal/sagittal balance, vertebral wedging), full-leg alignment (HKA, MAD,
mLDFA, MPTA, JLCA, limb lengths and discrepancy), AP hip/pelvis (Wiberg LCEA, Tönnis acetabular index, neck-shaft CCD
angle, pelvic obliquity), diaphyseal cortical morphometry (Barnett-Nordin index, corticomedullary ratio) and extremity
goniometry (Foot AP, Foot Lateral, Hand/Wrist AP), plus a 3D/2D bone silhouette segmentation. `api = 2`. **Research use
only: not clinically evaluated.**

| Entry | Kind | Does |
|---|---|---|
| *Skeletal bone mask* `bone_silhouette` | segmentation | Global + row-band adaptive percentile threshold, Euclidean disc hole closing and minimum area filter |
| *Spine morphometry* `spine` | tool | Spinal midline curve, endplate tilt profile, automatic Cobb angle, plumb balance (mm) and apical wedge ratio; 2 drawn lines override the endplates |
| *Lower limb alignment* `lower_limb` | tool | Full-leg tele-radiography (Right/Left): hip, knee and ankle centers, HKA angle, MAD (mm), mLDFA, MPTA, JLCA, femoral/tibial/total lengths and LLD; 3 probes or 2 knee lines override landmarks |
| *Hip and pelvis* `hip_pelvis` | tool | Bilateral femoral head centers and diameters, pelvic teardrop reference line (obliquity ° and mm), Wiberg LCEA, Tönnis angle, neck-shaft CCD angle and femoral offset; drawn ellipses/probes override femoral heads |
| *Bone morphometry* `bone_morphometry` | tool | Principal shaft axis, bone length, outer periosteal diameter $D$, inner medullary diameter $d$, combined cortical thickness $CCT = D - d$, Barnett-Nordin cortical index (%), corticomedullary ratio and cortical area |
| *Foot and hand* `foot_hand` | tool | View-selectable goniometry: Foot AP (HVA, 1–2 IMA), Foot Lateral (Böhler, Gissane, calcaneal pitch) and Hand/Wrist AP (2nd metacarpal index MCI, radial inclination) |

## Shared rules

| Topic | Rule |
|---|---|
| Geometry | In physical mm: pixel `(x, y)` lies at `(x · spacing[0], y · spacing[1])` mm. Angles, lengths, offsets and areas are exact on non-square pixels |
| Bone silhouette | `0.65 · global_percentile + 0.35 · smoothed_row_percentile` so craniocaudal soft-tissue thickness gradients (thorax vs abdomen, thigh vs ankle) do not wash out thinner bone segments; closed with an Euclidean distance transform disc |
| Hybrid mode | Each tool runs automatically with zero prior measurements, shows an annotated RGB preview image, charts and interactive sliders (`ctx.controls`), and accepts user-drawn ROIs (`line`, `probe`, `ellipse`, `polygon`) or existing segments (`ctx.segments`) to override landmarks |
| Stamping ROIs | Viewer ROIs (`cobb`, `line`, `probe`, `ellipse`, `text`) are returned on the initial run (`ctx.event is None`) and when clicking *Stamp ROIs on image* (`ctx.event == "stamp"`), so moving a slider updates the preview without duplicating ROIs on the slice |

## The entries

### Spine morphometry (`spine`)

| | |
|---|---|
| Input | Active slice (or slider-selected slice). Uses an existing spine/vertebra segment when present, otherwise segments the central vertebral corridor |
| Method | Row-by-row intensity-weighted vertebral centroid $c_x(y)$ and width $w(y)$, smoothed with a Gaussian kernel (`smooth_mm`). Endplate tilt $\theta(y) = \arctan2(dx_{\text{mm}}, dy_{\text{mm}})$. Selects the superior and inferior levels maximising $|\theta(y_1) - \theta(y_2)|$ (or set by the *Superior / Inferior endplate level* sliders) |
| Override | When 2 or more `line` measurements are present on the slice and *Override endplates with 2 drawn lines* is ticked, the last two lines are used as the superior and inferior endplates |
| Output | Table (Cobb angle, supplement, severity class, superior/inferior tilts, cranial-caudal plumb balance in mm, apical deviation in mm, apical wedge angle and height ratio), 2 charts (midline deviation and tilt profile), annotated RGB image, and `cobb` + plumb `line` + apex `probe` + `text` ROIs |

### Lower limb alignment (`lower_limb`)

| | |
|---|---|
| Input | Standing AP full-leg radiograph (bilateral or unilateral). Splits into Right and Left limbs when two long-bone silhouettes are present, or filters by the *Analyzed limb* choice |
| Landmarks | Proximal femoral head centroid (`hip_y_frac`), intercondylar knee centroid auto-refined at the condylar width flare maximum (`knee_y_frac`) with distal femoral and proximal tibial tangent lines fit to the condylar/plateau silhouettes, and distal tibial plafond centroid (`ankle_y_frac`) |
| Override | 3 `probe` ROIs on a limb override `(hip, knee, ankle)` in craniocaudal order; 2 `line` ROIs on a limb override the distal femoral and proximal tibial joint lines |
| Formulas | **HKA** = $180^\circ - \text{varus}^\circ$ between femoral ($\text{hip} \to \text{knee}$) and tibial ($\text{knee} \to \text{ankle}$) mechanical vectors. **MAD** = perpendicular distance (mm) from knee center to the hip–ankle line. **mLDFA** = lateral angle between femoral mechanical axis and distal femoral joint line. **MPTA** = medial angle between tibial mechanical axis and tibial plateau line. **JLCA** = acute angle between the two joint lines. **LLD** = $|L_{\text{Right}} - L_{\text{Left}}|$ |

### Hip and pelvis (`hip_pelvis`)

| | |
|---|---|
| Input | AP pelvis or single-hip radiograph |
| Landmarks | Bilateral femoral head domes located by Euclidean distance transform × intensity peak in the acetabular corridor; inferior teardrops define the pelvic horizontal reference line; superior-medial and superior-lateral sourcil points define the acetabular roof; subtrochanteric PCA axis and neck isthmus define the CCD axes |
| Override | An `ellipse` ROI on a hip overrides its femoral head center and diameter; a `probe` ROI overrides the head center |
| Formulas | **Pelvic obliquity** (° and mm step between teardrops). **Wiberg LCEA** = angle between the upward perpendicular to the pelvic reference line through the head center and the ray to the lateral sourcil rim. **Tönnis angle** = inclination of the sourcil roof relative to the pelvic reference line. **CCD angle** = obtuse neck-shaft angle ($90\text{–}180^\circ$). **Femoral offset** = perpendicular distance (mm) from head center to the shaft axis |

### Bone morphometry (`bone_morphometry`)

| | |
|---|---|
| Input | Any tubular bone radiograph. Restricts to the most recent closed ROI (`polygon`/`ellipse`) on the slice when drawn, else the first segment, else the largest bone silhouette |
| Method | Principal longitudinal axis $(\mathbf{u}, \mathbf{n})$ and bone length $L$ by PCA in mm. At `level_frac` along the shaft (default 0.50 = mid-shaft), averages 5 transverse profiles across $\pm 3\text{ mm}$ to locate the outer periosteal margins ($D$), left/right cortical peaks, and inner endosteal medullary margins ($d$) at half-prominence |
| Formulas | $CCT = D - d$; **Barnett-Nordin Cortical Index** $= 100 \cdot (D - d) / D$; **Corticomedullary Ratio** $= (D - d) / d$; **Cortical Area** $= \frac{\pi}{4}(D^2 - d^2)$; **Exton-Smith Index** $= (D^2 - d^2) / (D \cdot L)$ |

### Foot and hand (`foot_hand`)

| | |
|---|---|
| Modes | `auto` (inferred from aspect ratio and ray count), `foot_ap`, `foot_lateral`, `hand_ap` |
| Foot AP | 1st and 2nd metatarsal axes and 1st proximal phalanx axis → **Hallux Valgus Angle (HVA, °)** and **1st–2nd Intermetatarsal Angle (IMA, °)** |
| Foot Lateral | Superior calcaneal contour landmarks (posterior tuberosity, posterior facet apex, sinus tarsi nadir, anterior process) and inferior calcaneal line → **Böhler calcaneal angle (°)**, **Gissane crucial angle (°)** and **Calcaneal pitch (°)** |
| Hand / Wrist AP | 2nd metacarpal shaft radiogrammetry (**length**, $D$, $d$, **Metacarpal Cortical Index MCI %**) and distal **Radial inclination (°)** |

## Limits

| | |
|---|---|
| Heuristic detection | Threshold and contour heuristics assume standard radiographic positioning and contrast; severe metal hardware, casts, overlapping limbs or cropped joints move the automatic contours — use the interactive sliders or draw reference probes/lines to lock landmarks |
| Calibration | Millimetre values (`MAD`, lengths, diameters, plumb offset) require calibrated DICOM pixel spacing (`ImagerPixelSpacing` / `PixelSpacing`); magnification is not corrected unless the series spacing already accounts for it |
| Not clinical | None of the measurements are validated for clinical diagnosis or surgical planning |

## Licence

| | |
|---|---|
| Plugin | Own code, licensed under this repository's `LICENSE` |
| Dependencies | `numpy` (BSD-3-Clause), `scipy` (BSD-3-Clause) |

## Verified

| | |
|---|---|
| Verified | **Not run in radspider or on radiographic data** (`radspider_plugin`, `numpy` and `scipy` are provided by the plugin's runtime venv in radspider, not installed in this checkout). Validated statically with `tools/validate_plugins.py`, `tools/marketplace.py check` and `python -m unittest discover -s tools` |

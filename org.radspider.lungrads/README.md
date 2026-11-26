# Lung-RADS report

Plugin id: `org.radspider.lungrads`

TL;DR: a structured lung cancer screening CT report built on a frontal lung schematic: drag on a lobe to draw a
nodule or atypical cyst, then describe the selected mark below (type, behaviour since the prior exam, mean diameters
to one decimal). Each gets its Lung-RADS v2022 category computed from them (assigned by the reader where the rules
give none), with the 4X and S modifiers, category 0, and the exam category with its management. `api = 8` (the
sketch control: radspider with plugin API 8), standard library only. One tool, `report`, icon `clipboard-text`.

| Finding | Category |
|---|---|
| Solid | Baseline < 6 mm 2, 6-< 8 3, 8-< 15 4A, ≥ 15 4B; new < 4 2, 4-< 6 3, 6-< 8 4A, ≥ 8 4B; growing < 8 4A, ≥ 8 4B; slow-growing 4B |
| Part-solid | Baseline total < 6 2, solid < 6 3, 6-< 8 4A, ≥ 8 4B; new total < 6 3; new or growing solid < 4 4A, ≥ 4 4B; slow-growing 4B |
| Non-solid | < 30 mm (baseline, new or growing) 2; ≥ 30 baseline or new 3; slow-growing 2; growing ≥ 30 **no row: the reader assigns** |
| Juxtapleural | Baseline or new < 10 mm 2, else as solid |
| Airway | Subsegmental (baseline, new, stable) 2; segmental or more proximal baseline or new 4A, stable or growing 4B |
| Atypical cyst | Growing cystic component of a thick-walled cyst 3; thick-walled or multilocular 4A; growing wall, nodularity or loculation, new or increased opacity 4B |
| Stepped | Stable at annual screening (was 2) 2; stable or smaller at the 6-month exam of a 3: 2; at the 3-month exam of a 4A: 3 (airway 4B) |
| Modifiers | 4X turns 3, 4A or 4B into 4X; S adds its own row; category 0 (prior CT being located, lungs not evaluable, inflammation or infection) overrides the exam category |
| Exam | The most suspicious finding; without findings 1. *Category* per nodule overrides the computed one |
| Lobe | From where the mark sits on the schematic: right upper, middle, lower; left upper, lingula, lower. The fissures are approximate (right horizontal and oblique, left oblique, lingula below the left upper lobe's midline); a mark outside both lungs is shown as `?` and not reported |
| Marks | Circle `N1 4A` (the category in letters, `?` = not assigned): 1-2 ok, 3 accent, 4A and not assigned warning, 4B and 4X error tone |

| Source | Status |
|---|---|
| ACR Lung-RADS v2022 | The ACR document was not reachable. Airway, cyst, slow-growth, growth (> 1.5 mm in 12 months) and category-0 rows from the review by Kim et al., J Korean Soc Radiol 2023 (PMC9935959); **the solid, part-solid and non-solid size rows, the stepped rows and the management wording are from the author's knowledge of v2022**, not re-read against the document |

## Limits

- **Not a medical device.** A reporting aid: the reader checks and owns every line. The rules were written from the
  published system and the sources below by the plugin author and have **not** been reviewed by a radiologist.
- Reads no pixels and measures nothing: sizes are typed in. It needs an acquired image on screen only because a tool
  must run on something (`input = "image"`; not on an MPR, slab or MIP plane).
- At most 16 marks. Mark size on the schematic is not a measurement: diameters are typed in. The lobe follows the
  mark on the schematic, not the CT: check it.
- Needs radspider with plugin API 8; an older viewer refuses the plugin (`api 8 is not supported`).
- Each change starts Python again (about 0.1-0.3 s).
- Report: a two-column table (item, finding) in the language on screen; *Copy table* puts it on the clipboard as
  tab-separated lines. English and Spanish (`lang/es.toml`).

## Verified

| | |
|---|---|
| Verified (2.0.0) | **Not run in the radspider GUI.** Run outside the viewer with Python 3.13, a scratch test with the stand-in SDK of `tools/test_reports.py`: the lobe hit-test on a table of points (each lobe, between the lungs, a corner), the edit flow (an edit of nodule 1 survives selecting nodule 2 before the run; labels `N1 4A`, `N2 ?`, `?` and tones; the exam stays not assigned while a nodule has no diameter, then 4A); the window built with the real SDK of radspider main (API 8) and serialised as JSON; `ruff check`. **Not checked:** the look of the sketch, dragging in the GUI, plus everything listed as not checked for 1.0.0 Then `tools/test_reports.py` (26 tests: its hit-test and edit-flow tests included) and radspider's plugin host (main at 222ac45, a throwaway test in `tests/plugins.rs`, removed after): first open, then 7 marks (each lobe and the lingula, outside) each selected in turn: the host accepted the 15 shapes and the marks (`N1 ?`-`N6 ?` warn, `?` muted). The GUI was not run. |
| Verified (1.0.0) | **Not run in radspider.** Run outside the viewer with Python 3.13: (1) `python -m unittest tools.test_reports` (16 tests): the scoring rules against the tables in this README (written from the sources below, so they prove the code matches this page, not the ACR documents) with a stand-in SDK; a first open shows no finding and a finding without a category leaves the summary unassigned; every form at its largest built with the real SDK of the radspider checkout (`assets/python/radspider_plugin.py`, `Window._wire`) and checked against the host's window limits (≤ 8 windows, ≤ 32 controls per window, ≤ 64 per instance, unique names); `lang/es.toml` ids and placeholders equal to `lang/template.toml` (made by `python -m radspider_plugin template`); (2) `tools/validate_plugins.py`, `ruff check`. **Not checked:** the radspider host accepting the reply, the look of the windows, *Copy table* pasted into a RIS, the Spanish wording by a native radiologist, the solid and part-solid size rows, the stepped rows and the management wording against the ACR document |

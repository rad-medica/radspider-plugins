# PI-RADS report

Plugin id: `org.radspider.pirads`

TL;DR: a structured prostate MRI report built in a window: prostate dimensions to volume (ellipsoid) and PSA
density; lesions drawn on an axial sector map (base, midgland, apex), their side, level and sector taken from where
they sit, then size and T2W / DWI / DCE scores for the selected one; the PI-RADS v2.1 category of each computed from
those scores, extraprostatic extension, seminal vesicles, pelvic nodes and bone, and the overall category. `api = 8`
(the sketch control: radspider with plugin API 8), standard library only. One tool, `report`, icon `clipboard-text`.

| Rule | Applied |
|---|---|
| Peripheral zone | DWI decides; DWI 3 with positive DCE is 4; DCE negative or not performed (biparametric) keeps 3 |
| Transition zone | T2W decides; T2W 2 with DWI 4-5 is 3; T2W 3 with DWI 5 is 4; DCE plays no part |
| Central zone, anterior stroma, inadequate DWI | No category computed: the window asks the reader to assign it (anterior stroma lesions are scored with the zone they arise from) |
| Location | From the mark on the map: level (base, midgland, apex section), side (right, left, midline within 4 units), sector: anterior band AS; inside the dashed transition zone TZa / TZp (above / below its centre); on the base, the central zone ellipse CZ; else PZa (anterior), PZpm (near the midline), PZpl. A mark outside the three sections shows `?` and is not reported |
| Marks | `L1 P4` (lesion number, category; `P?` not assigned). Tone: 5 error, 4 warning, 3 accent, 1-2 ok |
| Volume | AP × transverse × craniocaudal × 0.52; PSA density = PSA / volume |
| Overall | The highest lesion category; without lesions "no lesion with an assigned category" |

| Source | Status |
|---|---|
| Turkbey et al., PI-RADS v2.1, Eur Urol 2019 | Not in PMC; rules taken from the review *PI-RADS v2.1: what has changed and how to report*, SA J Radiol 2021 (PMC8252188), whose table 6 misprints T2W 3 / DWI ≤ 4 as 4 (its text says 3; the plugin uses 3) |
| Inadequate DWI | The reviews read give no rule for it, so the plugin computes none |

## Limits

- **Not a medical device.** A reporting aid: the reader checks and owns every line. The rules were written from the
  published system and the sources below by the plugin author and have **not** been reviewed by a radiologist.
- Reads no pixels and measures nothing: sizes are typed in. It needs an acquired image on screen only because a tool
  must run on something (`input = "image"`; not on an MPR, slab or MIP plane).
- At most 12 lesions. Mark size on the map is not a measurement: the diameter is typed in. The map is a schematic of
  three axial sections, not the patient's anatomy; "bilateral" cannot be drawn (draw one lesion per side).
- Needs radspider with plugin API 8; an older viewer refuses the plugin (`api 8 is not supported`).
- Each change starts Python again (about 0.1-0.3 s).
- Report: a two-column table (item, finding) in the language on screen; *Copy table* puts it on the clipboard as
  tab-separated lines. English and Spanish (`lang/es.toml`).

## Verified

| | |
|---|---|
| Verified (2.0.0) | **Not run in the radspider GUI.** Run outside the viewer with Python 3.13, in a scratch script using the stand-in SDK of `tools/test_reports.py`: the existing rule tests; `locate` on nine points (AS, TZa, TZp, CZ, PZpm, PZpl, PZa, apex midline, outside); the edit flow (an edit of lesion 1 survives selecting lesion 2 before the run; PZ DWI 3 + DCE positive gives `L1 P4` warn; a central zone lesion is `P?` and leaves the overall not assigned until a manual category; a mark outside is `?` muted); the window built with the real SDK of radspider main (API 8), 16 controls, serialisable as JSON; `lang/es.toml` against the regenerated template; `ruff check`. **Not checked:** the look of the map, dragging in the GUI, plus everything listed as not checked for 1.0.0 Then `tools/test_reports.py` (26 tests: its hit-test and edit-flow tests included) and radspider's plugin host (main at 222ac45, a throwaway test in `tests/plugins.rs`, removed after): first open, then 5 marks (PZpl, CZ, TZp, AS, outside) each selected in turn: the host accepted the 32 shapes and the marks (`L1 P1` ok, `L2 P?` accent, `?` muted). The GUI was not run. |
| Verified (1.0.0) | **Not run in radspider.** Run outside the viewer with Python 3.13: (1) `python -m unittest tools.test_reports` (16 tests): the scoring rules against the tables in this README (written from the sources below, so they prove the code matches this page, not the ACR documents) with a stand-in SDK; a first open shows no finding and a finding without a category leaves the summary unassigned; every form at its largest built with the real SDK of the radspider checkout (`assets/python/radspider_plugin.py`, `Window._wire`) and checked against the host's window limits (≤ 8 windows, ≤ 32 controls per window, ≤ 64 per instance, unique names); `lang/es.toml` ids and placeholders equal to `lang/template.toml` (made by `python -m radspider_plugin template`); (2) `tools/validate_plugins.py`, `ruff check`. **Not checked:** the radspider host accepting the reply, the look of the windows, *Copy table* pasted into a RIS, the Spanish wording by a native radiologist |

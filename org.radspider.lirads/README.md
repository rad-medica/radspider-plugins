# LI-RADS report

Plugin id: `org.radspider.lirads`

TL;DR: a structured liver CT/MRI report for patients at high risk for HCC built on a Couinaud schematic: drag on
the liver to draw an observation (its segment comes from where it sits), then describe the selected one: size and
either a category the reader takes before the diagnostic table (LR-NC, LR-TIV, LR-1, LR-2, LR-M) or the LI-RADS
v2018 diagnostic table (nonrim APHE, size, nonperipheral washout, enhancing capsule, threshold growth) adjusted by
ancillary features, with the management of each category. `api = 8` (the sketch control: radspider with plugin
API 8), standard library only. One tool, `report`, icon `clipboard-text`.

| Rule | Applied |
|---|---|
| Population | *Patient at high risk for HCC* off: no categories, the report says LI-RADS does not apply (the marks stay) |
| Segment | From where the mark sits: right hepatic vein plane at x 110, middle at x 200, falciform at x 290; portal plane splits VII/VI, VIII/V, IVa/IVb and II/III; the dashed circle is I. A mark outside the liver is `?` and not reported |
| Marks | Circle `O1 LR5` (category in letters; LR-5, LR-M, LR-TIV error tone, LR-4 warning, LR-1/2 ok). `O1` alone: no category yet |
| Diagnostic table | No APHE: < 20 mm LR-3, LR-4 with 2+ features; ≥ 20 mm LR-3, LR-4 with 1+. Nonrim APHE: < 10 mm LR-3, LR-4 with 1+; 10-19 mm LR-3, capsule alone LR-4, washout or threshold growth or 2+ features LR-5; ≥ 20 mm LR-4, LR-5 with 1+ |
| Ancillary features | Favouring malignancy: up one, never to LR-5. Favouring benignity: down one. Both: no change |
| Not covered | Tie-breaking (the reader picks), LR-TR treatment response (v2024 has its own algorithm), CEUS and US LI-RADS |
| Most worrying | LR-1 < LR-2 < LR-NC < LR-3 < LR-4 < LR-5 < LR-M < LR-TIV, for the summary row |

| Source | Status |
|---|---|
| ACR LI-RADS CT/MRI v2018 core | The ACR document was not reachable. Algorithm order, ancillary-feature rules and LR-NC management from the review in J Hepatocell Carcinoma 2019 (PMC6368120); **the table cells and the other management lines are from the author's knowledge of v2018**, not re-read against the document |
| Newer versions | Only the treatment response algorithm was updated (v2024); no newer diagnostic core was found in PubMed (November 2026) |

## Limits

- **Not a medical device.** A reporting aid: the reader checks and owns every line. The rules were written from the
  published system and the sources below by the plugin author and have **not** been reviewed by a radiologist.
- Reads no pixels and measures nothing: sizes are typed in. It needs an acquired image on screen only because a tool
  must run on something (`input = "image"`; not on an MPR, slab or MIP plane).
- At most 9 observations (mark labels fit the host's 8 characters). Mark size on the schematic is not a
  measurement: the diameter is typed in. The schematic is a diagram, not the patient's anatomy.
- Needs radspider with plugin API 8; an older viewer refuses the plugin (`api 8 is not supported`).
- Each change starts Python again (about 0.1-0.3 s).
- Report: a two-column table (item, finding) in the language on screen; *Copy table* puts it on the clipboard as
  tab-separated lines. English and Spanish (`lang/es.toml`).

## Verified

| | |
|---|---|
| Verified (2.0.0) | **Not run in the radspider GUI.** Run outside the viewer with Python 3.13 (a scratch script, since moved into `tools/test_reports.py`): the hit-test of the schematic on every segment and two points outside; the edit flow with a stand-in SDK (an edit of observation 1 survives selecting observation 2 before the run; labels, tones, unassigned and most-worrying summary follow the marks); the window built with the real SDK of radspider main (API 8): 12 controls, unique names, serialisable as JSON; `ruff check`. **Not checked:** the look of the sketch, dragging in the GUI, plus everything listed as not checked for 1.0.0 Then `tools/test_reports.py` (26 tests: its hit-test and edit-flow tests included) and radspider's plugin host (main at 222ac45, a throwaway test in `tests/plugins.rs`, removed after): first open, then 5 marks (V, I, II, VII, outside) each selected in turn: the host accepted the 17 shapes and the marks (`O1`-`O4` accent, `?` muted). The GUI was not run. |
| Verified (1.0.0) | **Not run in radspider.** Run outside the viewer with Python 3.13: (1) `python -m unittest tools.test_reports` (16 tests): the scoring rules against the tables in this README (written from the sources below, so they prove the code matches this page, not the ACR documents) with a stand-in SDK; a first open shows no finding and a finding without a category leaves the summary unassigned; every form at its largest built with the real SDK of the radspider checkout (`assets/python/radspider_plugin.py`, `Window._wire`) and checked against the host's window limits (≤ 8 windows, ≤ 32 controls per window, ≤ 64 per instance, unique names); `lang/es.toml` ids and placeholders equal to `lang/template.toml` (made by `python -m radspider_plugin template`); (2) `tools/validate_plugins.py`, `ruff check`. **Not checked:** the radspider host accepting the reply, the look of the windows, *Copy table* pasted into a RIS, the Spanish wording by a native radiologist, the v2018 table cells and management against the ACR document |

# BI-RADS report

Plugin id: `org.radspider.birads`

TL;DR: a structured breast imaging report built on a schematic of both breasts: drag on a breast to draw a
finding, then describe the selected mark below with the BI-RADS lexicon and the reader's category. Exam (mammography,
ultrasound, both, MRI), indication, breast composition (or ultrasound tissue composition, or MRI fibroglandular
tissue and background enhancement) above; the overall assessment with its management and likelihood of malignancy
below. `api = 8` (the sketch control: radspider with plugin API 8), standard library only. One tool, `report`, icon
`clipboard-text`.

| Part | |
|---|---|
| Location | From where the mark sits: right or left breast (drawn facing the reader, the right one on the left) and the clock position as the reader faces the patient (12 up, 3 to the reader's right on both breasts), rounded to the hour; within 10 of the 100-unit radius of the nipple: retroareolar. A mark off both breasts is shown as `?` and not reported |
| Finding | Type (mass, calcifications, asymmetries, distortion, focus, non-mass enhancement, cysts, nodes, skin, duct), depth, distance from the nipple, largest diameter (typed in), notes (≤ 200 characters) |
| Marks | `F1 4B` (finding number and category; just `F1` while not assigned). Tone: 1, 2 ok; 0, 3 warning; 4, 4A-4C, 5, 6 error; not assigned accent |
| Descriptors | By type and exam: mass shape and margin (margin list per modality), mammographic density, ultrasound orientation, echo pattern and posterior features, MRI internal enhancement; calcification morphology and distribution; non-mass distribution and internal enhancement; MRI kinetics (initial, delayed) for mass, focus and non-mass |
| Category | The reader's choice per finding: 0, 1, 2, 3, 4A, 4B, 4C, 5, 6 (mammography, ultrasound), 4 undivided on MRI. BI-RADS has no scoring algorithm and the plugin suggests none |
| Overall | Default: the most worrying finding by the ACR hierarchy 1 < 2 < 3 < 6 < 0 < 4 < 5 (4A < 4B < 4C); without findings 1. *Overall assessment* overrides it |
| Wording | Category names, management and likelihood of malignancy of the ACR BI-RADS Atlas, 5th edition (2013) |

| Source | Status |
|---|---|
| ACR BI-RADS Atlas, 5th edition (2013) | Lexicon, categories, hierarchy, management: from the author's knowledge of the Atlas, not re-read against it |
| ACR BI-RADS v2025 Manual (released 1 December 2025) | **Not applied.** Public summaries mention new descriptors, contrast-enhanced mammography, method of detection and a wider category 6 (after neoadjuvant therapy); the manual itself was not available. The report says 5th edition |

## Limits

- **Not a medical device.** A reporting aid: the reader checks and owns every line. The rules were written from the
  published system and the sources below by the plugin author and have **not** been reviewed by a radiologist.
- Reads no pixels and measures nothing: sizes are typed in. It needs an acquired image on screen only because a tool
  must run on something (`input = "image"`; not on an MPR, slab or MIP plane).
- At most 16 findings (marks). Mark size on the schematic is not a measurement. No axillary tail or "central"
  region: they are not on the schematic (type them in the notes).
- Needs radspider with plugin API 8; an older viewer refuses the plugin (`api 8 is not supported`).
- Each change starts Python again (about 0.1-0.3 s).
- Report: a two-column table (item, finding) in the language on screen; *Copy table* puts it on the clipboard as
  tab-separated lines. English and Spanish (`lang/es.toml`).

## Verified

| | |
|---|---|
| Verified (2.0.0) | **Not run in the radspider GUI.** Run outside the viewer with Python 3.13: a scratch check (since moved into `tools/test_reports.py`) of `locate()` on a table of points (retroareolar, 12, 3, 9, 6 and 1 o'clock, between the breasts) and of the edit flow with a stand-in SDK (an edit of finding 1 survives selecting finding 2 before the run; labels `F1 4B`, `F2`, `?`, tones; the summary stays unassigned while a finding has no category, then follows the hierarchy); the window built with the real SDK of radspider main (API 8) for mammography and ultrasound (21 controls) and MRI (20), unique names, serialisable as JSON; `lang/es.toml` keys equal to the regenerated `lang/template.toml`; `ruff check`. **Not checked:** the look of the sketch, dragging in the GUI, plus everything listed as not checked for 1.0.0 Then `tools/test_reports.py` (26 tests: its hit-test and edit-flow tests included) and radspider's plugin host (main at 222ac45, a throwaway test in `tests/plugins.rs`, removed after): first open, then 4 marks (retroareolar, right 12:00, left 1:00, outside) each selected in turn: the host accepted the 20 shapes and the marks (`F1`-`F3` accent, `?` muted). The GUI was not run. |
| Verified (1.0.0) | **Not run in radspider.** Run outside the viewer with Python 3.13: (1) `python -m unittest tools.test_reports` (16 tests): the scoring rules against the tables in this README (written from the sources below, so they prove the code matches this page, not the ACR documents) with a stand-in SDK; a first open shows no finding and a finding without a category leaves the summary unassigned; every form at its largest built with the real SDK of the radspider checkout (`assets/python/radspider_plugin.py`, `Window._wire`) and checked against the host's window limits (≤ 8 windows, ≤ 32 controls per window, ≤ 64 per instance, unique names); `lang/es.toml` ids and placeholders equal to `lang/template.toml` (made by `python -m radspider_plugin template`); (2) `tools/validate_plugins.py`, `ruff check`. **Not checked:** the radspider host accepting the reply, the look of the windows, *Copy table* pasted into a RIS, the Spanish wording by a native radiologist |

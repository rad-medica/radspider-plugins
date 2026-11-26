# TI-RADS report

Plugin id: `org.radspider.tirads`

TL;DR: a structured thyroid ultrasound report built on a neck schematic: drag on a lobe to draw a nodule, inside a
lymph node level to draw a node, then describe the selected mark below. Nodules are scored with ACR TI-RADS (points,
TR level, FNA or follow-up by size), nodes classed with ETA 2013 (normal, indeterminate, suspicious) and,
optionally, the clinical TNM and stage of a differentiated thyroid carcinoma follow (AJCC 8th edition). `api = 8`
(the sketch control: radspider with plugin API 8), standard library only. One tool, `report`, icon `clipboard-text`.

| Part | Applied |
|---|---|
| Points | Composition (solid 2, mixed 1, cystic or spongiform 0 and no further points, cannot be determined 2), echogenicity (anechoic 0, hyper/isoechoic 1, hypoechoic 2, very hypoechoic 3, cannot be determined 1), shape (taller-than-wide 3), margin (smooth or ill-defined 0, lobulated or irregular 2, extra-thyroidal extension 3, cannot be determined 0), echogenic foci added up (macro 1, rim 2, punctate 3) |
| Level | 0 TR1, 1-2 TR2, 3 TR3, 4-6 TR4, 7+ TR5. The chart has no 1-point row; one review puts it in TR1, the plugin in TR2: the recommendation is the same (no FNA) |
| Recommendation | By the largest of the three diameters: TR3 FNA ≥ 25 mm, follow-up ≥ 15 (1, 3, 5 years); TR4 FNA ≥ 15, follow-up ≥ 10 (1, 2, 3, 5 years); TR5 FNA ≥ 10, follow-up ≥ 5 (yearly up to 5 years) |
| Location | From where the mark sits on the schematic: right or left lobe and its third (two dashed guides), isthmus, or one of levels I-V right and left, VI, VII. A mark elsewhere is shown as `?` and not reported |
| Lymph nodes | Per node: short axis, fatty hilum (present by default), the four ETA 2013 suspicious features, two other findings (round shape, increased central vascularity: reported, not scored). Suspicious = any feature; else indeterminate = no hilum; else normal. A level takes the tint of its worst node |
| Marks | Nodule: circle `N1 TR4` (TR5 error, TR4 warning tone). Node: square `L1`, `L1 I`, `L1 S` (status in letters, not colour alone) |
| TNM | T from the tumour diameter and gross extension (T1a ≤ 10, T1b ≤ 20, T2 ≤ 40, T3a > 40 mm; T3b strap muscles; T4a, T4b); cN1b if a suspicious lateral node (I-V), else cN1a if central (VI, VII), else cN0; stage by age (< 55: I, M1 II; ≥ 55: I, II, III, IVA, IVB) |

| Source | Status |
|---|---|
| Tessler et al., ACR TI-RADS, JACR 2017 | Not in PMC; points, levels and thresholds checked against two reviews (Ann Med Surg 2024, PMC11374223; Radiol Bras 2022, PMC8864691). "Margin cannot be determined = 0" is from the author's knowledge |
| AJCC 8th edition, differentiated thyroid cancer | T, N and stage groups checked against Perrier et al., CA Cancer J Clin 2018 (PMC5766386) |
| ETA 2013 lymph node guideline (Leenhardt) | Full text not available; criteria from the author's knowledge |

## Limits

- **Not a medical device.** A reporting aid: the reader checks and owns every line. The rules were written from the
  published system and the sources below by the plugin author and have **not** been reviewed by a radiologist.
- Reads no pixels and measures nothing: sizes are typed in. It needs an acquired image on screen only because a tool
  must run on something (`input = "image"`; not on an MPR, slab or MIP plane).
- At most 16 marks (nodules and nodes together). Mark size on the schematic is not a measurement: diameters are typed
  in. Moving a mark from the thyroid into a level (or back) turns it into the other kind; its old descriptors are
  dropped at the next edit.
- Needs radspider with plugin API 8; an older viewer refuses the plugin (`api 8 is not supported`).
- Each change starts Python again (about 0.1-0.3 s).
- Report: a two-column table (item, finding) in the language on screen; *Copy table* puts it on the clipboard as
  tab-separated lines. English and Spanish (`lang/es.toml`).

## Verified

| | |
|---|---|
| Verified (2.0.0) | (1) `python -m unittest tools.test_reports` (18 tests): the rules below, the hit-test of the schematic (lobe thirds, isthmus, levels, outside) and the edit flow with a stand-in SDK (an edit of nodule 1 survives selecting node 2 before the run; labels, tones and cN follow the marks); the window built with the real SDK, within the host limits and serialisable as JSON. (2) Through radspider's plugin host (main at 222ac45, a throwaway test in `tests/plugins.rs`, removed after): first open, then a nodule, a level III node and a mark outside, each selected in turn; the host accepted the 33 shapes and the marks and read back `N1 TR4` circle warn, `L1` square ok, `?` muted. **Not checked:** the look of the sketch and dragging in the GUI (no screenshot), plus everything listed as not checked for 1.0.0 |
| Verified (1.0.0) | **Not run in radspider.** Run outside the viewer with Python 3.13: (1) `python -m unittest tools.test_reports` (16 tests): the scoring rules against the tables in this README (written from the sources below, so they prove the code matches this page, not the ACR documents) with a stand-in SDK; a first open shows no finding and a finding without a category leaves the summary unassigned; every form at its largest built with the real SDK of the radspider checkout (`assets/python/radspider_plugin.py`, `Window._wire`) and checked against the host's window limits (≤ 8 windows, ≤ 32 controls per window, ≤ 64 per instance, unique names); `lang/es.toml` ids and placeholders equal to `lang/template.toml` (made by `python -m radspider_plugin template`); (2) `tools/validate_plugins.py`, `ruff check`. **Not checked:** the radspider host accepting the reply, the look of the windows, *Copy table* pasted into a RIS, the Spanish wording by a native radiologist, the ETA 2013 node criteria against the guideline (its full text was not available) |

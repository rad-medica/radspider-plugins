# Test kit

Plugin id: `org.radspider.testkit` · folder: [`../../org.radspider.testkit`](../../org.radspider.testkit)

TL;DR: one plugin exercising every plugin feature, so a radspider change can be checked against all of them. Not a clinical tool.

| Kind | Entries |
|---|---|
| Series builder nodes (4) | `scale_offset`, `normalize`, `smooth`, `checkerboard` |
| Segmentations (4) | `bands` (progress per slice), `largest_island`, `outside_segments` (reads existing segments), `nothing` (empty result) |
| Tools (8) | `summary`, `report` (chart, picture, ROIs, segment), `histogram` (`button = false`), `slow` (cancel), `fail` (error path), `study` (reads and edits ROIs and segments), `explorer` (interactive window), `windows_demo` (API 6: several windows) |

## API 6 (1.2.0)

| Feature | Where |
|---|---|
| Plugin icon (Phosphor) | `icon = "flask"`: every entry without its own takes it (builder nodes, segmentation cards) |
| Entry icons | `summary`: Phosphor `chart-bar`; `windows_demo`: `app-window`; `explorer`: PNG `icons/testkit.png` (32 × 32, alpha is the mask) |
| Translations | `lang/es.toml`: every manifest text and every marked text of `windows_demo`. `lang/template.toml`: `python -m radspider_plugin template org.radspider.testkit` (SDK on `PYTHONPATH`); regenerate it after changing texts |
| Form first, reuse | `windows_demo`: `window = { reuse = true, open = "form" }`, parameter `gain` on the form |
| Windows | `main` (row: choice + button with icon; table; echo of `ctx.lang` / `ctx.window` / `ctx.windows` / `gain`; section with slider, checkbox, button, text field), `residuals` (tabs: chart / picture + closed section), `log` (`keep` once open) |
| Close / reopen | *Show residuals* off: `residuals` left out of the answer, it closes. *Reopen residuals*: listed with `reopen = True`, also after the user closed it; the checkbox comes back on |
| Series | Zeros sized to the volume on a first run and from *Apply*, named with a marked text |

The other entries return plain (unmarked) strings: the tests compare them as written.

## Verified

| Version | What ran |
|---|---|
| 1.2.0 | radspider `tests/plugins.rs::testkit_plugin_runs_every_entry` (every entry, error, cancel, `windows_demo`: windows, keep, close, reopen, series, marked progress, icons) and `testkit_reads_and_edits_the_study_and_drives_a_window`, Windows, Python 3.13. The API 5 entries of 1.1.0 are not in this kit: the test says so and skips them. GUI: see radspider `docs/FEATURES.md`, plugin API 6 rows |

| Item | |
|---|---|
| Needs | numpy only. Pure-Python loops take minutes on a real CT |
| Module | `testkit.py`, selected with `module = "testkit"` in the manifest |
| Used by | radspider `tests/plugins.rs` (needs `RADSPIDER_PLUGIN_PIP=1` for numpy) |
| Rule | Adding a plugin feature to radspider means adding an entry here that uses it |

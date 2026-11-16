# Test kit

Plugin id: `org.radspider.testkit` · folder: [`../../org.radspider.testkit`](../../org.radspider.testkit)

TL;DR: one plugin exercising every plugin feature, so a radspider change can be checked against all of them. Not a clinical tool.

| Kind | Entries |
|---|---|
| Series builder nodes (4) | `scale_offset`, `normalize`, `smooth`, `checkerboard` |
| Segmentations (4) | `bands` (progress per slice), `largest_island`, `outside_segments` (reads existing segments), `nothing` (empty result) |
| Tools (9) | `summary`, `report` (chart, picture, ROIs, segment), `histogram` (`button = false`), `slow` (cancel), `fail` (error path), `study` (reads and edits ROIs and segments), `explorer` (interactive window), `windows_demo` (API 6: several windows), `image_info` (API 6: runs on the one image on screen) |

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

## Image tools (1.3.0)

`image_info` is declared with `input = "image"` (`icon = "image"`, `tags = ["0008,0060", "0018,0081", "0018,0080", "0028,0030"]`): the host calls it on the one image on screen, as a volume of one slice. It returns one window, `main` ("Image info"), with a table that echoes what an image tool receives:

| Rows | Source |
|---|---|
| Dimensions | `volume.dims` |
| Pixel spacing source | `volume.spacing_source` (`pixel`, `imager`, or `none` when the file has neither) |
| Image frame, Frames in file, Image index, Photometric | `ctx.image.frame`, `.frames`, `.index`, `.photometric` |
| Colour (rgb) | `volume.rgb() is not None` |
| Each declared tag and `<tag> source` | `volume.tags[tag]` and `volume.tag_source(tag)` (`top`, `shared`, `frame`, `alias:gggg,eeee`, or `none`) |
| Series modality, images, frames, phases, phase axis, b-values, gradient directions, image types | the eight fields of `ctx.series` |

A value the host did not give shows as `none`. The labels are marked texts with Spanish translations; the tag rows are the tag ids.

## Verified

| Version | What ran |
|---|---|
| 1.3.0 | radspider `tests/plugins.rs::testkit_image_info`, Windows, Python 3.13 (needs `RADSPIDER_PLUGIN_PIP=1`): one frame of a real file gathered the way the viewer does (`ImageIn`, `SeriesFacts`, declared tags with sources), on `CT_small.dcm` (grey, `128 × 128 × 1`, modality CT, spacing source `pixel`), `US1_UNCR.dcm` (colour: `rgb()` set, spacing source `none`) and frame 3 of `emri_small.dcm` (MR; no functional groups and no TR / TE, so its tags are `top` or `none`). The `shared` and `frame` sources and the `alias:` source are not exercised here (no such file in the corpus): the host's tag tests cover them. `tools/test_tools.py` covers the validator's `input` rules. The GUI was not run for this entry. Everything else of the kit was not rerun for 1.3.0 beyond that test; the rows below are 1.2.0's |
| 1.2.0 | radspider `tests/plugins.rs::testkit_plugin_runs_every_entry` (every entry, error, cancel, `windows_demo`: windows, keep, close, reopen, series, marked progress, icons) and `testkit_reads_and_edits_the_study_and_drives_a_window`, Windows, Python 3.13. The API 5 entries of 1.1.0 are not in this kit: the test says so and skips them. GUI: see radspider `docs/FEATURES.md`, plugin API 6 rows |

| Item | |
|---|---|
| Needs | numpy only. Pure-Python loops take minutes on a real CT |
| Module | `testkit.py`, selected with `module = "testkit"` in the manifest |
| Used by | radspider `tests/plugins.rs` (needs `RADSPIDER_PLUGIN_PIP=1` for numpy) |
| Rule | Adding a plugin feature to radspider means adding an entry here that uses it |

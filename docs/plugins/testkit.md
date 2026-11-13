# Test kit

Plugin id: `org.radspider.testkit` · folder: [`../../org.radspider.testkit`](../../org.radspider.testkit)

TL;DR: one plugin exercising every plugin feature, so a radspider change can be checked against all of them. Not a clinical tool.

| Kind | Entries |
|---|---|
| Series builder nodes (4) | `scale_offset`, `normalize`, `smooth`, `checkerboard` |
| Segmentations (4) | `bands` (progress per slice), `largest_island`, `outside_segments` (reads existing segments), `nothing` (empty result) |
| Tools (7) | `summary`, `report` (chart, picture, ROIs, segment), `histogram` (`button = false`), `slow` (cancel), `fail` (error path), `study` (reads and edits ROIs and segments), `explorer` (interactive window) |

| Item | |
|---|---|
| Needs | numpy only. Pure-Python loops take minutes on a real CT |
| Module | `testkit.py`, selected with `module = "testkit"` in the manifest |
| Used by | radspider `tests/plugins.rs` (needs `RADSPIDER_PLUGIN_PIP=1` for numpy) |
| Rule | Adding a plugin feature to radspider means adding an entry here that uses it |

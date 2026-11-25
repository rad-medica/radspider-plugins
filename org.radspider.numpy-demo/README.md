# NumPy demo

Plugin id: `org.radspider.numpy-demo`

TL;DR: the three entry kinds of `org.radspider.examples`, vectorised with numpy. The plugin to copy when a new one needs
a `requirements.txt`.

| Entry | Kind | Params | Does |
|---|---|---|---|
| *zscore* | synth node | none | (x − mean) / standard deviation over the voxels with data |
| *largest_above* | segmentation | `threshold` (200) | Largest 6-connected region at or above the threshold (flood fill without scipy) |
| *percentiles* | tool | none | 5th, 25th, 50th, 75th and 95th percentile of the voxels with data |

| Item | |
|---|---|
| Requirements | `numpy>=1.26` |
| API | `api = 6`. Icons (Phosphor): plugin and *zscore* `function`, *largest_above* `cube`, *percentiles* `percent`. Spanish catalog `lang/es.toml` |
| Verified | Covered end to end by radspider's `tests/plugins.rs` with `RADSPIDER_PLUGIN_PIP=1` (pip installs numpy). This page was written without rerunning it |

# Examples

Plugin id: `org.radspider.examples`

TL;DR: one entry of each kind, standard library only, no `requirements.txt`. The plugin to copy when writing a new one
(see `docs/DEVELOPING.md`).

| Entry | Kind | Params | Does |
|---|---|---|---|
| *window_clip* | synth node | `lo` (−100), `hi` (300) | Values outside [lo, hi] become no data (NaN) |
| *threshold* | segmentation | `threshold` (200) | Label 1: voxels at or above the threshold |
| *stats* | tool | none | Count, mean, minimum, maximum and the volume of voxels with data |

| Item | |
|---|---|
| API | `api = 6`. Icons (Phosphor): plugin `book-open`, *window_clip* `scissors`, *threshold* `sliders-horizontal`, *stats* `chart-bar`. Spanish catalog `lang/es.toml` |
| Verified | Covered end to end by radspider's `tests/plugins.rs` (needs a `../radspider-plugins` checkout and a Python ≥ 3.10). This page was written without rerunning it |

# Rust example

Plugin id: `org.radspider.rust-example`

TL;DR: `org.radspider.examples` written in Rust: a **native** plugin (`command` in `plugin.toml`, api ≥ 4). radspider
runs the executable directly, so there is no Python, venv or `requirements.txt`. Start here for a native plugin; the
SDK and the protocol are in radspider's `docs/PLUGINS.md` → *Native plugins (Rust)*.

| Entry | Kind | Params | Does |
|---|---|---|---|
| *window_clip* | synth node | `lo` (−100), `hi` (300) | Values outside [lo, hi] become no data (NaN) |
| *threshold* | segmentation | `threshold` (200) | Label 1: voxels at or above the threshold |
| *stats* | tool | none | Count, mean, minimum, maximum and the volume of voxels with data |

| Path | What |
|---|---|
| `plugin.toml` | Manifest: `command = "rust-example"`, no `module`, no `requirements` |
| `Cargo.toml`, `Cargo.lock`, `src/main.rs` | The executable. SDK: `radspider-plugin`, by path from a radspider checkout beside this repository (`../radspider`) |
| `bin/<os>-<arch>/rust-example[.exe]` | The executables radspider picks from (`windows-x86_64`, `linux-x86_64`, `macos-aarch64`). Committed, so the marketplace package is reproducible |
| `lang/es.toml`, `lang/template.toml`, `tr-ids.txt` | Spanish catalog; template made by `radspider-check --plugin-template <plugin dir> --ids tr-ids.txt` (Rust source is not scanned: `tr-ids.txt` lists the run-time ids of `src/main.rs`) |

## Build

```bash
cargo build --release --locked
```

Copy `target/release/rust-example[.exe]` to `bin/<os>-<arch>/` (`std::env::consts::OS`-`ARCH`). The workflow
`.github/workflows/native-plugins.yml` does this for the three systems: it runs on a push that changes `src/`,
`Cargo.toml` or `Cargo.lock` (or by hand), builds Windows x86_64, Linux x86_64 (static, musl) and macOS aarch64,
commits `bin/` and the regenerated `marketplace/index.json` to the same branch. Bump `version` with the source change:
new executables are a file change. `target/` is ignored by git and left out of the package.

| Item | |
|---|---|
| Size | Release build stripped, LTO: about 0.5 MB on Windows |
| Limits | No executable for the user's system (Intel macOS, Linux on ARM): radspider lists the plugin with a warning and a call says where it looked. Values are read with `Volume::values()`, which reads the file on every call |
| API | `api = 6`. Icons (Phosphor): plugin `gear`, *window_clip* `scissors`, *threshold* `sliders-horizontal`, *stats* `chart-bar` |
| Verified | Windows 11, executable built here with `cargo build --release --locked`: radspider's real plugin host (`tests/plugins.rs` helpers, a temporary test that was not committed) installed the folder and ran the three entries on the 24-voxel volume of `stdlib_example_plugin_runs_every_kind`, with the same assertions (NaN outside [50, 100], 60 kept; 4 voxels and `Above 200`; 23 voxels, 0.23 ml, `23 voxels`); an undeclared entry is refused. Linux and macOS executables come from the workflow, not run here. Not driven in the GUI |

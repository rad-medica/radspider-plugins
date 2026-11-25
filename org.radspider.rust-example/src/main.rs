//! `org.radspider.examples` in Rust: one builder node, one segmentation, one tool. The protocol (requests on stdin,
//! answers on stdout) is the SDK's; `println!` would corrupt it, `eprintln!` goes to the plugin log.

use radspider_plugin as rp;

fn main() {
    rp::Plugin::new()
        .synth_node("window_clip", window_clip)
        .segmentation("threshold", threshold)
        .tool("stats", stats)
        .run();
}

/// Values outside [lo, hi] become no data (NaN).
fn window_clip(volume: &rp::Volume, ctx: &rp::Context) -> rp::Result<Vec<f32>> {
    let lo = ctx.param("lo").unwrap_or(-100.0) as f32;
    let hi = ctx.param("hi").unwrap_or(300.0) as f32;
    Ok(volume.values()?.into_iter().map(|v| if (lo..=hi).contains(&v) { v } else { f32::NAN }).collect())
}

/// Label 1: voxels at or above the threshold. NaN compares false, so no data is never labelled.
fn threshold(volume: &rp::Volume, ctx: &rp::Context) -> rp::Result<rp::Labels> {
    let t = ctx.param("threshold").unwrap_or(200.0) as f32;
    let labels = volume.values()?.iter().map(|v| u8::from(*v >= t)).collect();
    Ok(rp::Labels::new(labels, [format!("Above {t}")]))
}

/// Count, mean, minimum, maximum and the volume of the voxels with data.
fn stats(volume: &rp::Volume, _ctx: &rp::Context) -> rp::Result<rp::Output> {
    let header = vec![rp::tr("Statistic"), rp::tr("Value")];
    let values: Vec<f32> = volume.values()?.into_iter().filter(|v| !v.is_nan()).collect();
    if values.is_empty() {
        return Ok(rp::Output { table: vec![header, vec![rp::tr("Voxels with data"), "0".into()]], ..rp::Output::default() });
    }
    let (min, max) = values.iter().fold((f32::INFINITY, f32::NEG_INFINITY), |(lo, hi), v| (lo.min(*v), hi.max(*v)));
    let mean = values.iter().map(|v| f64::from(*v)).sum::<f64>() / values.len() as f64;
    let [sx, sy, sz] = volume.spacing;
    let ml = values.len() as f64 * sx * sy * sz / 1000.0;
    let unit = volume.unit.as_deref().unwrap_or("");
    Ok(rp::Output {
        table: vec![
            header,
            vec![rp::tr("Voxels with data"), values.len().to_string().into()],
            vec![rp::tr("Mean {unit}").arg("unit", unit), ((mean * 1000.0).round() / 1000.0).to_string().into()],
            vec![rp::tr("Minimum {unit}").arg("unit", unit), min.to_string().into()],
            vec![rp::tr("Maximum {unit}").arg("unit", unit), max.to_string().into()],
            vec![rp::tr("Volume (ml)"), ((ml * 1000.0).round() / 1000.0).to_string().into()],
        ],
        message: Some(rp::trn(values.len() as u64, "{n} voxel", "{n} voxels")),
        ..rp::Output::default()
    })
}

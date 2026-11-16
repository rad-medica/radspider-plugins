"""Example plugin: one synthetic node, one segmentation, one tool. Standard library only."""

import math

import radspider_plugin as rp

NAN = float("nan")


@rp.synth_node("window_clip")
def window_clip(volume, ctx):
    lo, hi = ctx.params["lo"], ctx.params["hi"]
    return [v if lo <= v <= hi else NAN for v in volume.values]


@rp.segmentation("threshold")
def threshold(volume, ctx):
    t = ctx.params["threshold"]
    return [1 if v >= t else 0 for v in volume.values], ["Above %g" % t]


@rp.tool("stats")
def stats(volume, ctx):
    vals = [v for v in volume.values if not math.isnan(v)]
    if not vals:
        return rp.Result(table=[[rp.tr("Statistic"), rp.tr("Value")], [rp.tr("Voxels with data"), 0]])
    sx, sy, sz = volume.spacing
    mean = sum(vals) / len(vals)
    unit = volume.unit or ""
    return rp.Result(
        table=[
            [rp.tr("Statistic"), rp.tr("Value")],
            [rp.tr("Voxels with data"), len(vals)],
            [rp.tr("Mean {unit}", unit=unit), round(mean, 3)],
            [rp.tr("Minimum {unit}", unit=unit), min(vals)],
            [rp.tr("Maximum {unit}", unit=unit), max(vals)],
            [rp.tr("Volume (ml)"), round(len(vals) * sx * sy * sz / 1000.0, 3)],
        ],
        message=rp.trn(len(vals), "{n} voxel", "{n} voxels"),
    )

"""radspider test kit: every plugin feature in one module. Uses numpy (see requirements.txt).

The texts of `windows_demo` are marked with rp.tr / rp.trc / rp.trn: the viewer translates them through lang/<tag>.toml.
The other entries return plain strings (data the tests compare as written)."""

import time

import numpy as np

import radspider_plugin as rp


# ------------------------------------------------------------------ series builder nodes


@rp.synth_node("scale_offset")
def scale_offset(volume, ctx):
    gain, offset = ctx.params["gain"], ctx.params["offset"]
    print("scale_offset: gain=%g offset=%g on %s" % (gain, offset, volume.dims))  # goes to the log
    return volume.numpy() * gain + offset


@rp.synth_node("normalize")
def normalize(volume, ctx):
    a = volume.numpy()
    if np.isnan(a).all():
        return a
    lo, hi = np.nanmin(a), np.nanmax(a)
    return (a - lo) / ((hi - lo) or 1.0)


def _box_mean(a, reach):
    """Mean over a box of `reach` voxels each way along every axis; NaN neighbours are left out, NaN voxels stay."""
    valid = ~np.isnan(a)
    total = np.where(valid, a, 0.0).astype(np.float64)
    count = valid.astype(np.float64)
    for axis, r in enumerate(reach):
        if r == 0:
            continue
        n = a.shape[axis]
        idx = np.arange(n)
        lo, hi = np.maximum(idx - r, 0), np.minimum(idx + r + 1, n)
        for arr in (total, count):
            c = np.cumsum(arr, axis=axis)
            c = np.concatenate([np.zeros_like(np.take(c, [0], axis=axis)), c], axis=axis)
            arr[...] = np.take(c, hi, axis=axis) - np.take(c, lo, axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / count
    out[~valid] = np.nan
    return out.astype(np.float32)


@rp.synth_node("smooth")
def smooth(volume, ctx):
    radius = ctx.params["radius_mm"]
    sx, sy, sz = volume.spacing
    # numpy axes are (slice, row, column).
    reach = [int(round(radius / s)) if s > 0 else 0 for s in (sz, sy, sx)]
    ctx.progress(0.1, "smoothing")
    return _box_mean(volume.numpy(), reach)


@rp.synth_node("checkerboard")
def checkerboard(volume, ctx):
    sx, sy, sz = volume.spacing
    a = volume.numpy().copy()
    nz, ny, nx = a.shape
    bx = max(1, int(round(ctx.params["block_x_mm"] / sx)))
    by = max(1, int(round(ctx.params["block_y_mm"] / sy)))
    bz = max(1, int(round(ctx.params["block_z_mm"] / sz)))
    flip = 1 if ctx.params["invert"] >= 0.5 else 0
    z, y, x = np.ogrid[:nz, :ny, :nx]
    a[((x // bx) + (y // by) + (z // bz) + flip) % 2 == 1] = np.nan
    return a


# ------------------------------------------------------------------ segmentations


@rp.segmentation("bands")
def bands(volume, ctx):
    low, high = ctx.params["low"], ctx.params["high"]
    if low > high:
        raise ValueError("Low cut (%g) is above High cut (%g)" % (low, high))
    a = volume.numpy()
    labels = np.zeros(a.shape, np.uint8)
    for z in range(a.shape[0]):
        s = a[z]
        labels[z] = np.where(np.isnan(s), 0, np.where(s < low, 1, np.where(s <= high, 2, 3)))
        ctx.progress((z + 1) / a.shape[0], "slice %d of %d" % (z + 1, a.shape[0]))
    unit = (" " + volume.unit) if volume.unit else ""
    return labels, ["Below %g%s" % (low, unit), "%g to %g%s" % (low, high, unit), "Above %g%s" % (high, unit)]


def _largest_island(mask):
    """The largest 6-connected region of a boolean array (any dimension), by repeated dilation from seeds."""
    best = np.zeros(mask.shape, bool)
    left = mask.copy()
    while left.any():
        seed = np.zeros(mask.shape, bool)
        seed[tuple(i[0] for i in np.nonzero(left))] = True
        while True:
            grown = seed.copy()
            for axis in range(mask.ndim):
                grown |= np.roll(seed, 1, axis) | np.roll(seed, -1, axis)
                # No wrap around the edges.
                edge = [slice(None)] * mask.ndim
                edge[axis] = 0
                grown[tuple(edge)] &= seed[tuple(edge)] | np.take(seed, 1, axis) if mask.shape[axis] > 1 else seed[tuple(edge)]
                edge[axis] = -1
                grown[tuple(edge)] &= seed[tuple(edge)] | np.take(seed, -2, axis) if mask.shape[axis] > 1 else seed[tuple(edge)]
            grown &= mask
            if (grown == seed).all():
                break
            seed = grown
        if seed.sum() > best.sum():
            best = seed
        left &= ~seed
    return best


@rp.segmentation("largest_island")
def largest_island(volume, ctx):
    t = ctx.params["threshold"]
    return _largest_island(volume.numpy() >= t).astype(np.uint8), ["Largest island ≥ %g" % t]


@rp.segmentation("outside_segments")
def outside_segments(volume, ctx):
    """Reads ctx.segments: every voxel with data that no existing segment holds."""
    a = volume.numpy()
    free = ~np.isnan(a)
    for s in ctx.segments or []:
        free &= ~s.mask()
    print("outside_segments: %d existing segments" % len(ctx.segments or []))
    return free.astype(np.uint8), ["Not in any segment"]


@rp.segmentation("nothing")
def nothing(volume, ctx):
    return np.zeros(len(volume), np.uint8)  # labels alone: names are optional


# ------------------------------------------------------------------ tools


@rp.tool("summary")
def summary(volume, ctx):
    a = volume.numpy()
    vals = a[~np.isnan(a)]
    unit = volume.unit or ""
    nx, ny, nz = volume.dims
    sx, sy, sz = volume.spacing
    rows = [
        ["Quantity", "Value", "Unit"],
        ["Grid", "%d × %d × %d" % (nx, ny, nz), "voxels"],
        ["Spacing", "%.3f × %.3f × %.3f" % (sx, sy, sz), "mm"],
        ["Voxels with data", int(vals.size), ""],
        ["Voxels without data", int(a.size - vals.size), ""],
    ]
    if vals.size:
        p5, p50, p95 = np.percentile(vals, [5, 50, 95])
        rows += [
            ["Mean", round(float(vals.mean()), 3), unit],
            ["SD", round(float(vals.std()), 3), unit],
            ["Minimum", float(vals.min()), unit],
            ["5th percentile", float(p5), unit],
            ["Median", float(p50), unit],
            ["95th percentile", float(p95), unit],
            ["Maximum", float(vals.max()), unit],
            ["Volume with data", round(vals.size * sx * sy * sz / 1000.0, 2), "ml"],
        ]
    rows.append(["numpy in this environment", np.__version__, ""])
    return rp.Result(table=rows, message="Test kit: %d voxels summarised" % vals.size)


def _histogram(vals, bins):
    counts, edges = np.histogram(vals, bins=bins)
    return counts, edges


@rp.tool("histogram")
def histogram(volume, ctx):
    bins = int(ctx.params["bins"])
    a = volume.numpy()
    vals = a[~np.isnan(a)]
    table = [["Bin", "From", "To", "Count", "Share %"]]
    if not vals.size:
        return table
    counts, edges = _histogram(vals, bins)
    for i, c in enumerate(counts):
        table.append([i + 1, round(float(edges[i]), 3), round(float(edges[i + 1]), 3), int(c), round(100.0 * c / vals.size, 2)])
    centres = (edges[:-1] + edges[1:]) / 2
    plot = rp.Plot("Histogram", [rp.Series("voxels", centres, counts, kind="bars")], x_label=volume.unit or "value", y_label="count")
    return rp.Result(table=table, plots=[plot])


@rp.tool("report")
def report(volume, ctx):
    """A chart, a picture, ROIs on the image and a segment: everything a tool's window and the study can take."""
    a = volume.numpy()
    k = ctx.slice if ctx.slice is not None else a.shape[0] // 2
    s = a[k]
    t = ctx.params["threshold"]
    vals = s[~np.isnan(s)]
    counts, edges = _histogram(vals, 64) if vals.size else (np.zeros(1), np.array([0.0, 1.0]))
    centres = (edges[:-1] + edges[1:]) / 2
    profile = np.nanmean(s, axis=0)
    plots = [
        rp.Plot("Histogram of slice %d" % (k + 1), [rp.Series("count", centres, counts, kind="bars")], x_label=volume.unit or "value", y_label="pixels"),
        rp.Plot(
            "Column profile",
            [rp.Series("mean", np.arange(profile.size), np.nan_to_num(profile)), rp.Series("max", np.arange(profile.size), np.nan_to_num(np.nanmax(s, axis=0)), kind="points")],
            x_label="column",
            y_label=volume.unit or "value",
        ),
    ]
    # The slice as a grey picture with the bright region in red.
    lo, hi = (np.percentile(vals, [1, 99]) if vals.size else (0.0, 1.0))
    grey = np.clip((np.nan_to_num(s, nan=lo) - lo) / ((hi - lo) or 1.0), 0, 1)
    rgb = np.repeat((grey * 255).astype(np.uint8)[:, :, None], 3, axis=2)
    bright = np.nan_to_num(s, nan=-np.inf) >= t
    rgb[bright] = [255, 60, 60]
    image = rp.Image("Slice %d, ≥ %g in red" % (k + 1, t), s.shape[1], s.shape[0], rgb)
    rois, labels, notes = [], None, "nothing above %g on this slice" % t
    if bright.any():
        island = _largest_island(bright)
        ys, xs = np.nonzero(island)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        cx, cy = float(xs.mean()), float(ys.mean())
        rois = [
            rp.Roi("polygon", k, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]),
            rp.Roi("line", k, [(x0, cy), (x1, cy)]),
            rp.Roi("probe", k, [(cx, cy)]),
            rp.Roi("text", k, [(x0, max(0, y0 - 6))], text="Test kit: %d px ≥ %g" % (island.sum(), t)),
        ]
        vol = np.zeros(a.shape, np.uint8)
        vol[k][island] = 1
        labels = (vol, ["Test kit: bright region, slice %d" % (k + 1)])
        notes = "%d pixels in the largest bright region" % island.sum()
    table = [["Quantity", "Value"], ["Slice", k + 1], ["Threshold", t], ["Pixels ≥ threshold", int(bright.sum())]]
    return rp.Result(table=table, plots=plots, images=[image], rois=rois, labels=labels, message="Slice report: " + notes)


@rp.tool("slow")
def slow(volume, ctx):
    seconds = ctx.params["seconds"]
    start = time.time()
    while True:
        done = time.time() - start
        if done >= seconds:
            break
        ctx.progress(done / seconds, "%.0f of %.0f s" % (done, seconds))
        time.sleep(0.2)
    return rp.Result(table=[["Waited", "Seconds"], ["Done", seconds]], message="Slow tool finished")


@rp.tool("fail")
def fail(volume, ctx):
    raise RuntimeError("this failure is the test: the viewer shows it and carries on")


# ------------------------------------------------------------------ the study: reading and editing ROIs and segments


def _grow_in_plane(mask):
    """`mask` (slices, rows, columns) grown by one voxel along rows and columns, without wrapping round."""
    g = mask.copy()
    g[:, 1:, :] |= mask[:, :-1, :]
    g[:, :-1, :] |= mask[:, 1:, :]
    g[:, :, 1:] |= mask[:, :, :-1]
    g[:, :, :-1] |= mask[:, :, 1:]
    return g


@rp.tool("study")
def study(volume, ctx):
    rows = [["What", "Id", "Kind / name", "Slice / colour", "Points / voxels", "Text / locked"]]
    for r in ctx.rois:
        rows.append(["ROI", r.id, r.kind, r.slice, len(r.points), r.text])
    segments = ctx.segments
    for s in segments or []:
        rows.append(["Segment", s.id, s.name, "#%02x%02x%02x" % s.color, int(s.mask().sum()), "locked" if s.locked else ""])
    replace, delete, add = {}, [], []
    if ctx.rois:
        first = ctx.rois[0]
        replace[first.id] = rp.Roi(first.kind, first.slice, [(x + 1, y) for x, y in first.points], first.text)
        if len(ctx.rois) > 1:
            delete.append(ctx.rois[-1].id)
    k = ctx.slice if ctx.slice is not None else 0
    add.append(rp.Roi("text", k, [(0, 0)], text="Test kit: %d ROIs read" % len(ctx.rois)))
    edits = []
    unlocked = [s for s in segments or [] if not s.locked]
    if unlocked:
        s = unlocked[0]
        edits.append(rp.SegmentEdit(s.id, mask=_grow_in_plane(s.mask()), name=s.name + " (edited)", color=(255, 200, 0)))
        if ctx.params["delete_last"] >= 0.5 and len(unlocked) > 1:
            edits.append(rp.SegmentEdit(unlocked[-1].id, delete=True))
    for s in segments or []:
        if s.locked:
            edits.append(rp.SegmentEdit(s.id, name=s.name + " (must be refused)"))
    seg_note = "no segmentation on this volume" if segments is None else "%d segments" % len(segments)
    return rp.Result(
        table=rows,
        replace_rois=replace,
        delete_rois=delete,
        rois=add,
        segment_edits=edits,
        message="Study: %d ROIs, %s" % (len(ctx.rois), seg_note),
    )


@rp.tool("explorer")
def explorer(volume, ctx):
    """An interactive window: every control change runs this again with ctx.controls and ctx.event."""
    a = volume.numpy()
    nz = a.shape[0]
    c = ctx.controls
    default_k = ctx.slice if ctx.slice is not None else nz // 2
    k = int(min(max(c.get("slice", default_k), 0), nz - 1))
    vals_all = a[~np.isnan(a)]
    lo, hi = (float(vals_all.min()), float(vals_all.max())) if vals_all.size else (0.0, 1.0)
    if hi <= lo:
        hi = lo + 1.0
    t = float(min(max(c.get("threshold", (lo + hi) / 2), lo), hi))
    bins = int(c.get("bins", 32))
    log = bool(c.get("log", False))
    profile = c.get("profile", "columns")
    s = a[k]
    vals = s[~np.isnan(s)]
    counts, edges = np.histogram(vals, bins=bins, range=(lo, hi)) if vals.size else (np.zeros(bins), np.linspace(lo, hi, bins + 1))
    centres = (edges[:-1] + edges[1:]) / 2
    shown = np.log10(counts + 1.0) if log else counts
    axis = 0 if profile == "columns" else 1
    prof = np.nan_to_num(np.nanmean(np.where(np.isnan(s), np.nan, s), axis=axis)) if vals.size else np.zeros(s.shape[1 - axis])
    plots = [
        rp.Plot("Slice %d histogram" % (k + 1), [rp.Series("count", centres, shown, kind="bars")], x_label=volume.unit or "value",
                y_label="log10(count + 1)" if log else "count"),
        rp.Plot("Mean along %s" % profile, [rp.Series("mean", np.arange(prof.size), prof)], x_label=profile[:-1], y_label=volume.unit or "value"),
    ]
    grey = np.clip((np.nan_to_num(s, nan=lo) - lo) / (hi - lo), 0, 1)
    rgb = np.repeat((grey * 255).astype(np.uint8)[:, :, None], 3, axis=2)
    rgb[np.nan_to_num(s, nan=-np.inf) >= t] = [255, 60, 60]
    above = int((vals >= t).sum())
    rois = []
    if ctx.event == "mark":
        rois.append(rp.Roi("text", k, [(s.shape[1] / 2, s.shape[0] / 2)], text="Test kit: ≥ %g here: %d px" % (t, above)))
    controls = [
        rp.Slider("slice", "Slice", k, 0, max(nz - 1, 1), step=1, help="Slice of the volume shown here"),
        rp.Slider("threshold", "Threshold", t, lo, hi, help="Pixels at or above it are red"),
        rp.Number("bins", "Bins", bins, min=2, max=256, step=1),
        rp.Checkbox("log", "Log counts", log),
        rp.Choice("profile", "Profile", ["columns", "rows"], profile),
        rp.Button("mark", "Mark", help="Adds a note with the count on this slice"),
    ]
    return rp.Result(
        table=[["Slice", k + 1], ["Threshold", round(t, 3)], ["Pixels ≥ threshold", above], ["Event", ctx.event or ""]],
        plots=plots,
        images=[rp.Image("Slice %d, ≥ %g in red" % (k + 1, t), s.shape[1], s.shape[0], rgb)],
        rois=rois,
        controls=controls,
        message="Explorer: %s" % (ctx.event or "first run"),
    )


# ------------------------------------------------------------------ API 6: several windows, marked texts


@rp.tool("windows_demo")
def windows_demo(volume, ctx):
    """Three windows from one run, the Python twin of the Rust test kit's windows_demo: main (a row, a table, the
    request echoed, a section of controls), residuals (tabs with a chart, a picture and a closed section) and a log
    kept as the run that opened it left it. *Show residuals* off drops the residuals window from the answer (it
    closes); *Reopen residuals* lists it with reopen=True (it comes back even when the user closed it). A series of
    zeros comes back on a first run and from *Apply*, not from the other controls. The entry opens with a form (its
    `gain` parameter) and reuses its window (plugin.toml)."""
    ctx.progress(0.5, rp.tr("Halfway {p}", p=50))
    c = ctx.controls
    gain = ctx.params.get("gain")
    echo = "%s|%s|%s|gain %g" % (ctx.lang, ctx.window or "-", ",".join(ctx.windows), gain if gain is not None else float("nan"))
    level = float(c.get("level", 50.0))
    reopen = ctx.event == "reopen"
    show = reopen or bool(c.get("show_residuals", True))
    nx, ny, nz = volume.dims
    main = rp.Window("main", rp.tr("Fit"), [
        rp.Row([
            rp.Choice("model", rp.tr("Model"), [rp.tr("Mono"), "offset"], c.get("model")),
            rp.Button("apply", rp.tr("Apply {what}", what="fit"), icon="plus", help=rp.tr("Adds a series of zeros")),
        ]),
        rp.Table([
            [rp.tr("Quantity"), rp.trc("short", "Value")],
            [rp.trn(nz, "{n} slice", "{n} slices"), "%d × %d" % (nx, ny)],
            [rp.tr("Level"), level],
        ]),
        rp.Label(echo, weak=True),
        rp.Section(rp.tr("Display"), [
            rp.Slider("level", rp.tr("Level"), level, 0, 100, step=1, help=rp.tr("Moves the line of the chart")),
            rp.Row([
                rp.Checkbox("show_residuals", rp.tr("Show residuals"), show, help=rp.tr("Off closes the residuals window")),
                rp.Button("reopen", rp.tr("Reopen residuals"), icon="arrow-counter-clockwise",
                          help=rp.tr("Shows the residuals window again, also after you closed it")),
            ]),
            rp.TextField("note", rp.tr("Note"), c.get("note", "hi"), max_length=20),
        ]),
    ], size=(520, 420), icon="plus")
    residuals = None
    if show:
        x = list(range(11))
        chart = rp.Plot(rp.tr("Chart"), [rp.Series(rp.tr("Level"), x, [level * i / 10.0 for i in x])],
                        x_label=rp.tr("Step"), y_label=rp.tr("Level"))
        shade = int(round(level * 2.55))
        picture = rp.Image(rp.tr("Level {level} as grey", level=level), 16, 16,
                           bytes([shade if (i // 3) % 16 < 8 else 255 - shade for i in range(16 * 16 * 3)]))
        residuals = rp.Window("residuals", rp.tr("Residuals"), [
            rp.Tabs([
                (rp.tr("Map"), [chart]),
                (rp.tr("Picture"), [picture, rp.Section(rp.tr("About"), [rp.Label(rp.tr("Closed on the first run"))], open=False)]),
            ]),
        ], size=(420, 360), reopen=reopen)
    # Nothing to recompute: once on screen, the log stays as the run that opened it left it.
    if "log" in ctx.windows:
        log = rp.Window("log", keep=True)
    else:
        log = rp.Window("log", rp.tr("Log"), [rp.Label(rp.tr("Opened by the first run"))])
    volumes = []
    if ctx.event in (None, "apply"):
        volumes.append(rp.NewVolume(np.zeros(len(volume), np.float32), rp.tr("Fit {n}", n=1)))
    return rp.Result(windows=[main, residuals, log], volumes=volumes)


# ------------------------------------------------------------------ API 6: image tools


def _show(value):
    """A value as a table cell: no value is "none", a list is comma separated, a float has no trailing zeros."""
    if value is None:
        return "none"
    if isinstance(value, (list, tuple)):
        return ", ".join(_show(v) for v in value) if value else "none"
    if isinstance(value, float):
        return "%g" % value
    return str(value)


@rp.tool("image_info")
def image_info(volume, ctx):
    """An image tool (`input = "image"`): the one image on screen comes as a volume of one slice. The table echoes
    everything the SDK gives such a tool: the grid, `spacing_source`, `ctx.image`, the declared tags with
    `tag_source`, every `ctx.series` field and whether `rgb()` holds a colour image."""
    nx, ny, nz = volume.dims
    image, series = ctx.image, ctx.series
    rows = [
        [rp.tr("Quantity"), rp.tr("Value")],
        [rp.tr("Dimensions"), "%d × %d × %d" % (nx, ny, nz)],
        [rp.tr("Pixel spacing source"), _show(volume.spacing_source)],
        [rp.tr("Image frame"), _show(image.frame)],
        [rp.tr("Frames in file"), _show(image.frames)],
        [rp.tr("Image index"), _show(image.index)],
        [rp.tr("Photometric"), _show(image.photometric)],
        [rp.tr("Colour (rgb)"), str(volume.rgb() is not None)],
    ]
    for tag in ("0008,0060", "0018,0081", "0018,0080", "0028,0030"):
        rows.append([tag, _show(volume.tags[tag])])
        rows.append([tag + " source", _show(volume.tag_source(tag))])
    rows += [
        [rp.tr("Series modality"), _show(series.modality)],
        [rp.tr("Series images"), _show(series.images)],
        [rp.tr("Series frames"), _show(series.frames)],
        [rp.tr("Series phases"), _show(series.phases)],
        [rp.tr("Series phase axis"), _show(series.phase_axis)],
        [rp.tr("Series b-values"), _show(series.b_values)],
        [rp.tr("Series gradient directions"), _show(series.gradient_directions)],
        [rp.tr("Series image types"), _show(series.image_types)],
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("Image info"), [rp.Table(rows)])])

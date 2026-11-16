"""Volume tools: voxel arithmetic, two-series maps and a rigid registration.

| Entry | Kind | Does |
|---|---|---|
| ``invert`` | node | x → −x |
| ``scale`` | node | x → factor · x (second step of ``normalize``) |
| ``normalize`` | tool | mean inside a closed measurement or a segment, and the factor that brings it to a target |
| ``delta_r2_map`` | two-volume tool | ΔR2 = −(factor / TE) · ln(second / active), as a new series with statistics |
| ``merge_tag_grids`` | two-volume tool | product of two tagged series, slice maxima equalised |
| ``rigid_register`` | two-volume tool | 6-parameter rigid registration by mutual information, multi-resolution |

Conventions (those of ``org.radspider.registration-demo``): ``volume`` is the fixed image, ``ctx.other`` the moving
one; arrays are (slices, rows, columns); a voxel (x, y, z) lies at ``origin + M · (x, y, z)`` with ``M`` the columns
``row``, ``col``, ``normal`` times the spacing; NaN is "no data". Everything a two-volume tool returns is on the grid
of ``volume``.
"""

import numpy as np
from scipy import ndimage, optimize

import radspider_plugin as rp

#: Voxels handled at once when a second series is resampled (float64 coordinates cost 8 bytes each per axis).
BAND_VOXELS = 4_000_000
#: The finest pyramid level of the registration holds about this many voxels of the fixed image.
FINE_VOXELS = 2_000_000
#: A pose that leaves fewer of the samples inside the moving image than this is not scored.
MIN_OVERLAP = 0.25
#: Function evaluations per pyramid level, at most.
MAX_EVALUATIONS = 500
CLOSED = ("polygon", "ellipse")
#: Voxel order (x, y, z) ↔ array order (z, y, x).
FLIP = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])


# ---------------------------------------------------------------------------------------------------------------
# Series builder nodes
# ---------------------------------------------------------------------------------------------------------------


@rp.synth_node("invert")
def invert(volume, ctx):
    # Plain negation, not max + min − x: that is what the reference tool does to grey images. −NaN is NaN.
    return -volume.numpy()


@rp.synth_node("scale")
def scale(volume, ctx):
    factor = float(ctx.params["factor"])
    if not np.isfinite(factor):
        raise ValueError("Factor is not a number: enter the factor the Normalize tool reported")
    return (volume.numpy() * np.float32(factor)).astype(np.float32)


# ---------------------------------------------------------------------------------------------------------------
# Regions: closed measurements and segments
# ---------------------------------------------------------------------------------------------------------------


def roi_mask(roi, ny, nx):
    """Voxels of one slice whose centre lies inside a polygon (even-odd rule) or an ellipse (the two points are
    opposite corners of its box). Points are voxel centres, as in ``rp.Roi``."""
    mask = np.zeros((ny, nx), dtype=bool)
    pts = np.asarray(roi.points, dtype=np.float64).reshape(-1, 2)
    if roi.kind == "ellipse" and len(pts) >= 2:
        (xa, ya), (xb, yb) = pts[0], pts[1]
        cx, cy, rx, ry = (xa + xb) / 2, (ya + yb) / 2, abs(xb - xa) / 2, abs(yb - ya) / 2
        if rx <= 0 or ry <= 0:
            return mask
        ys, xs = np.ogrid[0:ny, 0:nx]
        return ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1.0
    if roi.kind != "polygon" or len(pts) < 3:
        return mask
    x0, x1 = max(int(np.floor(pts[:, 0].min())), 0), min(int(np.ceil(pts[:, 0].max())), nx - 1)
    y0, y1 = max(int(np.floor(pts[:, 1].min())), 0), min(int(np.ceil(pts[:, 1].max())), ny - 1)
    if x1 < x0 or y1 < y0:
        return mask
    ys, xs = np.mgrid[y0 : y1 + 1, x0 : x1 + 1].astype(np.float64)
    inside = np.zeros(xs.shape, dtype=bool)
    for (xa, ya), (xb, yb) in zip(pts, np.roll(pts, -1, axis=0)):
        if ya == yb:
            continue
        crosses = (ya > ys) != (yb > ys)
        with np.errstate(invalid="ignore"):
            inside ^= crosses & (xs < xa + (ys - ya) * (xb - xa) / (yb - ya))
    mask[y0 : y1 + 1, x0 : x1 + 1] = inside
    return mask


def closed_rois(volume, ctx):
    nz = volume.dims[2]
    return [r for r in ctx.rois if r.kind in CLOSED and 0 <= r.slice < nz and len(r.points) >= (3 if r.kind == "polygon" else 2)]


def segment_by_number(ctx, n):
    if ctx.segments is None:
        raise ValueError(
            "Segment %d asked for, but the series has no segmentation on this volume: open MPR on the series and "
            "make a segment, or set the segment number to 0" % n
        )
    if n > len(ctx.segments):
        raise ValueError(
            "Segment %d asked for, but the series has %d: use 1 (top of the Segments panel) to %d"
            % (n, len(ctx.segments), len(ctx.segments))
        )
    return ctx.segments[n - 1]


def rois_mask(volume, rois):
    nx, ny, nz = volume.dims
    mask = np.zeros((nz, ny, nx), dtype=bool)
    for r in rois:
        mask[r.slice] |= roi_mask(r, ny, nx)
    return mask


def stats_rows(values, unit=""):
    """Mean, SD (population), minimum, maximum and count of a 1-D array of finite values."""
    v = values.astype(np.float64)
    if unit:
        names = (
            rp.tr("Mean ({unit})", unit=unit), rp.tr("SD ({unit})", unit=unit),
            rp.tr("Minimum ({unit})", unit=unit), rp.tr("Maximum ({unit})", unit=unit),
        )
    else:
        names = (rp.tr("Mean"), rp.tr("SD"), rp.tr("Minimum"), rp.tr("Maximum"))
    return [
        [names[0], _sig(v.mean())],
        [names[1], _sig(v.std())],
        [names[2], _sig(v.min())],
        [names[3], _sig(v.max())],
        [rp.tr("Voxels"), int(v.size)],
    ]


def _sig(x, digits=6):
    x = float(x)
    return float("%.*g" % (digits, x)) if np.isfinite(x) else x


# ---------------------------------------------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------------------------------------------


def _roi_place(roi, on_screen):
    """Where the measurement used by Normalize lies: its kind, its slice, and why this one was picked."""
    n = roi.slice + 1
    if roi.kind == "polygon":
        if on_screen:
            return rp.tr("polygon on slice {n} (the slice on screen)", n=n)
        return rp.tr("polygon on slice {n} (last listed)", n=n)
    if on_screen:
        return rp.tr("ellipse on slice {n} (the slice on screen)", n=n)
    return rp.tr("ellipse on slice {n} (last listed)", n=n)


@rp.tool("normalize")
def normalize(volume, ctx):
    target = float(ctx.params["target"])
    number = ctx.params["segment"]
    a = volume.numpy()
    if number >= 1:
        seg = segment_by_number(ctx, number)
        inside = a[seg.mask()]
        where = rp.tr("segment {n} “{name}”", n=number, name=seg.name[:200])
    else:
        rois = closed_rois(volume, ctx)
        if not rois:
            raise ValueError(
                "No closed measurement: draw a polygon or an ellipse on the series, or set the segment number to "
                "the place of a segment in the Segments panel (1 = top)"
            )
        # The viewer does not say which measurement is selected, nor when each was drawn. Closest to "the selected
        # ROI of the image on screen": the last one listed on the slice on screen, else the last one listed.
        here = [r for r in rois if ctx.slice is not None and r.slice == ctx.slice]
        roi = (here or rois)[-1]
        inside = a[roi.slice][roi_mask(roi, volume.dims[1], volume.dims[0])]
        where = _roi_place(roi, bool(here))
    inside = inside[np.isfinite(inside)]
    if inside.size == 0:
        raise ValueError("The region (%s) holds no voxel with data: make it larger or move it onto the image" % where)
    mean = float(inside.astype(np.float64).mean())
    if mean == 0.0:
        raise ValueError("The mean inside the region (%s) is 0: no factor can bring it to %g" % (where, target))
    factor = target / mean
    text = 'plugin("org.radspider.volume-tools/scale", x, %.9g)' % factor
    table = [[rp.tr("Quantity"), rp.tr("Value")], [rp.tr("Region"), where]]
    table += stats_rows(inside, volume.unit or "")
    table += [[rp.tr("Target mean"), target], [rp.tr("Factor (target / mean)"), _sig(factor, 9)],
              [rp.tr("Series builder"), text]]
    return rp.Result(
        table=table,
        message=rp.tr(
            "Mean {mean} → factor {factor}. Series builder: Volume tools · Scale with that factor",
            mean="%.6g" % mean, factor="%.9g" % factor,
        ),
    )


# ---------------------------------------------------------------------------------------------------------------
# Geometry and resampling
# ---------------------------------------------------------------------------------------------------------------


def affine_of(v):
    """``M`` (3 × 3) and ``o`` with patient position = ``o + M · (x, y, z)``. Without a place: the grid itself."""
    if v.origin is None or v.row is None or v.col is None or v.normal is None:
        return np.diag(np.array(v.spacing, dtype=np.float64)), np.zeros(3)
    m = np.array([v.row, v.col, v.normal], dtype=np.float64).T * np.array(v.spacing, dtype=np.float64)
    return m, np.array(v.origin, dtype=np.float64)


def same_grid(a, b):
    if a.dims != b.dims:
        return False
    if a.origin is None or b.origin is None:
        return True  # nothing says otherwise
    (ma, oa), (mb, ob) = affine_of(a), affine_of(b)
    return bool(np.allclose(ma, mb, atol=1e-3) and np.allclose(oa, ob, atol=1e-3))


def same_frame(a, b):
    return bool(a.frame_of_reference and b.frame_of_reference and a.frame_of_reference == b.frame_of_reference)


def frames_text(a, b):
    if not (a.frame_of_reference and b.frame_of_reference):
        return rp.tr("unknown")
    return rp.tr("same") if a.frame_of_reference == b.frame_of_reference else rp.tr("different")


def second_text(other, resampled):
    """The second series' size and how it was put on the grid of the active one."""
    x, y, z = other.dims
    if resampled:
        return rp.tr("{x} × {y} × {z}, resampled through patient coordinates", x=x, y=y, z=z)
    return rp.tr("{x} × {y} × {z}, same grid", x=x, y=y, z=z)


def voxel_map(fixed_affine, moving_affine, rotation=None, translation=None, centre=None):
    """``J``, ``b`` with moving voxel (x, y, z) = ``J`` · fixed voxel + ``b`` for the rigid map
    ``q = R (p − c) + c + t`` from fixed to moving patient positions (identity when left out)."""
    (mf, of), (mm, om) = fixed_affine, moving_affine
    r = np.eye(3) if rotation is None else rotation
    t = np.zeros(3) if translation is None else translation
    c = np.zeros(3) if centre is None else centre
    inv = np.linalg.inv(mm)
    return inv @ r @ mf, inv @ (r @ (of - c) + c + t - om)


def resampled_bands(a, j, b, dims):
    """``a`` (the moving array) at the voxels of the fixed grid ``dims``, trilinear, NaN outside, in bands along z:
    yields ``(z0, z1, block)``."""
    nx, ny, nz = dims
    m, off = FLIP @ j @ FLIP, FLIP @ b
    limits = np.array(a.shape, dtype=np.float64) - 1.0
    step = max(1, BAND_VOXELS // (nx * ny))
    ys = np.arange(ny, dtype=np.float64)[None, :, None]
    xs = np.arange(nx, dtype=np.float64)[None, None, :]
    for z0 in range(0, nz, step):
        z1 = min(nz, z0 + step)
        block = ndimage.affine_transform(
            a, m, offset=off + m[:, 0] * z0, output_shape=(z1 - z0, ny, nx), output=np.float32, order=1, mode="nearest"
        )
        # mode="nearest" keeps a voxel that lands on the last sample from being lost to rounding; what really
        # lies outside is cleared here.
        zs = np.arange(z0, z1, dtype=np.float64)[:, None, None]
        outside = np.zeros(block.shape, dtype=bool)
        for axis in range(3):
            c = m[axis, 0] * zs + m[axis, 1] * ys + m[axis, 2] * xs + off[axis]
            outside |= (c < -1e-3) | (c > limits[axis] + 1e-3)
        block[outside] = np.nan
        yield z0, z1, block


def second_on_grid(volume, other, tool):
    """How the second series gets onto the grid of the first for a voxel-by-voxel tool: ``None`` when the grids are
    the same, else the voxel map through patient coordinates. Refuses when nothing relates the two."""
    if other is None:
        raise ValueError("This tool needs a second series: pick one under Second series in Plugin tools")
    if same_grid(volume, other):
        return None
    if not same_frame(volume, other) or volume.origin is None or other.origin is None:
        raise ValueError(
            "The second series lies on another grid and does not share the Frame of Reference of the active one "
            "(%s), so its voxels cannot be matched to it. Pick a series of the same acquisition, or register it "
            "first (Volume tools · PetSpectFusion) and run %s on the registered series" % (frames_text(volume, other), tool)
        )
    return voxel_map(affine_of(volume), affine_of(other))


def second_bands(volume, other, how):
    """The second series on the grid of the first, in bands along z."""
    b = other.numpy()
    nx, ny, nz = volume.dims
    if how is None:
        step = max(1, BAND_VOXELS // (nx * ny))
        for z0 in range(0, nz, step):
            yield z0, min(nz, z0 + step), b[z0 : z0 + step]
    else:
        yield from resampled_bands(b, how[0], how[1], volume.dims)


# ---------------------------------------------------------------------------------------------------------------
# ΔR2 map
# ---------------------------------------------------------------------------------------------------------------


def region_of(volume, ctx, choice):
    """The voxels a map is limited to, and how to call them. ``choice``: −1 whole volume, 0 automatic (closed
    measurements, else visible segments, else everything), n ≥ 1 segment n."""
    if choice < 0:
        return None, rp.tr("whole volume")
    if choice >= 1:
        seg = segment_by_number(ctx, choice)
        return seg.mask(), rp.tr("segment {n} “{name}”", n=choice, name=seg.name[:200])
    rois = closed_rois(volume, ctx)
    if rois:
        slices = sorted({r.slice for r in rois})
        return rois_mask(volume, rois), rp.tr(
            "{n} closed measurement(s) on {slices} slice(s)", n=len(rois), slices=len(slices)
        )
    visible = [s for s in ctx.segments or [] if s.visible]
    if visible:
        mask = visible[0].mask().copy()
        for s in visible[1:]:
            mask |= s.mask()
        return mask, rp.trn(len(visible), "{n} visible segment", "{n} visible segments")
    return None, rp.tr("whole volume (no closed measurement, no visible segment)")


@rp.tool("delta_r2_map")
def delta_r2_map(volume, ctx):
    te = float(ctx.params["te_ms"])
    threshold = float(ctx.params["threshold"])
    factor = float(ctx.params["factor"])
    if not te > 0:
        raise ValueError("TE must be above 0 ms")
    how = second_on_grid(volume, ctx.other, "T2 Ratio Map")
    region, where = region_of(volume, ctx, ctx.params["region"])
    pre = volume.numpy()
    nx, ny, nz = volume.dims
    out = np.full((nz, ny, nx), np.nan, dtype=np.float32)
    gain = -factor / te
    floor = max(threshold, 0.0)  # a logarithm needs both above 0 whatever the threshold says
    for z0, z1, post in second_bands(volume, ctx.other, how):
        v1 = pre[z0:z1].astype(np.float64)
        v2 = post.astype(np.float64)
        with np.errstate(invalid="ignore"):
            ok = (v1 > floor) & (v2 > floor)
        if region is not None:
            ok &= region[z0:z1]
        band = out[z0:z1]
        band[ok] = (gain * np.log(v2[ok] / v1[ok])).astype(np.float32)
        ctx.progress(0.9 * z1 / nz, rp.tr("ΔR2: slice {z} of {n}", z=z1, n=nz))
    values = out[np.isfinite(out)]
    if values.size == 0:
        raise ValueError(
            "No voxel of %s has both series above the threshold (%g): lower the threshold, or check that the "
            "second series covers the region" % (where, threshold)
        )
    unit = "1/s" if factor == 1000.0 else "1/ms" if factor == 1.0 else "%g/ms" % factor
    table = [
        [rp.tr("Quantity"), rp.tr("Value")],
        [rp.tr("Formula"), rp.tr("−({factor} / {te} ms) · ln(second / active)", factor="%g" % factor, te="%g" % te)],
        [rp.tr("Second series"), second_text(ctx.other, how is not None)],
        [rp.tr("Region"), where],
        [rp.tr("Threshold (both series above)"), threshold],
    ]
    table += stats_rows(values, "ΔR2, " + unit)
    lo, hi = np.percentile(values, [0.5, 99.5])
    if not hi > lo:
        lo, hi = float(values.min()) - 0.5, float(values.max()) + 0.5
    counts, edges = np.histogram(values, bins=64, range=(float(lo), float(hi)))
    plot = rp.Plot(
        rp.tr("ΔR2 histogram (0.5th to 99.5th percentile)"),
        [rp.Series(rp.tr("voxels"), (edges[:-1] + edges[1:]) / 2, counts, kind="bars")],
        x_label=rp.tr("ΔR2 ({unit})", unit=unit),
        y_label=rp.tr("voxels"),
    )
    return rp.Result(
        volume=out,
        volume_name=rp.tr("Delta R2 map (TE {te} ms)", te="%g" % te),
        table=table,
        plots=[plot],
        message=rp.trn(
            int(values.size), "ΔR2 mean {mean} {unit} over {n} voxel ({where})",
            "ΔR2 mean {mean} {unit} over {n} voxels ({where})",
            mean="%.4g" % values.astype(np.float64).mean(), unit=unit, where=str(where)[:300],
        ),
    )


# ---------------------------------------------------------------------------------------------------------------
# Tag grid
# ---------------------------------------------------------------------------------------------------------------


@rp.tool("merge_tag_grids")
def merge_tag_grids(volume, ctx):
    how = second_on_grid(volume, ctx.other, "Cardiac Tagging MRI")
    equalize = ctx.params["equalize"]
    first = volume.numpy()
    nx, ny, nz = volume.dims
    out = np.empty((nz, ny, nx), dtype=np.float32)
    peaks = np.zeros(nz, dtype=np.float64)
    for z0, z1, second in second_bands(volume, ctx.other, how):
        a = first[z0:z1].astype(np.float64)
        product = a * second.astype(np.float64)
        for k in range(z1 - z0):
            # Each slice of the product is divided by the full range (maximum − minimum) of the first series' slice.
            data = a[k][np.isfinite(a[k])]
            width = float(data.max() - data.min()) if data.size else 0.0
            if width > 0:
                product[k] /= width
            good = product[k][np.isfinite(product[k])]
            peaks[z0 + k] = max(float(good.max()), 0.0) if good.size else 0.0
        out[z0:z1] = product.astype(np.float32)
        ctx.progress(0.9 * z1 / nz, rp.tr("Tag grid: slice {z} of {n}", z=z1, n=nz))
    if not np.isfinite(out).any():
        raise ValueError("The two series share no voxel with data: check that the second series covers the active one")
    top = float(peaks.max())
    scaled = 0
    if equalize and top > 0:
        # Every slice is stretched so that its maximum is the largest slice maximum. A slice whose maximum is not
        # above 0 has nothing to stretch and is left as it is.
        for k in np.flatnonzero(peaks > 0):
            out[k] *= np.float32(top / peaks[k])
            scaled += 1
    if equalize:
        equalised = rp.trn(
            nz, "yes, {scaled} of {n} slice to {top}", "yes, {scaled} of {n} slices to {top}",
            scaled=scaled, top="%.6g" % top,
        )
    else:
        equalised = rp.tr("no")
    table = [
        [rp.tr("Quantity"), rp.tr("Value")],
        [rp.tr("Combination"), rp.tr("product of the two series ÷ range of the active series' slice")],
        [rp.tr("Second series"), second_text(ctx.other, how is not None)],
        [rp.tr("Slices"), nz],
        [rp.tr("Slice maxima equalised"), equalised],
        [rp.tr("Smallest slice maximum before"), _sig(peaks.min())],
        [rp.tr("Largest slice maximum before"), _sig(top)],
    ]
    return rp.Result(
        volume=out, volume_name=rp.tr("Tag grid"), table=table,
        message=rp.trn(nz, "Tag grid of {n} slice", "Tag grid of {n} slices"),
    )


# ---------------------------------------------------------------------------------------------------------------
# Rigid registration by mutual information
# ---------------------------------------------------------------------------------------------------------------


def rotation_matrix(degrees):
    """Rotation about the patient x, then y, then z axis (``R = Rz · Ry · Rx``), angles in degrees."""
    ax, ay, az = np.radians(np.asarray(degrees, dtype=np.float64))
    cx, sx, cy, sy, cz, sz = np.cos(ax), np.sin(ax), np.cos(ay), np.sin(ay), np.cos(az), np.sin(az)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def shrunk(a, affine, target):
    """A coarser copy of ``a`` with voxels of about ``target`` mm: means over whole blocks (no-data voxels left out
    of the mean), and the affine of the coarse grid."""
    m, o = affine
    size = np.linalg.norm(m, axis=0)  # mm along x, y, z
    nz, ny, nx = a.shape
    s = [int(np.clip(round(target / size[i]), 1, max(1, n // 4))) for i, n in enumerate((nx, ny, nz))]
    sx, sy, sz = s
    cz, cy, cx = nz // sz, ny // sy, nx // sx
    if (sx, sy, sz) == (1, 1, 1):
        out = a.astype(np.float32)
    else:
        out = np.empty((cz, cy, cx), dtype=np.float32)
        for k in range(cz):
            block = a[k * sz : (k + 1) * sz, : cy * sy, : cx * sx]
            ok = np.isfinite(block)
            total = np.where(ok, block, 0.0).reshape(sz, cy, sy, cx, sx).sum(axis=(0, 2, 4), dtype=np.float64)
            count = ok.reshape(sz, cy, sy, cx, sx).sum(axis=(0, 2, 4))
            out[k] = np.where(count > 0, total / np.maximum(count, 1), np.nan)
    step = np.array(s, dtype=np.float64)
    return out, (m * step, o + m @ ((step - 1.0) / 2.0))


def intensity_range(values, what):
    lo, hi = np.percentile(values, [0.5, 99.5])
    if not hi > lo:
        lo, hi = float(values.min()), float(values.max())
    if not hi > lo:
        raise ValueError("The %s series has one value everywhere it has data: nothing to register" % what)
    return float(lo), float(hi)


def centre_of_mass(a, affine):
    """Patient position of the intensity-weighted centre, the background (1st percentile) taken off."""
    ok = np.isfinite(a)
    if not ok.any():
        raise ValueError("A series has no data")
    w = np.where(ok, a, 0.0).astype(np.float64) - np.percentile(a[ok], 1.0)
    w[~ok | (w < 0)] = 0.0
    total = w.sum()
    if not total > 0:
        w, total = ok.astype(np.float64), float(ok.sum())
    z, y, x = (float((w.sum(axis=tuple(i for i in range(3) if i != axis)) * np.arange(a.shape[axis])).sum() / total) for axis in range(3))
    m, o = affine
    return o + m @ np.array([x, y, z])


class Metric:
    """Mutual information between samples of the fixed image and the moving image under a rigid map, from a joint
    histogram whose entries are spread linearly over the two nearest bins of each image (a first-order Parzen
    window: the value changes smoothly with the pose)."""

    def __init__(self, fixed, fixed_affine, moving, moving_affine, bins, samples, centre):
        nz, ny, nx = fixed.shape
        index = np.flatnonzero(np.isfinite(fixed).reshape(-1))
        if index.size < 100:
            raise ValueError("The active series has too little data to register")
        if index.size > samples:
            # A fixed seed: the same two series give the same answer every run.
            index = np.sort(np.random.default_rng(76926294).choice(index, size=samples, replace=False))
        values = fixed.reshape(-1)[index].astype(np.float64)
        z, rest = np.divmod(index, ny * nx)
        y, x = np.divmod(rest, nx)
        m, o = fixed_affine
        self.points = o + np.stack([x, y, z], axis=1).astype(np.float64) @ m.T
        self.centre = centre
        self.bins = bins
        self.moving = moving
        mm, om = moving_affine
        self.to_voxel, self.origin = np.linalg.inv(mm), om
        self.limits = np.array([moving.shape[2], moving.shape[1], moving.shape[0]], dtype=np.float64) - 1.0
        self.f0, self.fw = self._bin(values, intensity_range(values, "active"))
        self.range = intensity_range(moving[np.isfinite(moving)], "second")
        self.evaluations = 0

    def _bin(self, values, limits):
        lo, hi = limits
        pos = np.clip((values - lo) / (hi - lo), 0.0, 1.0) * (self.bins - 1)
        low = np.minimum(pos.astype(np.intp), self.bins - 2)
        return low, pos - low

    def __call__(self, degrees, translation):
        """(mutual information in nats, fraction of the samples inside the moving image)."""
        self.evaluations += 1
        q = (self.points - self.centre) @ rotation_matrix(degrees).T + self.centre + np.asarray(translation)
        v = (q - self.origin) @ self.to_voxel.T
        inside = np.all((v >= 0.0) & (v <= self.limits), axis=1)
        if inside.sum() < MIN_OVERLAP * len(v):
            return 0.0, float(inside.mean())
        v = v[inside]
        m = ndimage.map_coordinates(self.moving, [v[:, 2], v[:, 1], v[:, 0]], order=1, mode="nearest")
        ok = np.isfinite(m)
        share = float(ok.sum()) / len(self.points)
        if share < MIN_OVERLAP:
            return 0.0, share
        m0, mw = self._bin(m[ok].astype(np.float64), self.range)
        f0, fw = self.f0[inside][ok], self.fw[inside][ok]
        b = self.bins
        flat = f0 * b + m0
        joint = (
            np.bincount(flat, (1 - fw) * (1 - mw), b * b)
            + np.bincount(flat + 1, (1 - fw) * mw, b * b)
            + np.bincount(flat + b, fw * (1 - mw), b * b)
            + np.bincount(flat + b + 1, fw * mw, b * b)
        ).reshape(b, b)
        joint /= joint.sum()
        pf, pm = joint.sum(axis=1), joint.sum(axis=0)
        filled = joint > 0
        return float((joint[filled] * np.log(joint[filled] / np.outer(pf, pm)[filled])).sum()), share


def register(fixed, fixed_affine, moving, moving_affine, levels, bins, samples, start, progress):
    """The rigid map ``q = R (p − c) + c + t`` from fixed to moving positions that maximises mutual information.
    Returns a dict with ``degrees``, ``translation``, ``centre``, the metric before and after, and a log per level."""
    mf, of = fixed_affine
    nz, ny, nx = fixed.shape
    extent = np.linalg.norm(mf, axis=0) * np.array([nx, ny, nz])
    centre = of + mf @ ((np.array([nx, ny, nz], dtype=np.float64) - 1.0) / 2.0)
    radius = float(extent.mean()) / 2.0
    fine = max(float(np.linalg.norm(mf, axis=0).min()), float(np.prod(extent) / FINE_VOXELS) ** (1.0 / 3.0))
    degrees, translation = np.zeros(3), np.asarray(start, dtype=np.float64)
    log, first, metric, built = [], None, None, 0.25 / levels
    for level in range(levels):
        target = fine * 2 ** (levels - 1 - level)
        base = level / levels
        progress(
            0.05 + 0.75 * base,
            rp.tr("Level {level} of {levels}: building {mm} mm copies", level=level + 1, levels=levels,
                  mm="%.1f" % target),
        )
        f, fa = shrunk(fixed, fixed_affine, target)
        m, ma = shrunk(moving, moving_affine, target)
        metric = Metric(f, fa, m, ma, bins, samples, centre)
        before, share = metric(degrees, translation)
        if share < MIN_OVERLAP:
            raise ValueError(
                "The two series overlap too little at the start (%.0f %% of the active one): pick the right second "
                "series, or set Start to 1 to begin from the centres of mass" % (100 * share)
            )
        if first is None:
            first = before
        # One unit of every parameter moves the edge of the image by about one voxel of this level.
        unit = np.concatenate([np.full(3, np.degrees(target / radius)), np.full(3, target)])
        x0 = np.concatenate([degrees, translation]) / unit

        def cost(x, metric=metric, unit=unit, base=base, level=level):
            value = -metric(x[:3] * unit[:3], x[3:] * unit[3:])[0]
            if metric.evaluations % 20 == 0:
                done = min(metric.evaluations / MAX_EVALUATIONS, 1.0)
                progress(
                    0.05 + 0.75 * (base + (built + (1 - built) * done) / levels),
                    rp.tr(
                        "Level {level} of {levels} ({mm} mm): mutual information {mi}",
                        level=level + 1, levels=levels, mm="%.1f" % target, mi="%.4f" % -value,
                    ),
                )
            return value

        found = optimize.minimize(cost, x0, method="Powell", options={"xtol": 0.02, "ftol": 1e-5, "maxfev": MAX_EVALUATIONS})
        best = np.asarray(found.x, dtype=np.float64).reshape(-1) * unit
        after = metric(best[:3], best[3:])[0]
        if after >= before:
            degrees, translation = best[:3], best[3:]
        else:
            after = before
        log.append((level + 1, target, f.shape, len(metric.points), metric.evaluations, before, after))
    final = metric(degrees, translation)
    # "Before" on the finest copies, so that the two figures of the table are comparable.
    initial = metric(np.zeros(3), np.asarray(start, dtype=np.float64))
    return {
        "degrees": degrees, "translation": translation, "centre": centre, "before": initial[0], "after": final[0],
        "overlap": final[1], "first": first, "log": log,
    }


@rp.tool("rigid_register")
def rigid_register(volume, ctx):
    other = ctx.other
    if other is None:
        raise ValueError("This tool needs a second series: pick one under Second series in Plugin tools")
    levels = ctx.params["levels"]
    bins = ctx.params["bins"]
    samples = ctx.params["samples"] * 1000
    if min(volume.dims) < 2 or min(other.dims) < 2:
        raise ValueError("Both series need at least 2 slices, rows and columns")
    fixed, moving = volume.numpy(), other.numpy()
    fa, ma = affine_of(volume), affine_of(other)
    ctx.progress(0.01, rp.tr("Starting position"))
    shared = same_frame(volume, other) and volume.origin is not None and other.origin is not None
    by_mass = not shared or ctx.params["start"] == "centres of mass"
    if by_mass:
        # Different Frames of Reference: the stored positions say nothing about each other, so the centres of mass
        # (of coarse copies) are laid on each other.
        coarse = max(np.linalg.norm(fa[0], axis=0).max(), np.linalg.norm(ma[0], axis=0).max()) * 2
        start = centre_of_mass(*shrunk(moving, ma, coarse)) - centre_of_mass(*shrunk(fixed, fa, coarse))
        if shared:
            how = rp.tr("centres of mass")
        else:
            frames = str(frames_text(volume, other))
            if frames == "unknown":
                how = rp.tr("centres of mass (Frames of Reference unknown)")
            elif frames == "same":
                how = rp.tr("centres of mass (Frames of Reference same)")
            else:
                how = rp.tr("centres of mass (Frames of Reference different)")
    else:
        start = np.zeros(3)
        how = rp.tr("patient coordinates (same Frame of Reference)")
    found = register(fixed, fa, moving, ma, levels, bins, samples, start, ctx.progress)
    rotation = rotation_matrix(found["degrees"])
    j, b = voxel_map(fa, ma, rotation, found["translation"], found["centre"])
    nx, ny, nz = volume.dims
    out = np.empty((nz, ny, nx), dtype=np.float32)
    for z0, z1, block in resampled_bands(moving, j, b, volume.dims):
        out[z0:z1] = block
        ctx.progress(0.82 + 0.17 * z1 / nz, rp.tr("Resampling the second series: slice {z} of {n}", z=z1, n=nz))
    covered = float(np.isfinite(out).mean())
    d, t = found["degrees"], found["translation"]
    sx, sy, sz = other.spacing
    table = [
        [rp.tr("Quantity"), rp.tr("Value")],
        [
            rp.tr("Second series"),
            rp.tr(
                "{x} × {y} × {z}, {sx} × {sy} × {sz} mm", x=other.dims[0], y=other.dims[1], z=other.dims[2],
                sx="%.3g" % sx, sy="%.3g" % sy, sz="%.3g" % sz,
            ),
        ],
        [rp.tr("Frames of Reference"), frames_text(volume, other)],
        [rp.tr("Start"), how],
        [rp.tr("Start offset x, y, z (mm)"), "%.2f, %.2f, %.2f" % tuple(start)],
        [rp.tr("Rotation about x (deg)"), round(float(d[0]), 3)],
        [rp.tr("Rotation about y (deg)"), round(float(d[1]), 3)],
        [rp.tr("Rotation about z (deg)"), round(float(d[2]), 3)],
        [rp.tr("Translation x (mm)"), round(float(t[0]), 3)],
        [rp.tr("Translation y (mm)"), round(float(t[1]), 3)],
        [rp.tr("Translation z (mm)"), round(float(t[2]), 3)],
        [rp.tr("Rotation centre x, y, z (mm)"), "%.2f, %.2f, %.2f" % tuple(found["centre"])],
        [rp.tr("Mutual information before"), round(found["before"], 5)],
        [rp.tr("Mutual information after"), round(found["after"], 5)],
        [rp.tr("Active series covered by the result (%)"), round(100 * covered, 1)],
    ]
    for level, target, shape, points, evaluations, before, after in found["log"]:
        table.append([
            rp.tr(
                "Level {level} ({mm} mm, {x} × {y} × {z})", level=level, mm="%.1f" % target, x=shape[2], y=shape[1],
                z=shape[0],
            ),
            rp.tr(
                "{points} samples, {evaluations} evaluations, MI {before} → {after}", points=points,
                evaluations=evaluations, before="%.4f" % before, after="%.4f" % after,
            ),
        ])
    return rp.Result(
        volume=out,
        volume_name=rp.tr("Registered (rigid)"),
        table=table,
        message=rp.tr(
            "Rotation {rx}, {ry}, {rz}°; translation {tx}, {ty}, {tz} mm; mutual information {before} → {after}",
            rx="%.2f" % d[0], ry="%.2f" % d[1], rz="%.2f" % d[2], tx="%.1f" % t[0], ty="%.1f" % t[1],
            tz="%.1f" % t[2], before="%.3f" % found["before"], after="%.3f" % found["after"],
        ),
    )

"""Registration demo: the smallest two-volume tool.

``volume`` is the fixed image (the active series), ``ctx.other`` the moving one (the second series the user picked).
The tool finds one translation, no rotation and no scaling, and returns the moving image on the fixed grid.

| Step | |
|---|---|
| 1 | The moving image is resampled onto the fixed grid through patient coordinates (trilinear), when the two grids differ |
| 2 | The peak of the cross-correlation (FFT) of a coarse copy gives the shift to the voxel; three more passes on a central block, from where it points, refine it to a fraction of a voxel |
| 3 | The shifted moving image goes back as a new series; the table has the shift and the match before and after |

Limits: translation only; a shift beyond half the volume wraps around and is wrong; cross-correlation wants the
same kind of image twice (CT and CT, the same MR sequence): across modalities it finds nothing useful. It is a demo of the API, not a clinical registration.
"""

import numpy as np

import radspider_plugin as rp

#: Most voxels of the coarse pass, and most voxels per axis of the refining block.
COARSE_VOXELS = 4_000_000
BLOCK = 128
#: Passes after the coarse one.
REFINE = 3


def _matrix(v):
    """3 × 3 matrix taking voxel (x, y, z) to mm from the origin, and the origin."""
    m = np.array([v.row, v.col, v.normal], dtype=np.float64).T * np.array(v.spacing, dtype=np.float64)
    return m, np.array(v.origin, dtype=np.float64)


def _same_grid(a, b):
    if a.dims != b.dims:
        return False
    if a.origin is None or b.origin is None:
        return True  # nothing says otherwise
    (ma, oa), (mb, ob) = _matrix(a), _matrix(b)
    return np.allclose(ma, mb, atol=1e-3) and np.allclose(oa, ob, atol=1e-3)


def _trilinear(a, x, y, z):
    """``a`` (slices, rows, columns) at fractional voxels; NaN outside."""
    nz, ny, nx = a.shape
    inside = (x >= 0) & (x <= nx - 1) & (y >= 0) & (y <= ny - 1) & (z >= 0) & (z <= nz - 1)
    x0 = np.clip(np.floor(x).astype(np.intp), 0, max(nx - 2, 0))
    y0 = np.clip(np.floor(y).astype(np.intp), 0, max(ny - 2, 0))
    z0 = np.clip(np.floor(z).astype(np.intp), 0, max(nz - 2, 0))
    x1, y1, z1 = np.minimum(x0 + 1, nx - 1), np.minimum(y0 + 1, ny - 1), np.minimum(z0 + 1, nz - 1)
    fx, fy, fz = x - x0, y - y0, z - z0
    out = np.zeros(x.shape, dtype=np.float64)
    for zi, wz in ((z0, 1 - fz), (z1, fz)):
        for yi, wy in ((y0, 1 - fy), (y1, fy)):
            for xi, wx in ((x0, 1 - fx), (x1, fx)):
                w = wz * wy * wx
                # A corner of no weight must not bring its NaN in.
                out += np.where(w > 0, w * a[zi, yi, xi], 0.0)
    out[~inside] = np.nan
    return out.astype(np.float32)


def on_fixed_grid(fixed, moving, progress):
    """The moving image sampled at the voxel centres of the fixed grid, and how it got there."""
    a = moving.numpy()
    if _same_grid(fixed, moving):
        return a.astype(np.float32), "same grid"
    if fixed.origin is None or moving.origin is None:
        raise ValueError("the two series have different grids and no place in the patient to relate them")
    (mf, of), (mm, om) = _matrix(fixed), _matrix(moving)
    to_moving = np.linalg.inv(mm)
    m = to_moving @ mf
    t = to_moving @ (of - om)
    nx, ny, nz = fixed.dims
    xs, ys = np.meshgrid(np.arange(nx, dtype=np.float64), np.arange(ny, dtype=np.float64))
    out = np.empty((nz, ny, nx), dtype=np.float32)
    for k in range(nz):
        c = [m[i, 0] * xs + m[i, 1] * ys + m[i, 2] * k + t[i] for i in range(3)]
        out[k] = _trilinear(a, c[0], c[1], c[2])
        if k % 16 == 0:
            progress(0.4 * k / nz, "Resampling the second series")
    return out, "resampled through patient coordinates"


def _filled(a):
    """Zero mean, no-data voxels at the mean: they add nothing to the correlation."""
    ok = np.isfinite(a)
    if not ok.any():
        raise ValueError("a volume has no data where the two series overlap")
    out = np.where(ok, a, 0.0).astype(np.float64)
    out -= out[ok].mean()
    out[~ok] = 0.0
    return out


def find_peak(f, m, subvoxel):
    """``s`` (z, y, x) in voxels with ``m(p) ≈ f(p - s)``: where the content of ``f`` went in ``m``. The peak of the
    cross-correlation (one FFT each way), then a parabola through its neighbours for the fraction."""
    corr = np.fft.irfftn(np.conj(np.fft.rfftn(_filled(f))) * np.fft.rfftn(_filled(m)), s=f.shape)
    peak = np.unravel_index(int(np.argmax(corr)), corr.shape)
    shift = []
    for axis, p in enumerate(peak):
        n = corr.shape[axis]
        d = 0.0
        if subvoxel and n > 2:
            at = list(peak)
            at[axis] = (p - 1) % n
            before = corr[tuple(at)]
            at[axis] = (p + 1) % n
            after = corr[tuple(at)]
            bend = before - 2 * corr[peak] + after
            if bend < 0:
                d = float(np.clip(0.5 * (before - after) / bend, -0.5, 0.5))
        s = p + d
        shift.append(s - n if s > n / 2 else s)
    return np.array(shift)


def _moved_whole(a, i, axis):
    """``out[k] = a[k + i]`` along ``axis``, NaN where that falls outside."""
    out = np.full(a.shape, np.nan, dtype=np.float32)
    n = a.shape[axis]
    if abs(i) >= n:
        return out
    src = [slice(None)] * 3
    dst = [slice(None)] * 3
    src[axis] = slice(max(i, 0), n + min(i, 0))
    dst[axis] = slice(max(-i, 0), n + min(-i, 0))
    out[tuple(dst)] = a[tuple(src)]
    return out


def moved(a, shift):
    """``out(p) = a(p + shift)``, linear between voxels, NaN outside."""
    for axis, s in enumerate(shift):
        i = int(np.floor(s))
        f = float(s - i)
        lo = _moved_whole(a, i, axis)
        a = lo if f < 1e-6 else ((1 - f) * lo + f * _moved_whole(a, i + 1, axis)).astype(np.float32)
    return a


def match(f, m):
    """Normalised cross-correlation and mean absolute difference over the voxels both have."""
    ok = np.isfinite(f) & np.isfinite(m)
    if ok.sum() < 2:
        return float("nan"), float("nan"), 0
    a, b = f[ok].astype(np.float64), m[ok].astype(np.float64)
    a0, b0 = a - a.mean(), b - b.mean()
    den = np.sqrt((a0 * a0).sum() * (b0 * b0).sum())
    return (float((a0 * b0).sum() / den) if den > 0 else float("nan")), float(np.abs(a - b).mean()), int(ok.sum())


def find_shift(f, m, subvoxel, progress):
    """The translation of ``m`` onto ``f`` in voxels (z, y, x): ``moved(m, shift)`` lies over ``f``."""
    step = max(1, int(np.ceil((f.size / COARSE_VOXELS) ** (1 / 3))))
    progress(0.45, "Coarse search")
    shift = np.rint(find_peak(f[::step, ::step, ::step], m[::step, ::step, ::step], False) * step)
    block = tuple(slice(max(0, (n - BLOCK) // 2), max(0, (n - BLOCK) // 2) + min(n, BLOCK)) for n in f.shape)
    # Content the shift pushed out of the picture pulls the first peak towards zero: look again from where it
    # points, whole voxels first, the fraction last.
    for i in range(REFINE):
        progress(0.55 + 0.3 * i / REFINE, "Refining")
        last = i == REFINE - 1
        more = find_peak(f[block], moved(m, shift)[block], subvoxel and last)
        shift = shift + (more if last else np.rint(more))
    return shift


@rp.tool("translate")
def translate(volume, ctx):
    other = ctx.other
    if other is None:
        raise ValueError("this tool needs a second series")
    fixed = volume.numpy()
    start, how = on_fixed_grid(volume, other, ctx.progress)
    shift = find_shift(fixed, start, ctx.params["subvoxel"] >= 0.5, ctx.progress)
    ctx.progress(0.85, "Moving the second series")
    result = moved(start, shift)
    before, after = match(fixed, start), match(fixed, result)
    # Where the second series' content lies from the fixed one's, along the fixed grid's x, y and slice axes.
    x, y, z = (float(shift[2]), float(shift[1]), float(shift[0]))
    mm = (x * volume.spacing[0], y * volume.spacing[1], z * volume.spacing[2])
    frames = (
        "unknown" if not (volume.frame_of_reference and other.frame_of_reference)
        else "same" if volume.frame_of_reference == other.frame_of_reference
        else "different"
    )
    unit = other.unit or ""
    table = [
        ["Quantity", "Value"],
        ["Second series", "%d × %d × %d, %s" % (other.dims + (how,))],
        ["Frames of Reference", frames],
        ["Offset x (mm)", round(mm[0], 3)],
        ["Offset y (mm)", round(mm[1], 3)],
        ["Offset z (mm)", round(mm[2], 3)],
        ["Offset x (voxels)", round(x, 3)],
        ["Offset y (voxels)", round(y, 3)],
        ["Offset z (voxels)", round(z, 3)],
        ["Correlation before", round(before[0], 4)],
        ["Correlation after", round(after[0], 4)],
        [("Mean |difference| before (%s)" % unit).replace(" ()", ""), round(before[1], 3)],
        [("Mean |difference| after (%s)" % unit).replace(" ()", ""), round(after[1], 3)],
        ["Voxels compared after", after[2]],
    ]
    return rp.Result(
        volume=result,
        volume_name="Registered (translation)",
        table=table,
        message="Offset %.1f, %.1f, %.1f mm; correlation %.3f → %.3f" % (mm + (before[0], after[0])),
    )

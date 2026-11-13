"""ROI tools: measurements in, numbers, measurements and segments out. numpy + scipy.ndimage.

Ten tools that work on what the user drew (lines, probes, notes, polygons, ellipses). All geometry is done in mm
with ``volume.spacing``: a point (x, y) of a slice is at (x * spacing[0], y * spacing[1]) mm in that slice.

Conventions shared by the tools:

* "the slice on screen" is ``ctx.slice``; tables show it 1-based ("Image"), as the viewer counts.
* "most recent" is the last one in ``ctx.rois`` on a slice: the host lists a slice's measurements in the order
  they were made.
* a pixel belongs to a closed shape when its centre is inside it (even-odd rule; an edge belongs to the pixels on
  its right / below, so adjacent shapes never share a pixel).
"""

import math

import numpy as np
from scipy import ndimage

import radspider_plugin as rp

CLOSED = ("polygon", "ellipse")
CALCIUM_HU = 130.0
REFERENCE_THICKNESS_MM = 3.0  # Agatston 1990 scored 3 mm slices


# ------------------------------------------------------------------ geometry helpers


def _screen_slice(volume, ctx):
    k = ctx.slice
    if k is None:
        raise ValueError("No slice on screen: click an image of the series and run the tool again")
    k = int(k)
    if not 0 <= k < volume.dims[2]:
        raise ValueError("The slice on screen (%d) is outside the volume (%d slices)" % (k + 1, volume.dims[2]))
    return k


def _mm(points, volume):
    """Points (x, y) in voxels as an (n, 2) array in mm of the slice plane."""
    return np.asarray(points, dtype=np.float64).reshape(-1, 2) * np.array(volume.spacing[:2])


def _voxels(points_mm, volume):
    return [(float(x), float(y)) for x, y in np.asarray(points_mm) / np.array(volume.spacing[:2])]


def _length_mm(roi, volume):
    p = _mm(roi.points, volume)
    return float(np.hypot(*(p[1] - p[0])))


def _polygon_area_centroid(p):
    """Area (unsigned) and area centroid of a closed polygon given as (n, 2); vertex mean when it has no area."""
    q = np.roll(p, -1, axis=0)
    cross = p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]
    signed = cross.sum() / 2.0
    if abs(signed) < 1e-12:
        return 0.0, p.mean(axis=0)
    centroid = ((p + q) * cross[:, None]).sum(axis=0) / (6.0 * signed)
    return abs(float(signed)), centroid


def _polygon_perimeter(p):
    return float(np.hypot(*(np.roll(p, -1, axis=0) - p).T).sum())


def _point_in_polygon(pt, p):
    q = np.roll(p, -1, axis=0)
    inside = False
    for (ax, ay), (bx, by) in zip(p, q):
        if (ay <= pt[1]) != (by <= pt[1]) and pt[0] < ax + (pt[1] - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def _polygon_mask(points, ny, nx):
    """Pixels of a (ny, nx) slice whose centre is inside the polygon (voxel coordinates), even-odd rule."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    mask = np.zeros((ny, nx), bool)
    x0, x1 = max(int(math.ceil(p[:, 0].min())), 0), min(int(math.floor(p[:, 0].max())), nx - 1)
    y0, y1 = max(int(math.ceil(p[:, 1].min())), 0), min(int(math.floor(p[:, 1].max())), ny - 1)
    if x0 > x1 or y0 > y1:
        return mask
    xs = np.arange(x0, x1 + 1, dtype=np.float64)[None, :]
    ys = np.arange(y0, y1 + 1, dtype=np.float64)[:, None]
    inside = np.zeros((ys.size, xs.size), bool)
    for (ax, ay), (bx, by) in zip(p, np.roll(p, -1, axis=0)):
        if ay == by:
            continue
        crosses = (ay <= ys) != (by <= ys)
        inside ^= crosses & (xs < ax + (ys - ay) * (bx - ax) / (by - ay))
    mask[y0 : y1 + 1, x0 : x1 + 1] = inside
    return mask


def _ellipse_mask(points, ny, nx):
    (xa, ya), (xb, yb) = points[0], points[1]
    cx, cy, a, b = (xa + xb) / 2.0, (ya + yb) / 2.0, abs(xb - xa) / 2.0, abs(yb - ya) / 2.0
    if a <= 0 or b <= 0:
        return np.zeros((ny, nx), bool)
    ys, xs = np.ogrid[:ny, :nx]
    return ((xs - cx) / a) ** 2 + ((ys - cy) / b) ** 2 <= 1.0


def _shape_mask(roi, ny, nx):
    return _polygon_mask(roi.points, ny, nx) if roi.kind == "polygon" else _ellipse_mask(roi.points, ny, nx)


def _shape_geometry(roi, volume):
    """(area mm², perimeter mm, centre in voxels) of a polygon or an ellipse."""
    p = _mm(roi.points, volume)
    if roi.kind == "polygon":
        area, centroid = _polygon_area_centroid(p)
        return area, _polygon_perimeter(p), tuple(centroid / np.array(volume.spacing[:2]))
    a, b = abs(p[1, 0] - p[0, 0]) / 2.0, abs(p[1, 1] - p[0, 1]) / 2.0
    # Ramanujan's second approximation: exact for a circle, error below 0.04 % up to an axis ratio of 10.
    h = ((a - b) / (a + b)) ** 2 if a + b > 0 else 0.0
    perimeter = math.pi * (a + b) * (1.0 + 3.0 * h / (10.0 + math.sqrt(4.0 - 3.0 * h)))
    centre = np.asarray(roi.points, dtype=np.float64)[:2].mean(axis=0)
    return math.pi * a * b, perimeter, tuple(centre)


def _stats(values):
    """(n, mean, SD, min, max, sum) of the values with data; SD is the population SD."""
    v = values[~np.isnan(values)].astype(np.float64)
    if not v.size:
        return 0, None, None, None, None, None
    return int(v.size), float(v.mean()), float(v.std()), float(v.min()), float(v.max()), float(v.sum())


def _r(v, digits=3):
    return "" if v is None else round(float(v), digits)


def _patient(volume, x, y, z):
    """Patient mm of a voxel; without a place in the patient, mm from the first voxel along the volume's axes."""
    p = volume.to_patient(x, y, z)
    return p if p is not None else (x * volume.spacing[0], y * volume.spacing[1], z * volume.spacing[2])


def _two_lines(lines, what):
    for r in lines:
        if _length_is_zero(r):
            raise ValueError("A line of %s has no length: redraw it" % what)
    return lines[-2], lines[-1]


def _length_is_zero(roi):
    (x0, y0), (x1, y1) = roi.points[0], roi.points[1]
    return x0 == x1 and y0 == y1


# ------------------------------------------------------------------ 1. Cobb angle


@rp.tool("cobb_angle")
def cobb_angle(volume, ctx):
    k = _screen_slice(volume, ctx)
    lines = [r for r in ctx.rois if r.kind == "line" and r.slice == k]
    if len(lines) < 2:
        raise ValueError(
            "Cobb angle needs two lines on the slice on screen (found %d): draw one along each endplate first" % len(lines)
        )
    first, second = _two_lines(lines[-2:], "the Cobb angle")
    a, b = _mm(first.points, volume), _mm(second.points, volume)
    u, v = a[1] - a[0], b[1] - b[0]
    cos = abs(float(u @ v)) / (float(np.hypot(*u)) * float(np.hypot(*v)))
    angle = math.degrees(math.acos(min(cos, 1.0)))
    table = [
        ["Quantity", "Value", "Unit"],
        ["Image", k + 1, ""],
        ["Cobb angle", round(angle, 1), "°"],
        ["Supplement", round(180.0 - angle, 1), "°"],
        ["Line 1 length", round(float(np.hypot(*u)), 2), "mm"],
        ["Line 2 length", round(float(np.hypot(*v)), 2), "mm"],
    ]
    roi = rp.Roi("cobb", k, [tuple(first.points[0]), tuple(first.points[1]), tuple(second.points[0]), tuple(second.points[1])])
    return rp.Result(table=table, rois=[roi], message="Cobb angle %.1f° (supplement %.1f°)" % (angle, 180.0 - angle))


# ------------------------------------------------------------------ 2. Export ROIs


@rp.tool("export_rois")
def export_rois(volume, ctx):
    if not ctx.rois:
        raise ValueError("The series has no measurements: draw at least one, then export")
    a = volume.numpy()
    nz, ny, nx = a.shape
    header = [
        "Id", "Image", "Kind", "Text", "Points", "Length mm", "Area mm2", "Perimeter mm",
        "Centre x mm", "Centre y mm", "Centre z mm", "Pixels", "Mean", "SD", "Min", "Max", "Total",
        "Points voxel (x y z)", "Points patient mm (x y z)",
    ]  # fmt: skip
    table = [header]
    for i, r in enumerate(ctx.rois):
        pts = np.asarray(r.points, dtype=np.float64).reshape(-1, 2)
        length = area = perimeter = None
        centre = tuple(pts.mean(axis=0))
        stats = (None,) * 6
        if r.kind == "line":
            length = _length_mm(r, volume)
        elif r.kind in CLOSED:
            area, perimeter, centre = _shape_geometry(r, volume)
            if 0 <= r.slice < nz:
                stats = _stats(a[r.slice][_shape_mask(r, ny, nx)])
        c = _patient(volume, centre[0], centre[1], r.slice)
        voxel = "; ".join("%.3f %.3f %d" % (x, y, r.slice) for x, y in pts)
        patient = "; ".join("%.3f %.3f %.3f" % _patient(volume, x, y, r.slice) for x, y in pts)
        n, mean, sd, lo, hi, total = stats
        table.append([
            r.id, r.slice + 1, r.kind, r.text or "", len(pts), _r(length), _r(area), _r(perimeter),
            _r(c[0]), _r(c[1]), _r(c[2]), "" if n is None else n, _r(mean), _r(sd), _r(lo), _r(hi), _r(total),
            voxel, patient,
        ])  # fmt: skip
        ctx.progress((i + 1) / len(ctx.rois), "measurement %d of %d" % (i + 1, len(ctx.rois)))
    note = "" if volume.origin is not None else " (no place in the patient: mm are from the first voxel)"
    return rp.Result(table=table, message="%d measurements: Save as CSV… writes the table%s" % (len(ctx.rois), note))


# ------------------------------------------------------------------ 3. Rotate ROI


@rp.tool("rotate_roi")
def rotate_roi(volume, ctx):
    k = _screen_slice(volume, ctx)
    angle = float(ctx.params["angle_deg"])
    here = [r for r in ctx.rois if r.slice == k and r.kind in ("polygon", "line")]
    if not here:
        raise ValueError("No polygon or line on the slice on screen: draw one, or scroll to its image, and run again")
    chosen = here if ctx.params["all_on_slice"] >= 0.5 else here[-1:]
    t = math.radians(angle)
    # Counter-clockwise as seen on screen, where y points down: (1, 0) turned by 90° must become (0, -1).
    turn = np.array([[math.cos(t), math.sin(t)], [-math.sin(t), math.cos(t)]])
    table = [["Id", "Kind", "Centre x (voxel)", "Centre y (voxel)", "Rotated by °"]]
    replace = {}
    for r in chosen:
        p = _mm(r.points, volume)
        centre = _polygon_area_centroid(p)[1] if r.kind == "polygon" else p.mean(axis=0)
        # Rotating in mm keeps the shape: in voxels a non-square pixel would shear it.
        replace[r.id] = rp.Roi(r.kind, r.slice, _voxels((p - centre) @ turn.T + centre, volume), r.text)
        cx, cy = centre / np.array(volume.spacing[:2])
        table.append([r.id, r.kind, round(float(cx), 2), round(float(cy), 2), angle])
    return rp.Result(table=table, replace_rois=replace, message="Rotated %d measurement(s) by %g°" % (len(chosen), angle))


# ------------------------------------------------------------------ 4. Points to line


@rp.tool("points_to_line")
def points_to_line(volume, ctx):
    probes = sorted((r for r in ctx.rois if r.kind == "probe"), key=lambda r: r.slice)  # stable: keeps list order
    if len({r.slice for r in probes}) < 2:
        raise ValueError("Points to line needs probes on at least two different slices (found %d probes)" % len(probes))
    added = []
    table = [["Image", "x (voxel)", "y (voxel)", "x mm", "y mm", "z mm", "Point"]]
    length = 0.0
    for p, q in zip(probes, probes[1:]):
        (x0, y0), (x1, y1) = p.points[0], q.points[0]
        a, b = np.array(_patient(volume, x0, y0, p.slice)), np.array(_patient(volume, x1, y1, q.slice))
        length += float(np.linalg.norm(b - a))
        table.append([p.slice + 1, _r(x0), _r(y0), *(_r(c) for c in a), "placed"])
        for z in range(p.slice + 1, q.slice):
            # Linear in voxel indices = a straight line in the patient: the grid is regular.
            f = (z - p.slice) / (q.slice - p.slice)
            x, y = x0 + f * (x1 - x0), y0 + f * (y1 - y0)
            added.append(rp.Roi("probe", z, [(x, y)], text="generated"))
            table.append([z + 1, _r(x), _r(y), *(_r(c) for c in _patient(volume, x, y, z)), "generated"])
    last = probes[-1]
    lx, ly = last.points[0]
    table.append([last.slice + 1, _r(lx), _r(ly), *(_r(c) for c in _patient(volume, lx, ly, last.slice)), "placed"])
    message = "%d probes joined: %d added, path length %.1f mm" % (len(probes), len(added), length)
    return rp.Result(table=table, rois=added, message=message)


# ------------------------------------------------------------------ 5. Sphere volumes


@rp.tool("sphere_volumes")
def sphere_volumes(volume, ctx):
    lines = [r for r in ctx.rois if r.kind == "line"]
    if ctx.slice is not None and sum(r.slice == ctx.slice for r in lines) >= 2:
        lines = [r for r in lines if r.slice == ctx.slice]
    if len(lines) < 2:
        raise ValueError("Volume calculator needs two lines (found %d): draw the first and the second diameter" % len(lines))
    first, second = _two_lines(lines[-2:], "the diameters")
    d1, d2 = _length_mm(first, volume), _length_mm(second, volume)
    v1, v2 = math.pi * d1**3 / 6.0, math.pi * d2**3 / 6.0  # mm³
    change = 100.0 * v2 / v1 - 100.0
    table = [
        ["Quantity", "Value", "Unit"],
        ["Diameter 1 (image %d)" % (first.slice + 1), round(d1, 2), "mm"],
        ["Diameter 2 (image %d)" % (second.slice + 1), round(d2, 2), "mm"],
        ["Volume 1", round(v1 / 1000.0, 4), "ml"],
        ["Volume 2", round(v2 / 1000.0, 4), "ml"],
        ["Change", round((v2 - v1) / 1000.0, 4), "ml"],
        ["Change", round(change, 2), "%"],
        ["Ratio volume 2 / volume 1", round(v2 / v1, 3), "×"],
        ["Doublings (log2 of the ratio)", round(math.log2(v2 / v1), 3), ""],
    ]
    return rp.Result(table=table, message="%.2f ml → %.2f ml: %+.2f %%, ×%.2f" % (v1 / 1000.0, v2 / 1000.0, change, v2 / v1))


# ------------------------------------------------------------------ 6. ROIs to labels


def _shape_names(shapes, rois, volume):
    """A name per closed shape: its own text, else the text of a note placed inside it on its slice, else its kind."""
    ny, nx = volume.dims[1], volume.dims[0]
    notes = [r for r in rois if r.kind == "text" and (r.text or "").strip()]
    names = []
    for r in shapes:
        name = (r.text or "").strip()
        if not name:
            for t in notes:
                x, y = t.points[0]
                if t.slice != r.slice or not (0 <= round(x) < nx and 0 <= round(y) < ny):
                    continue
                if r.kind == "polygon":
                    inside = _point_in_polygon((x, y), np.asarray(r.points, dtype=np.float64))
                else:
                    inside = bool(_ellipse_mask(r.points, ny, nx)[int(round(y)), int(round(x))])
                if inside:
                    name = t.text.strip()
                    break
        names.append(name or r.kind.capitalize())
    return names


@rp.tool("rois_to_labels")
def rois_to_labels(volume, ctx):
    shapes = [r for r in ctx.rois if r.kind in CLOSED and 0 <= r.slice < volume.dims[2]]
    if not shapes:
        raise ValueError("No closed measurements in the series: draw polygons or ellipses around the structure first")
    nx, ny, nz = volume.dims
    names = _shape_names(shapes, ctx.rois, volume)
    order = []
    labels = np.zeros((nz, ny, nx), np.uint8)
    for i, (r, name) in enumerate(zip(shapes, names)):
        if name not in order:
            if len(order) == 255:
                raise ValueError("More than 255 different names: a label volume holds 255 segments at most")
            order.append(name)
        # A later shape wins where two with different names overlap: one label per voxel.
        labels[r.slice][_shape_mask(r, ny, nx)] = order.index(name) + 1
        ctx.progress((i + 1) / len(shapes), "shape %d of %d" % (i + 1, len(shapes)))
    counts = np.bincount(labels.ravel(), minlength=len(order) + 1)
    kept = [i for i in range(1, len(order) + 1) if counts[i]]
    if not kept:
        raise ValueError("The closed measurements hold no pixel centre: draw them larger")
    # Names without a voxel are dropped and the values renumbered: label value i must be name i.
    remap = np.zeros(len(order) + 1, np.uint8)
    remap[kept] = np.arange(1, len(kept) + 1)
    labels = remap[labels]
    ml = volume.spacing[0] * volume.spacing[1] * volume.spacing[2] / 1000.0
    table = [["Segment", "Shapes", "Slices", "Voxels", "Volume ml"]]
    for old in kept:
        mine = [r for r, n in zip(shapes, names) if n == order[old - 1]]
        table.append([order[old - 1], len(mine), len({r.slice for r in mine}), int(counts[old]), round(counts[old] * ml, 3)])
    total = int(counts[1:].sum())
    table.append(["Total", len(shapes), len({r.slice for r in shapes}), total, round(total * ml, 3)])
    message = "%d segment(s), %.2f ml from %d shapes (segments need MPR open on the series)" % (len(kept), total * ml, len(shapes))
    return rp.Result(table=table, labels=(labels, [order[i - 1] for i in kept]), message=message)


# ------------------------------------------------------------------ 7. Sector statistics


def _ray_radius(p, centre, angles):
    """Distance from `centre` to the outermost crossing of the closed polygon `p` along each direction (radians,
    counter-clockwise on screen from +x); NaN where a ray meets no edge."""
    a = p - centre
    e = np.roll(a, -1, axis=0) - a
    d = np.stack([np.cos(angles), -np.sin(angles)], axis=1)  # y points down on screen
    den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (a[None, :, 0] * e[None, :, 1] - a[None, :, 1] * e[None, :, 0]) / den
        s = (a[None, :, 0] * d[:, None, 1] - a[None, :, 1] * d[:, None, 0]) / den
    hit = (np.abs(den) > 1e-12) & (t > 0) & (s >= -1e-9) & (s <= 1 + 1e-9)
    r = np.where(hit, t, -np.inf).max(axis=1)
    return np.where(np.isfinite(r), r, np.nan)


def _fill_gaps(r, what):
    good = ~np.isnan(r)
    if not good.any():
        raise ValueError("The centre of the inner contour is not inside the %s contour: redraw the contours" % what)
    if good.all():
        return r
    i = np.arange(r.size)
    return np.interp(i, i[good], r[good], period=r.size)


def _contours(polygons, volume):
    """(epicardial, endocardial) of the polygons on a slice, as mm arrays, with the endocardial centroid."""
    shapes = [(_polygon_area_centroid(_mm(r.points, volume)), _mm(r.points, volume)) for r in polygons]
    shapes = [(area, centroid, p) for (area, centroid), p in shapes if area > 0]
    if len(shapes) < 2:
        raise ValueError(
            "Sector statistics needs two closed polygons on the slice on screen (found %d): draw the epicardial "
            "contour and, inside it, the endocardial one" % len(shapes)
        )
    shapes.sort(key=lambda s: s[0])
    epi_area, epi_centroid, epi = shapes[-1]
    inner = shapes[:-1]
    if len(inner) > 1:
        # More than two polygons (sector outlines of an earlier run): only a cavity surrounds the centre of the
        # outer contour; the outlines lie in the wall.
        inner = [s for s in inner if _point_in_polygon(epi_centroid, s[2])]
        if not inner:
            raise ValueError(
                "%d polygons on this slice and none surrounds the centre of the largest: delete the ones that are "
                "not the epicardial and endocardial contours" % len(shapes)
            )
    _, centre, endo = inner[-1]
    if not (_point_in_polygon(centre, endo) and _point_in_polygon(centre, epi)):
        raise ValueError("The smaller polygon must lie inside the larger one: redraw the endocardial contour")
    return epi, endo, centre


@rp.tool("sector_statistics")
def sector_statistics(volume, ctx):
    k = _screen_slice(volume, ctx)
    sectors, layers = int(round(ctx.params["sectors"])), int(round(ctx.params["layers"]))
    reference = float(ctx.params["reference_deg"])
    epi, endo, centre = _contours([r for r in ctx.rois if r.kind == "polygon" and r.slice == k], volume)
    s = volume.numpy()[k]
    ny, nx = s.shape
    spacing = np.array(volume.spacing[:2])

    samples = 720
    grid = np.radians(np.arange(samples) * 360.0 / samples)
    r_endo, r_epi = _fill_gaps(_ray_radius(endo, centre, grid), "endocardial"), _fill_gaps(_ray_radius(epi, centre, grid), "epicardial")

    def radii(deg):
        d = np.asarray(deg, dtype=np.float64) % 360.0
        step = 360.0 / samples
        return np.interp(d, np.arange(samples) * step, r_endo, period=360.0), np.interp(d, np.arange(samples) * step, r_epi, period=360.0)

    ring = _polygon_mask(epi / spacing, ny, nx) & ~_polygon_mask(endo / spacing, ny, nx)
    ys, xs = np.nonzero(ring)
    if not ys.size:
        raise ValueError("No pixel between the two contours: draw them further apart")
    dx, dy = xs * spacing[0] - centre[0], ys * spacing[1] - centre[1]
    # Angle counter-clockwise on screen (y points down) from the reference direction.
    deg = np.degrees(np.arctan2(-dy, dx))
    step = 360.0 / sectors
    sector = np.minimum(((deg - reference) % 360.0 / step).astype(int), sectors - 1)
    inner, outer = radii(deg)
    with np.errstate(divide="ignore", invalid="ignore"):
        depth = (np.hypot(dx, dy) - inner) / (outer - inner)
    layer = np.clip(np.nan_to_num(depth * layers), 0, layers - 1).astype(int)
    values = s[ys, xs]

    unit = volume.unit or ""
    pixel_mm2 = float(spacing[0] * spacing[1])
    table = [["Sector", "Layer", "Mean " + unit, "SD", "Min", "Max", "Area mm2", "Pixels"]]
    means = np.full((layers, sectors), np.nan)
    for i in range(sectors):
        for j in range(layers):
            pick = (sector == i) & (layer == j)
            n, mean, sd, lo, hi, _ = _stats(values[pick])
            if mean is not None:
                means[j, i] = mean
            table.append([i + 1, j + 1, _r(mean), _r(sd), _r(lo), _r(hi), round(int(pick.sum()) * pixel_mm2, 2), int(pick.sum())])
    n, mean, sd, lo, hi, _ = _stats(values)
    table.append(["All", "All", _r(mean), _r(sd), _r(lo), _r(hi), round(ys.size * pixel_mm2, 2), int(ys.size)])

    x = np.arange(1, sectors + 1)
    series = [rp.Series("layer %d" % (j + 1) if layers > 1 else "mean", x, np.nan_to_num(means[j]), kind="bars") for j in range(layers)]
    plots = [rp.Plot("Sector means, image %d" % (k + 1), series, x_label="sector", y_label=unit or "value")]

    rois = []
    if ctx.params["outlines"] >= 0.5:
        arc = max(2, int(math.ceil(step / 5.0))) + 1
        for i in range(sectors):
            a = reference + np.linspace(i * step, (i + 1) * step, arc)
            inner, outer = radii(a)
            direction = np.stack([np.cos(np.radians(a)), -np.sin(np.radians(a))], axis=1)
            for j in range(layers):
                lo_r = inner + (outer - inner) * j / layers
                hi_r = inner + (outer - inner) * (j + 1) / layers
                outline = np.concatenate([centre + direction * lo_r[:, None], (centre + direction * hi_r[:, None])[::-1]])
                rois.append(rp.Roi("polygon", k, _voxels(outline, volume), text="S%d L%d" % (i + 1, j + 1)))
            mid = math.radians(reference + (i + 0.5) * step)
            at = centre + np.array([math.cos(mid), -math.sin(mid)]) * (radii([math.degrees(mid)])[1][0] + 3.0)
            rois.append(rp.Roi("text", k, _voxels([at], volume), text="S%d" % (i + 1)))
    message = "%d sectors × %d layer(s) on image %d, %d pixels in the wall" % (sectors, layers, k + 1, ys.size)
    return rp.Result(table=table, plots=plots, rois=rois, message=message)


# ------------------------------------------------------------------ 8. Count points


@rp.tool("count_points")
def count_points(volume, ctx):
    marks = [r for r in ctx.rois if r.kind in ("probe", "text")]
    if not marks:
        raise ValueError("Nothing to count: mark each item with a probe or a text note (the note's text is its type)")
    line_mm = {}
    for r in ctx.rois:
        if r.kind == "line":
            line_mm[r.slice] = line_mm.get(r.slice, 0.0) + _length_mm(r, volume)

    def type_of(r):
        return (r.text or "").strip() or ("Probe" if r.kind == "probe" else "Note")

    def row(image, name, count, length):
        density = round(count / length, 4) if length else ""
        return [image, name, count, round(length, 2) if length else "", density, round(10.0 * count / length, 3) if length else ""]

    table = [["Image", "Type", "Count", "Line length mm", "Per mm", "Per 10 mm"]]
    totals = {}
    for k in sorted({r.slice for r in marks}):
        here = {}
        for r in marks:
            if r.slice == k:
                here[type_of(r)] = here.get(type_of(r), 0) + 1
        for name in sorted(here):
            table.append(row(k + 1, name, here[name], line_mm.get(k, 0.0)))
            totals[name] = totals.get(name, 0) + here[name]
        if len(here) > 1:
            table.append(row(k + 1, "All types", sum(here.values()), line_mm.get(k, 0.0)))
    length = sum(line_mm.values())
    for name in sorted(totals):
        table.append(row("All", name, totals[name], length))
    table.append(row("All", "All types", len(marks), length))
    names = sorted(totals)
    plots = [rp.Plot("Count by type", [rp.Series("count", np.arange(1, len(names) + 1), [totals[n] for n in names], kind="bars")],
                     x_label="type (table order)", y_label="count")]  # fmt: skip
    density = ", %.3f per mm over %.1f mm of lines" % (len(marks) / length, length) if length else ", no line to give a density"
    return rp.Result(table=table, plots=plots, message="%d marks of %d type(s)%s" % (len(marks), len(totals), density))


# ------------------------------------------------------------------ 9. Grow from seed


@rp.tool("grow_from_seed")
def grow_from_seed(volume, ctx):
    probes = [r for r in ctx.rois if r.kind == "probe"]
    if not probes:
        raise ValueError("No probe in the series: place one inside the structure to grow from")
    here = [r for r in probes if r.slice == ctx.slice]
    seed = (here or probes)[-1]
    nx, ny, nz = volume.dims
    x, y, z = int(round(seed.points[0][0])), int(round(seed.points[0][1])), seed.slice
    if not (0 <= x < nx and 0 <= y < ny and 0 <= z < nz):
        raise ValueError("The probe is outside the image: place it inside the structure")
    a = volume.numpy()
    value = float(a[z, y, x])
    if math.isnan(value):
        raise ValueError("The probe is on a voxel without data: place it inside the structure")
    mode = int(round(ctx.params["mode"]))
    lower, upper = float(ctx.params["lower"]), float(ctx.params["upper"])
    unit = volume.unit or ""
    if mode == 0:
        lo, hi, how = value - lower, value + upper, "seed value − %g … + %g" % (lower, upper)
    elif mode == 1:
        lo, hi, how = lower, upper, "absolute bounds"
        if lo > hi:
            raise ValueError("Lower bound (%g) is above the upper bound (%g): swap them" % (lo, hi))
    else:
        if not 0 < lower <= 100:
            raise ValueError("Mode 2 takes Lower as a percentage of the local maximum (1–100), got %g" % lower)
        half = [max(int(float(ctx.params["search_mm"]) / s / 2.0), 0) for s in volume.spacing]
        box = a[max(z - half[2], 0) : z + half[2] + 1, max(y - half[1], 0) : y + half[1] + 1, max(x - half[0], 0) : x + half[0] + 1]
        hi = float(np.nanmax(box))
        lo, how = hi * lower / 100.0, "%g %% of the maximum within %g mm" % (lower, ctx.params["search_mm"])
    if not lo <= value <= hi:
        raise ValueError(
            "The probe's value (%g) is outside the range %g … %g (%s): move the probe or widen the range" % (value, lo, hi, how)
        )
    ctx.progress(0.2, "thresholding")
    with np.errstate(invalid="ignore"):
        inside = (a >= lo) & (a <= hi)
    regions, _ = ndimage.label(inside)  # default structure: face neighbours, 6-connected
    ctx.progress(0.8, "selecting the region of the probe")
    region = regions == regions[z, y, x]
    n, mean, sd, vmin, vmax, _ = _stats(a[region])
    ml = n * volume.spacing[0] * volume.spacing[1] * volume.spacing[2] / 1000.0
    table = [
        ["Quantity", "Value", "Unit"],
        ["Seed voxel (x, y, image)", "%d, %d, %d" % (x, y, z + 1), ""],
        ["Seed value", round(value, 3), unit],
        ["Range", "%g … %g" % (lo, hi), unit],
        ["Range from", how, ""],
        ["Voxels", n, ""],
        ["Volume", round(ml, 3), "ml"],
        ["Mean", _r(mean), unit],
        ["SD", _r(sd), unit],
        ["Minimum", _r(vmin), unit],
        ["Maximum", _r(vmax), unit],
    ]
    name = "Grown from (%d, %d, %d): %g … %g%s" % (x, y, z + 1, lo, hi, (" " + unit) if unit else "")
    message = "%d voxels, %.2f ml (segment needs MPR open on the series)" % (n, ml)
    return rp.Result(table=table, labels=(region.astype(np.uint8), [name]), message=message)


# ------------------------------------------------------------------ 10. Calcium score


def _agatston(a, region, spacing, min_area_mm2, progress=None):
    """Agatston score, volume (mm³), in-slice lesion count, peak HU and the scored voxels of `a` inside `region`
    (None = everywhere). Slices are labelled in bands so the label array stays small."""
    sx, sy, sz = spacing
    nz = a.shape[0]
    in_plane = np.zeros((3, 3, 3), int)
    in_plane[1] = 1  # 8-connected within a slice, nothing across slices: lesions are per slice
    scored = np.zeros(a.shape, bool)
    score, lesions, peak = 0.0, 0, None
    band = 32
    for z0 in range(0, nz, band):
        block = a[z0 : z0 + band]
        with np.errstate(invalid="ignore"):
            hot = block >= CALCIUM_HU
        if region is not None:
            hot &= region[z0 : z0 + band]
        labels, n = ndimage.label(hot, structure=in_plane)
        if n:
            index = np.arange(1, n + 1)
            pixels = np.bincount(labels.ravel(), minlength=n + 1)[1:]
            peaks = np.asarray(ndimage.maximum(block, labels, index), dtype=np.float64)
            area = pixels * sx * sy
            keep = area >= min_area_mm2 - 1e-9
            weight = np.select([peaks >= 400, peaks >= 300, peaks >= 200], [4, 3, 2], 1)
            score += float((area * weight)[keep].sum()) * sz / REFERENCE_THICKNESS_MM
            lesions += int(keep.sum())
            if keep.any():
                peak = max(peak or -math.inf, float(peaks[keep].max()))
            scored[z0 : z0 + band] = np.concatenate([[False], keep])[labels]
        if progress:
            progress(min(z0 + band, nz) / nz)
    volume_mm3 = float(scored.sum()) * sx * sy * sz
    return score, volume_mm3, lesions, peak, scored


@rp.tool("calcium_score")
def calcium_score(volume, ctx):
    if volume.unit != "HU":
        raise ValueError(
            "Calcium scoring needs a CT in Hounsfield units; this series is in %s: run it on the non-contrast cardiac CT"
            % (volume.unit or "no unit")
        )
    a = volume.numpy()
    min_area = float(ctx.params["min_area_mm2"])
    segments = list(ctx.segments or [])
    table = [["Region", "Agatston score", "Volume mm3", "Lesions (per slice)", "Lesions (3D)", "Peak HU"]]

    def row(name, region, lo, hi):
        score, mm3, lesions, peak, scored = _agatston(
            a, region, volume.spacing, min_area, lambda f: ctx.progress(lo + (hi - lo) * f, name)
        )
        solid = ndimage.label(scored, structure=np.ones((3, 3, 3), int))[1]
        table.append([name, round(score, 1), round(mm3, 1), lesions, solid, _r(peak, 0)])
        return score, mm3

    if segments:
        union = np.zeros(a.shape, bool)
        for i, s in enumerate(segments):
            mask = s.mask()
            union |= mask
            row(s.name, mask, i / (len(segments) + 1), (i + 1) / (len(segments) + 1))
        # The union, not the sum of the rows: a voxel in two overlapping segments is scored once.
        score, mm3 = row("Total (all segments)", union, len(segments) / (len(segments) + 1), 1.0)
        where = "inside %d segment(s)" % len(segments)
    else:
        score, mm3 = row("Whole volume", None, 0.0, 1.0)
        where = "WHOLE VOLUME: bone and everything else ≥ 130 HU is counted. Segment the coronaries (or the heart) first"
    thickness = "slice spacing %.2f mm / 3 mm" % volume.spacing[2]
    message = "Agatston %.1f, volume %.1f mm³, %s; lesions ≥ %g mm², scaled by %s" % (score, mm3, where, min_area, thickness)
    return rp.Result(table=table, message=message)

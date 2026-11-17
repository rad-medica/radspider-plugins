"""Skeletal radiology: automatic and hybrid interactive measurements on 2D skeletal radiographs (or active slice).

Five interactive measurement tools covering the major skeletal radiography domains plus a bone silhouette segmentation:

* ``bone_silhouette`` (segmentation): adaptive global + row-band percentile threshold, hole closing and island filter.
* ``spine`` (tool): spinal midline, endplate tilt profile, automatic Cobb angle, coronal/sagittal plumb balance and
  apical vertebral wedge ratio. Two drawn lines on the slice override the endplates.
* ``lower_limb`` (tool): full-leg tele-radiography (pangoniometry) for right and/or left limb: HKA angle, mechanical
  axis deviation (MAD), mLDFA, MPTA, JLCA, femoral/tibial/total lengths and leg length discrepancy (LLD).
* ``hip_pelvis`` (tool): AP pelvis and hip goniometry: femoral head diameters, pelvic obliquity, Wiberg LCEA, Tönnis
  acetabular index, cervicodiaphyseal neck-shaft angle (CCD) and femoral offset.
* ``bone_morphometry`` (tool): diaphyseal radiogrammetry of a tubular bone: bone length, outer diameter (D), medullary
  diameter (d), combined cortical thickness (CCT), Barnett-Nordin cortical index (%), corticomedullary ratio and
  cross-sectional cortical area.
* ``foot_hand`` (tool): extremity goniometry for Foot AP (HVA, 1-2 IMA), Foot Lateral (Böhler, Gissane, calcaneal
  pitch) and Hand/Wrist AP (2nd metacarpal index MCI, radial inclination).

All geometry is computed in physical mm using ``volume.spacing[:2]``. Research use only: not clinically evaluated.
"""

import math

import numpy as np
from scipy import ndimage

import radspider_plugin as rp

CLOSED = ("polygon", "ellipse")


# ------------------------------------------------------------------ slice, geometry & mask helpers


def _spacing_xy(volume):
    """In-plane pixel spacing (sx, sy) in mm, guarding against non-positive metadata."""
    sx = float(volume.spacing[0]) if volume.spacing and volume.spacing[0] > 0 else 1.0
    sy = float(volume.spacing[1]) if len(volume.spacing) > 1 and volume.spacing[1] > 0 else 1.0
    return sx, sy


def _active_slice(volume, ctx):
    """Returns (k, slice_2d_float64) for the active or control-selected slice."""
    a = volume.numpy()
    nz = a.shape[0]
    default_k = ctx.slice if ctx.slice is not None else nz // 2
    k = int(min(max(round(float(ctx.controls.get("slice", default_k))), 0), max(nz - 1, 0)))
    sl = a[k].astype(np.float64)
    if not np.isfinite(sl).any():
        raise ValueError("Slice %d has no finite pixel values: select a slice with radiographic data" % (k + 1))
    return k, sl


def _should_stamp_rois(ctx):
    """ROIs are added on the initial run and when the user clicks the Stamp ROIs button, not on every slider drag."""
    return ctx.event in (None, "stamp")


def _quantity_header():
    return [rp.tr("Quantity"), rp.tr("Value"), rp.tr("Unit")]


def _side_text(name):
    """The side of a limb ("Right" / "Left", the keys of the results) as a marked text."""
    return rp.tr("Right") if name == "Right" else rp.tr("Left")


def _hip_side_text(name):
    """The side of a hip: its own context, as the word is feminine in Spanish (cadera derecha)."""
    return rp.trc("hip", "Right") if name == "Right" else rp.trc("hip", "Left")


def _r(val, digits=2):
    if val is None or not np.isfinite(val):
        return ""
    return round(float(val), digits)


def _close_2d(mask, radius_mm, sx, sy):
    """Morphological closing of a 2D boolean mask with a physical disc of ``radius_mm`` using Euclidean EDT."""
    if radius_mm <= 0 or not mask.any():
        return mask
    pad_y = int(math.ceil(radius_mm / sy)) + 2
    pad_x = int(math.ceil(radius_mm / sx)) + 2
    crop = np.pad(mask, ((pad_y, pad_y), (pad_x, pad_x)), mode="constant", constant_values=False)
    grown = ndimage.distance_transform_edt(~crop, sampling=(sy, sx)) <= radius_mm
    closed = ndimage.distance_transform_edt(grown, sampling=(sy, sx)) > radius_mm
    return closed[pad_y:-pad_y, pad_x:-pad_x]


def _bone_mask_2d(sl, sx, sy, percentile=72.0, closing_mm=3.0, min_area_mm2=25.0, fill_holes=True):
    """Segments osseous structures on a 2D radiograph combining global and row-band adaptive thresholds."""
    valid = np.isfinite(sl)
    if not valid.any():
        return np.zeros(sl.shape, dtype=bool)
    vals = sl[valid]
    lo, hi = float(np.percentile(vals, 2.0)), float(np.percentile(vals, 99.5))
    if hi <= lo:
        return np.zeros(sl.shape, dtype=bool)
    filled = np.where(valid, sl, lo)
    pct = float(np.clip(percentile, 30.0, 99.0))
    global_t = float(np.percentile(vals, pct))

    # Row-band percentile adapts to craniocaudal attenuation changes (e.g. pelvis vs ankle, thorax vs lumbar).
    row_t = np.nanpercentile(np.where(valid, sl, np.nan), pct, axis=1)
    row_t = np.where(np.isfinite(row_t), row_t, global_t)
    sigma_rows = max(1.0, 15.0 / sy)
    row_t = ndimage.gaussian_filter1d(row_t, sigma=sigma_rows, mode="nearest")
    thresh = 0.65 * global_t + 0.35 * row_t[:, None]

    mask = valid & (filled >= thresh) & (filled > lo + 0.05 * (hi - lo))
    if closing_mm > 0:
        mask = _close_2d(mask, closing_mm, sx, sy)
    if fill_holes:
        mask = ndimage.binary_fill_holes(mask)

    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = np.bincount(lab.ravel())
    min_px = max(1, int(round(min_area_mm2 / (sx * sy))))
    keep = sizes >= min_px
    keep[0] = False
    if not keep.any():
        keep[int(np.argmax(sizes[1:]) + 1)] = True
    return keep[lab]


def _roi_mask_2d(roi, ny, nx):
    """Boolean mask of a closed ROI (polygon or ellipse) on a 2D slice."""
    pts = np.asarray(roi.points, dtype=np.float64).reshape(-1, 2)
    mask = np.zeros((ny, nx), dtype=bool)
    if roi.kind == "ellipse" and len(pts) >= 2:
        (xa, ya), (xb, yb) = pts[0], pts[1]
        cx, cy, rx, ry = 0.5 * (xa + xb), 0.5 * (ya + yb), 0.5 * abs(xb - xa), 0.5 * abs(yb - ya)
        if rx <= 0 or ry <= 0:
            return mask
        ys, xs = np.ogrid[:ny, :nx]
        return ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1.0
    if roi.kind == "polygon" and len(pts) >= 3:
        x0, x1 = max(int(math.floor(pts[:, 0].min())), 0), min(int(math.ceil(pts[:, 0].max())), nx - 1)
        y0, y1 = max(int(math.floor(pts[:, 1].min())), 0), min(int(math.ceil(pts[:, 1].max())), ny - 1)
        if x0 > x1 or y0 > y1:
            return mask
        ys, xs = np.mgrid[y0 : y1 + 1, x0 : x1 + 1].astype(np.float64)
        inside = np.zeros(xs.shape, dtype=bool)
        for (ax, ay), (bx, by) in zip(pts, np.roll(pts, -1, axis=0)):
            if ay == by:
                continue
            crosses = (ay <= ys) != (by <= ys)
            inside ^= crosses & (xs < ax + (ys - ay) * (bx - ax) / (by - ay))
        mask[y0 : y1 + 1, x0 : x1 + 1] = inside
    return mask


def _largest_components(mask, k=1, min_fraction=0.08):
    """Returns up to ``k`` largest connected components of ``mask`` as a list of boolean masks, sorted left-to-right."""
    lab, n = ndimage.label(mask)
    if n == 0:
        return []
    sizes = np.bincount(lab.ravel())
    order = np.argsort(sizes[1:])[::-1] + 1
    top_size = sizes[order[0]]
    picked = []
    for idx in order[:k]:
        if sizes[idx] >= min_fraction * top_size:
            comp = lab == idx
            xs = np.nonzero(comp)[1]
            picked.append((float(xs.mean()), comp))
    picked.sort(key=lambda item: item[0])
    return [comp for _, comp in picked]


def _pca_axis_mm(xs, ys, sx, sy, weights=None):
    """Principal axis in physical mm: returns (cx_px, cy_px, ux_mm, uy_mm, length_mm, width_mm)."""
    pts_mm = np.column_stack([xs * sx, ys * sy]).astype(np.float64)
    if weights is not None:
        w = np.clip(np.asarray(weights, dtype=np.float64), 0.0, None)
        w_sum = float(w.sum())
        if w_sum <= 0:
            w = np.ones(len(xs), dtype=np.float64)
            w_sum = float(len(xs))
        centre_mm = (pts_mm * w[:, None]).sum(axis=0) / w_sum
        centered = pts_mm - centre_mm
        cov = (centered * w[:, None]).T @ centered / w_sum
    else:
        centre_mm = pts_mm.mean(axis=0)
        centered = pts_mm - centre_mm
        cov = (centered.T @ centered) / max(len(xs), 1)
    _, eigvecs = np.linalg.eigh(cov)
    u_mm = eigvecs[:, -1]
    # Convention: point predominantly downwards (+y) or to the right (+x) for consistency.
    if abs(u_mm[1]) >= abs(u_mm[0]):
        if u_mm[1] < 0:
            u_mm = -u_mm
    elif u_mm[0] < 0:
        u_mm = -u_mm
    v_mm = np.array([-u_mm[1], u_mm[0]])
    proj_u = centered @ u_mm
    proj_v = centered @ v_mm
    p_lo, p_hi = float(np.percentile(proj_u, 1.0)), float(np.percentile(proj_u, 99.0))
    w_lo, w_hi = float(np.percentile(proj_v, 5.0)), float(np.percentile(proj_v, 95.0))
    return (
        float(centre_mm[0] / sx),
        float(centre_mm[1] / sy),
        float(u_mm[0]),
        float(u_mm[1]),
        max(0.0, p_hi - p_lo),
        max(0.0, w_hi - w_lo),
    )


def _acute_angle_deg(p0, p1, q0, q1, sx, sy):
    """Acute angle (0-90°) in physical mm between line (p0, p1) and line (q0, q1)."""
    u = np.array([(p1[0] - p0[0]) * sx, (p1[1] - p0[1]) * sy], dtype=np.float64)
    v = np.array([(q1[0] - q0[0]) * sx, (q1[1] - q0[1]) * sy], dtype=np.float64)
    nu, nv = float(np.hypot(*u)), float(np.hypot(*v))
    if nu < 1e-9 or nv < 1e-9:
        return 0.0
    cos = min(1.0, abs(float(u @ v)) / (nu * nv))
    return math.degrees(math.acos(cos))


# ------------------------------------------------------------------ RGB preview drawing helpers


def _canvas_rgb(sl, mask=None):
    """Windowed 8-bit RGB canvas of ``sl`` with an optional subtle cyan outline of ``mask``."""
    valid = np.isfinite(sl)
    vals = sl[valid]
    lo, hi = (float(np.percentile(vals, 1.0)), float(np.percentile(vals, 99.0))) if vals.size else (0.0, 1.0)
    if hi <= lo:
        hi = lo + 1.0
    grey = np.clip((np.nan_to_num(sl, nan=lo) - lo) / (hi - lo), 0.0, 1.0)
    rgb = np.repeat((grey * 235.0).astype(np.uint8)[:, :, None], 3, axis=2)
    if mask is not None and mask.any():
        eroded = ndimage.binary_erosion(mask, iterations=1)
        edge = mask & ~eroded
        rgb[edge] = [70, 180, 220]
    return rgb


def _draw_line(rgb, p0, p1, color, thickness=1):
    """Draws a line segment from p0=(x0, y0) to p1=(x1, y1) onto an RGB uint8 image."""
    ny, nx = rgb.shape[:2]
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    steps = max(2, int(math.hypot(x1 - x0, y1 - y0) * 2.0) + 1)
    xs = np.rint(np.linspace(x0, x1, steps)).astype(int)
    ys = np.rint(np.linspace(y0, y1, steps)).astype(int)
    for dy in range(-thickness, thickness + 1):
        for dx in range(-thickness, thickness + 1):
            yy = np.clip(ys + dy, 0, ny - 1)
            xx = np.clip(xs + dx, 0, nx - 1)
            rgb[yy, xx] = color


def _draw_dot(rgb, pt, color, radius=3):
    """Draws a filled circular marker at pt=(x, y) onto an RGB uint8 image."""
    ny, nx = rgb.shape[:2]
    cx, cy = int(round(pt[0])), int(round(pt[1]))
    y0, y1 = max(0, cy - radius), min(ny - 1, cy + radius)
    x0, x1 = max(0, cx - radius), min(nx - 1, cx + radius)
    if x0 > x1 or y0 > y1:
        return
    ys, xs = np.ogrid[y0 : y1 + 1, x0 : x1 + 1]
    hit = (xs - cx) ** 2 + (ys - cy) ** 2 <= radius**2
    rgb[y0 : y1 + 1, x0 : x1 + 1][hit] = color


def _draw_circle(rgb, center, rx_px, ry_px, color, thickness=1):
    """Draws an ellipse/circle perimeter onto an RGB uint8 image."""
    angles = np.linspace(0.0, 2.0 * math.pi, 180)
    xs = center[0] + rx_px * np.cos(angles)
    ys = center[1] + ry_px * np.sin(angles)
    for i in range(len(angles) - 1):
        _draw_line(rgb, (xs[i], ys[i]), (xs[i + 1], ys[i + 1]), color, thickness=thickness)


# ------------------------------------------------------------------ 0. Segmentation: bone_silhouette


@rp.segmentation("bone_silhouette")
def bone_silhouette(volume, ctx):
    a = volume.numpy()
    if not np.isfinite(a).any():
        raise ValueError("The series has no finite voxel values")
    sx, sy = _spacing_xy(volume)
    pct = float(ctx.params["bone_percentile"])
    closing_mm = float(ctx.params["closing_mm"])
    min_area = float(ctx.params["min_area_mm2"])
    labels = np.zeros(a.shape, dtype=np.uint8)
    nz = a.shape[0]
    for z in range(nz):
        sl = a[z].astype(np.float64)
        if np.isfinite(sl).any():
            labels[z] = _bone_mask_2d(sl, sx, sy, pct, closing_mm, min_area).astype(np.uint8)
        ctx.progress((z + 1) / nz, rp.tr("slice {i} of {n}", i=z + 1, n=nz))
    return labels, ["Skeletal bone"]


# ------------------------------------------------------------------ 1. Tool: spine


def _spine_mask_from_context(volume, ctx, k, sl, sx, sy, pct):
    """Uses an existing spine/vertebra segment on slice k when present, else segments the central spinal column."""
    for s in ctx.segments or []:
        name = (s.name or "").lower()
        if any(w in name for w in ("spine", "vertebra", "columna", "bone", "skeletal")):
            m = s.mask()[k]
            if m.any():
                return m, rp.tr("segment '{name}'", name=s.name)
    _, nx = sl.shape
    raw = _bone_mask_2d(sl, sx, sy, pct, closing_mm=4.0, min_area_mm2=30.0)
    # Focus on the central 70 % corridor where the vertebral column lies on AP/lateral spine radiographs.
    corridor = np.zeros_like(raw)
    x_lo, x_hi = int(0.15 * nx), int(0.85 * nx)
    corridor[:, x_lo:x_hi] = True
    central = raw & corridor
    if central.any():
        raw = central
    return raw, rp.tr("auto threshold (P{percentile})", percentile="%g" % round(pct, 1))


@rp.tool("spine")
def spine(volume, ctx):
    k, sl = _active_slice(volume, ctx)
    ny, nx = sl.shape
    sx, sy = _spacing_xy(volume)
    c = ctx.controls
    pct = float(c.get("bone_percentile", ctx.params["bone_percentile"]))
    smooth_mm = float(c.get("smooth_mm", ctx.params["smooth_mm"]))
    cranial_frac = float(np.clip(c.get("cranial_frac", 0.18), 0.05, 0.48))
    caudal_frac = float(np.clip(c.get("caudal_frac", 0.82), 0.52, 0.95))
    view_choice = c.get("view", "auto")
    use_drawn = bool(c.get("use_drawn_lines", True))

    ctx.progress(0.05, rp.tr("Bone mask"))
    mask, source = _spine_mask_from_context(volume, ctx, k, sl, sx, sy, pct)
    if not mask.any():
        raise ValueError("No spinal bone structure detected on slice %d: lower 'Bone intensity percentile'" % (k + 1))

    ctx.progress(0.4, rp.tr("Measuring"))
    # Extract row-by-row vertebral column centroid and width, weighted by image intensity above the row minimum.
    rows_valid = np.nonzero(mask.any(axis=1))[0]
    if rows_valid.size < 6:
        raise ValueError("Detected bone region is too short (%d rows) to trace a spinal column" % rows_valid.size)
    y_top, y_bot = int(rows_valid[0]), int(rows_valid[-1])
    ys = np.arange(y_top, y_bot + 1, dtype=np.float64)
    cx_raw = np.zeros_like(ys)
    widths_mm = np.zeros_like(ys)
    filled = np.where(np.isfinite(sl), sl, float(np.nanmin(sl)))
    for i, y in enumerate(range(y_top, y_bot + 1)):
        xs = np.nonzero(mask[y])[0]
        if xs.size == 0:
            cx_raw[i] = cx_raw[i - 1] if i > 0 else nx / 2.0
            widths_mm[i] = widths_mm[i - 1] if i > 0 else 30.0
        else:
            w = np.clip(filled[y, xs] - float(filled[y, xs].min()) + 1.0, 1.0, None)
            cx_raw[i] = float((xs * w).sum() / w.sum())
            widths_mm[i] = float((np.percentile(xs, 90) - np.percentile(xs, 10)) * sx)

    sigma_y = max(1.0, smooth_mm / sy)
    cx = ndimage.gaussian_filter1d(cx_raw, sigma=sigma_y, mode="nearest")
    w_smooth_mm = np.clip(ndimage.gaussian_filter1d(widths_mm, sigma=sigma_y, mode="nearest"), 15.0, 80.0)

    # Local midline slope dx_mm / dy_mm -> endplate tilt angle (degrees from horizontal).
    dx_mm = np.gradient(cx * sx)
    dy_mm = np.full_like(dx_mm, sy)
    tilt_deg = np.degrees(np.arctan2(dx_mm, dy_mm))

    # Auto-select cranial and caudal maximally tilted endplates around the search window.
    n_rows = len(ys)
    mid_idx = n_rows // 2
    if "cranial_frac" in c or "caudal_frac" in c:
        idx_sup = int(np.clip(round(cranial_frac * (n_rows - 1)), 0, max(mid_idx - 1, 0)))
        idx_inf = int(np.clip(round(caudal_frac * (n_rows - 1)), min(mid_idx + 1, n_rows - 1), n_rows - 1))
    else:
        lo_sup, hi_sup = max(0, int(0.05 * n_rows)), max(1, int(0.48 * n_rows))
        lo_inf, hi_inf = min(n_rows - 2, int(0.52 * n_rows)), min(n_rows - 1, int(0.95 * n_rows))
        sup_candidates = np.arange(lo_sup, hi_sup + 1)
        inf_candidates = np.arange(lo_inf, hi_inf + 1)
        diffs = np.abs(tilt_deg[sup_candidates, None] - tilt_deg[None, inf_candidates])
        best_flat = int(np.argmax(diffs))
        idx_sup = int(sup_candidates[best_flat // len(inf_candidates)])
        idx_inf = int(inf_candidates[best_flat % len(inf_candidates)])
        cranial_frac = round(idx_sup / max(n_rows - 1, 1), 3)
        caudal_frac = round(idx_inf / max(n_rows - 1, 1), 3)

    def _endplate_segment(idx):
        y0 = float(ys[idx])
        x0 = float(cx[idx])
        half_w = 0.5 * w_smooth_mm[idx]
        ang = math.radians(float(tilt_deg[idx]))
        # Endplate tangent is perpendicular to the local spinal axis: direction (cos(ang), -sin(ang)) in mm.
        dx_px = (half_w * math.cos(ang)) / sx
        dy_px = -(half_w * math.sin(ang)) / sy
        return (x0 - dx_px, y0 - dy_px), (x0 + dx_px, y0 + dy_px), float(tilt_deg[idx])

    drawn_lines = [r for r in ctx.rois if r.kind == "line" and r.slice == k and len(r.points) >= 2]
    if use_drawn and len(drawn_lines) >= 2:
        l1, l2 = drawn_lines[-2], drawn_lines[-1]
        if (l1.points[0][1] + l1.points[1][1]) > (l2.points[0][1] + l2.points[1][1]):
            l1, l2 = l2, l1
        sup_a, sup_b = tuple(l1.points[0]), tuple(l1.points[1])
        inf_a, inf_b = tuple(l2.points[0]), tuple(l2.points[1])
        sup_tilt = math.degrees(math.atan2((sup_b[1] - sup_a[1]) * sy, (sup_b[0] - sup_a[0]) * sx))
        inf_tilt = math.degrees(math.atan2((inf_b[1] - inf_a[1]) * sy, (inf_b[0] - inf_a[0]) * sx))
        source = rp.tr("2 drawn endplate lines + auto midline")
    else:
        sup_a, sup_b, sup_tilt = _endplate_segment(idx_sup)
        inf_a, inf_b, inf_tilt = _endplate_segment(idx_inf)

    cobb_deg = _acute_angle_deg(sup_a, sup_b, inf_a, inf_b, sx, sy)
    supplement_deg = 180.0 - cobb_deg

    # Plumb balance (cranial reference to caudal reference horizontal offset in mm) and apical deviation.
    x_cran, y_cran = float(cx[0]), float(ys[0])
    x_caud, y_caud = float(cx[-1]), float(ys[-1])
    plumb_offset_mm = (x_cran - x_caud) * sx
    chord_x = x_cran + (ys - y_cran) / max(y_caud - y_cran, 1.0) * (x_caud - x_cran)
    dev_mm = (cx - chord_x) * sx
    apex_idx = int(np.argmax(np.abs(dev_mm)))
    apex_x, apex_y = float(cx[apex_idx]), float(ys[apex_idx])
    apex_dev_mm = float(dev_mm[apex_idx])

    # Apical wedge angle and border height ratio across an ~18 mm vertebral body height band around the apex.
    half_vb = max(2, int(round(9.0 / sy)))
    i_up = max(0, apex_idx - half_vb)
    i_dn = min(n_rows - 1, apex_idx + half_vb)
    ua, ub, _ = _endplate_segment(i_up)
    da, db, _ = _endplate_segment(i_dn)
    wedge_deg = _acute_angle_deg(ua, ub, da, db, sx, sy)
    h_left = math.hypot((da[0] - ua[0]) * sx, (da[1] - ua[1]) * sy)
    h_right = math.hypot((db[0] - ub[0]) * sx, (db[1] - ub[1]) * sy)
    wedge_ratio = min(h_left, h_right) / max(h_left, h_right, 1e-6)

    if view_choice == "auto":
        is_sag = abs(plumb_offset_mm) > 25.0 or abs(apex_dev_mm) > 30.0
    else:
        is_sag = view_choice == "sagittal (lateral)"
    inferred_view = rp.tr("sagittal (lateral)") if is_sag else rp.tr("coronal (AP/PA)")

    severities = (
        rp.tr("Normal (< 10°)"),
        rp.tr("Mild (10–25°)"),
        rp.tr("Moderate (25–45°)"),
        rp.tr("Severe (≥ 45°)"),
    )
    severity_index = 0 if cobb_deg < 10.0 else 1 if cobb_deg < 25.0 else 2 if cobb_deg < 45.0 else 3
    severity = severities[severity_index]

    table = [
        _quantity_header(),
        [rp.tr("Image"), k + 1, ""],
        [rp.tr("Detection source"), source, ""],
        [rp.tr("Projection view"), inferred_view, ""],
        [rp.tr("Cobb angle"), _r(cobb_deg, 1), "°"],
        [rp.tr("Supplement"), _r(supplement_deg, 1), "°"],
        [rp.tr("Classification"), severity, ""],
        [rp.tr("Superior endplate tilt"), _r(sup_tilt, 1), "°"],
        [rp.tr("Inferior endplate tilt"), _r(inf_tilt, 1), "°"],
        [rp.tr("Plumb line balance (cranial − caudal)"), _r(plumb_offset_mm, 1), "mm"],
        [rp.tr("Apical lateral deviation"), _r(apex_dev_mm, 1), "mm"],
        [rp.tr("Apical vertebral wedge angle"), _r(wedge_deg, 1), "°"],
        [rp.tr("Apical height ratio (concavity / convexity)"), _r(wedge_ratio, 3), ""],
        [rp.tr("Spinal column length analyzed"), _r((y_bot - y_top) * sy, 1), "mm"],
    ]

    pos_mm = (ys - y_top) * sy
    plots = [
        rp.Plot(
            rp.tr("Spinal midline deviation from cranial-caudal axis"),
            [rp.Series(rp.tr("Deviation (mm)"), pos_mm, dev_mm)],
            x_label=rp.tr("Craniocaudal distance (mm)"),
            y_label=rp.tr("Lateral / sagittal offset (mm)"),
        ),
        rp.Plot(
            rp.tr("Vertebral tilt profile along the spine"),
            [rp.Series(rp.tr("Endplate tilt (°)"), pos_mm, tilt_deg)],
            x_label=rp.tr("Craniocaudal distance (mm)"),
            y_label=rp.tr("Tilt (°)"),
        ),
    ]

    ctx.progress(0.85, rp.tr("Drawing the preview"))
    rgb = _canvas_rgb(sl, mask)
    for i in range(len(ys) - 1):
        _draw_line(rgb, (cx[i], ys[i]), (cx[i + 1], ys[i + 1]), [60, 230, 120], thickness=1)
    _draw_line(rgb, (x_cran, y_cran), (x_cran, y_caud), [120, 180, 255], thickness=1)
    _draw_line(rgb, sup_a, sup_b, [255, 220, 40], thickness=2)
    _draw_line(rgb, inf_a, inf_b, [255, 220, 40], thickness=2)
    _draw_dot(rgb, (apex_x, apex_y), [255, 70, 70], radius=4)
    image = rp.Image(
        rp.tr("Spine morphometry (slice {slice}): Cobb {cobb}°", slice=k + 1, cobb="%.1f" % cobb_deg), nx, ny, rgb
    )

    rois = []
    if _should_stamp_rois(ctx):
        rois = [
            rp.Roi("cobb", k, [sup_a, sup_b, inf_a, inf_b]),
            rp.Roi("line", k, [(x_cran, y_cran), (x_cran, y_caud)]),
            rp.Roi("probe", k, [(apex_x, apex_y)]),
            rp.Roi(
                "text",
                k,
                [(max(4.0, apex_x + 12.0), max(8.0, apex_y))],
                text="Cobb %.1f° | Balance %+.1f mm | Wedge %.2f" % (cobb_deg, plumb_offset_mm, wedge_ratio),
            ),
        ]

    nz = volume.dims[2]
    controls = [
        rp.Slider("slice", rp.tr("Slice"), k, 0, max(nz - 1, 1), step=1),
        rp.Choice(
            "view", rp.tr("View"), [rp.tr("auto"), rp.tr("coronal (AP/PA)"), rp.tr("sagittal (lateral)")], view_choice
        ),
        rp.Slider("bone_percentile", rp.tr("Bone intensity percentile (%)"), pct, 40.0, 98.0, step=1.0),
        rp.Slider("smooth_mm", rp.tr("Midline smoothing (mm)"), smooth_mm, 1.0, 40.0, step=0.5),
        rp.Slider("cranial_frac", rp.tr("Superior endplate level (0–0.48)"), cranial_frac, 0.05, 0.48, step=0.01),
        rp.Slider("caudal_frac", rp.tr("Inferior endplate level (0.52–0.95)"), caudal_frac, 0.52, 0.95, step=0.01),
        rp.Checkbox("use_drawn_lines", rp.tr("Override endplates with 2 drawn lines when present"), use_drawn),
        rp.Button(
            "stamp",
            rp.tr("Stamp ROIs on image"),
            help=rp.tr("Adds the Cobb angle, plumb line and apex marker to the slice"),
        ),
    ]
    # One sentence per class: the class is a translated word, and a marked text cannot be an argument of another.
    spine_args = {"cobb": "%.1f" % cobb_deg, "balance": "%+.1f" % plumb_offset_mm, "ratio": "%.3f" % wedge_ratio}
    msg = (
        rp.tr("Spine: Cobb {cobb}° (Normal (< 10°)), balance {balance} mm, wedge ratio {ratio}", **spine_args),
        rp.tr("Spine: Cobb {cobb}° (Mild (10–25°)), balance {balance} mm, wedge ratio {ratio}", **spine_args),
        rp.tr("Spine: Cobb {cobb}° (Moderate (25–45°)), balance {balance} mm, wedge ratio {ratio}", **spine_args),
        rp.tr("Spine: Cobb {cobb}° (Severe (≥ 45°)), balance {balance} mm, wedge ratio {ratio}", **spine_args),
    )[severity_index]
    return rp.Result(table=table, plots=plots, images=[image], rois=rois, controls=controls, message=msg)


# ------------------------------------------------------------------ 2. Tool: lower_limb


def _alignment_text(alignment):
    """The coronal alignment class of a limb as a marked text."""
    return rp.tr("Varus") if alignment == "Varus" else rp.tr("Valgus") if alignment == "Valgus" else rp.tr("Neutral")


def _analyze_single_limb(sl, limb_mask, is_right_limb, sx, sy, hip_frac, knee_frac, ankle_frac, probes, lines):
    """Computes mechanical alignment landmarks and angles for one lower limb mask."""
    ys_all, xs_all = np.nonzero(limb_mask)
    y_min, y_max = int(ys_all.min()), int(ys_all.max())
    span_y = max(y_max - y_min, 10)
    filled = np.where(np.isfinite(sl), sl, float(np.nanmin(sl)))

    def _row_centroid(y_center, half_band_px):
        y0 = max(y_min, int(round(y_center - half_band_px)))
        y1 = min(y_max, int(round(y_center + half_band_px)))
        sub = limb_mask[y0 : y1 + 1]
        yy, xx = np.nonzero(sub)
        if xx.size == 0:
            return float(xs_all.mean()), float(y_center), 20.0
        yy = yy + y0
        w = np.clip(filled[yy, xx] - float(filled[yy, xx].min()) + 1.0, 1.0, None)
        cx = float((xx * w).sum() / w.sum())
        cy = float((yy * w).sum() / w.sum())
        width_px = float(np.percentile(xx, 92) - np.percentile(xx, 8))
        return cx, cy, max(width_px, 4.0)

    # Auto-refine knee level around the condylar flare maximum in [0.42, 0.62] when knee_frac is at default.
    band_px = max(2, int(round(6.0 / sy)))
    if abs(knee_frac - 0.52) < 1e-3:
        best_w, best_y = -1.0, y_min + 0.52 * span_y
        for frac in np.linspace(0.43, 0.60, 18):
            yc = y_min + frac * span_y
            _, _, w_px = _row_centroid(yc, band_px)
            if w_px > best_w:
                best_w, best_y = w_px, yc
        ky_auto = best_y
    else:
        ky_auto = y_min + knee_frac * span_y

    hx, hy, hw_px = _row_centroid(y_min + hip_frac * span_y, max(3, int(round(10.0 / sy))))
    kx, ky, kw_px = _row_centroid(ky_auto, band_px)
    ax, ay, _ = _row_centroid(y_min + ankle_frac * span_y, max(2, int(round(8.0 / sy))))

    # Hybrid override: 3 probes on this limb's side override (hip, knee, ankle) in cranial-to-caudal order.
    if len(probes) >= 3:
        pts_sorted = sorted([r.points[0] for r in probes], key=lambda p: p[1])
        (hx, hy), (kx, ky), (ax, ay) = pts_sorted[0], pts_sorted[1], pts_sorted[-1]

    # Distal femoral condylar line and proximal tibial plateau line around the knee center.
    offset_y = max(3.0, 8.0 / sy)
    fx0, fy0 = kx - 0.45 * kw_px, ky - offset_y
    fx1, fy1 = kx + 0.45 * kw_px, ky - offset_y
    tx0, ty0 = kx - 0.42 * kw_px, ky + offset_y
    tx1, ty1 = kx + 0.42 * kw_px, ky + offset_y

    # Fit lower edge of femoral condyles and upper edge of tibial plateau from the bone silhouette when available.
    for sign, is_fem in ((-1, True), (1, False)):
        y_band0 = max(y_min, int(round(ky + sign * 2.5 * offset_y)))
        y_band1 = min(y_max, int(round(ky + sign * 0.4 * offset_y)))
        if y_band0 > y_band1:
            y_band0, y_band1 = y_band1, y_band0
        sub = limb_mask[y_band0 : y_band1 + 1]
        cols = np.nonzero(sub.any(axis=0))[0]
        if cols.size >= 6:
            c_lo, c_hi = int(np.percentile(cols, 15)), int(np.percentile(cols, 85))
            xs_fit, ys_fit = [], []
            for col in range(c_lo, c_hi + 1):
                r_hits = np.nonzero(sub[:, col])[0]
                if r_hits.size:
                    xs_fit.append(float(col))
                    ys_fit.append(float(y_band0 + (r_hits[-1] if is_fem else r_hits[0])))
            if len(xs_fit) >= 4:
                slope, intercept = np.polyfit(np.asarray(xs_fit), np.asarray(ys_fit), 1)
                slope = float(np.clip(slope, -0.35, 0.35))
                if is_fem:
                    fx0, fx1 = float(c_lo), float(c_hi)
                    fy0, fy1 = intercept + slope * fx0, intercept + slope * fx1
                else:
                    tx0, tx1 = float(c_lo), float(c_hi)
                    ty0, ty1 = intercept + slope * tx0, intercept + slope * tx1

    if len(lines) >= 2:
        l_sorted = sorted(lines[-2:], key=lambda r: 0.5 * (r.points[0][1] + r.points[1][1]))
        (fx0, fy0), (fx1, fy1) = l_sorted[0].points[0], l_sorted[0].points[1]
        (tx0, ty0), (tx1, ty1) = l_sorted[1].points[0], l_sorted[1].points[1]

    # Geometry in physical mm.
    h_mm = np.array([hx * sx, hy * sy])
    k_mm = np.array([kx * sx, ky * sy])
    a_mm = np.array([ax * sx, ay * sy])
    fem_vec = k_mm - h_mm
    tib_vec = a_mm - k_mm
    limb_vec = a_mm - h_mm
    fem_len = float(np.hypot(*fem_vec))
    tib_len = float(np.hypot(*tib_vec))
    total_len = float(np.hypot(*limb_vec))

    # Signed angle between femoral and tibial mechanical vectors; medial deviation = varus, lateral = valgus.
    cross_ft = float(fem_vec[0] * tib_vec[1] - fem_vec[1] * tib_vec[0])
    dot_ft = float(fem_vec @ tib_vec)
    dev_deg = math.degrees(math.atan2(cross_ft, max(dot_ft, 1e-9)))
    # For the right limb (left side of radiographic image, smaller x), knee shifted laterally (-x) gives varus.
    varus_deg = -dev_deg if is_right_limb else dev_deg
    hka_deg = 180.0 - varus_deg

    # Mechanical Axis Deviation (MAD): perpendicular distance from knee center to Hip-Ankle line.
    if total_len > 1e-6:
        # Signed distance: positive = medial, negative = lateral.
        u_ha = limb_vec / total_len
        n_medial = np.array([u_ha[1], -u_ha[0]]) if is_right_limb else np.array([-u_ha[1], u_ha[0]])
        mad_signed_mm = float((k_mm - h_mm) @ n_medial)
    else:
        mad_signed_mm = 0.0
    mad_mm = abs(mad_signed_mm)

    # Joint angles mLDFA, MPTA and JLCA.
    if fx1 < fx0:
        fx0, fy0, fx1, fy1 = fx1, fy1, fx0, fy0
    if tx1 < tx0:
        tx0, ty0, tx1, ty1 = tx1, ty1, tx0, ty0
    f_line = np.array([(fx1 - fx0) * sx, (fy1 - fy0) * sy])
    t_line = np.array([(tx1 - tx0) * sx, (ty1 - ty0) * sy])
    f_lat_dir = -f_line if is_right_limb else f_line
    t_med_dir = t_line if is_right_limb else -t_line
    fem_up = -fem_vec
    tib_dn = tib_vec

    def _vec_angle(u, v):
        nu, nv = float(np.hypot(*u)), float(np.hypot(*v))
        if nu < 1e-9 or nv < 1e-9:
            return 90.0
        return math.degrees(math.acos(np.clip(float(u @ v) / (nu * nv), -1.0, 1.0)))

    mldfa_deg = _vec_angle(fem_up, f_lat_dir)
    mpta_deg = _vec_angle(tib_dn, t_med_dir)
    jlca_deg = _acute_angle_deg((fx0, fy0), (fx1, fy1), (tx0, ty0), (tx1, ty1), sx, sy)
    alignment = "Varus" if varus_deg > 1.5 else "Valgus" if varus_deg < -1.5 else "Neutral"  # the key of _alignment_text

    return {
        "hip": (hx, hy),
        "knee": (kx, ky),
        "ankle": (ax, ay),
        "fem_line": ((fx0, fy0), (fx1, fy1)),
        "tib_line": ((tx0, ty0), (tx1, ty1)),
        "hip_radius_px": max(6.0, 0.45 * hw_px),
        "fem_len_mm": fem_len,
        "tib_len_mm": tib_len,
        "total_len_mm": total_len,
        "hka_deg": hka_deg,
        "varus_deg": varus_deg,
        "alignment": alignment,
        "mad_mm": mad_mm,
        "mad_dir": "medial" if mad_signed_mm >= 0 else "lateral",
        "mldfa_deg": mldfa_deg,
        "mpta_deg": mpta_deg,
        "jlca_deg": jlca_deg,
    }


def _limb_message(names, results):
    """The status line of the lower-limb tool: one literal sentence per side set and alignment class (a marked text
    cannot be an argument of another, so the class word cannot be one)."""
    args = {}
    for key, name in (("right", "Right"), ("left", "Left")):
        if name in results:
            args[key + "_hka"] = "%.1f" % results[name]["hka_deg"]
            args[key + "_mad"] = "%.1f" % results[name]["mad_mm"]
    if names == ["Right"]:
        return {
            "Varus": rp.tr("Lower limb: Right HKA {right_hka}° (Varus), MAD {right_mad} mm", **args),
            "Valgus": rp.tr("Lower limb: Right HKA {right_hka}° (Valgus), MAD {right_mad} mm", **args),
            "Neutral": rp.tr("Lower limb: Right HKA {right_hka}° (Neutral), MAD {right_mad} mm", **args),
        }[results["Right"]["alignment"]]
    if names == ["Left"]:
        return {
            "Varus": rp.tr("Lower limb: Left HKA {left_hka}° (Varus), MAD {left_mad} mm", **args),
            "Valgus": rp.tr("Lower limb: Left HKA {left_hka}° (Valgus), MAD {left_mad} mm", **args),
            "Neutral": rp.tr("Lower limb: Left HKA {left_hka}° (Neutral), MAD {left_mad} mm", **args),
        }[results["Left"]["alignment"]]
    return {
        ("Varus", "Varus"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Varus), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Varus), MAD {left_mad} mm",
            **args,
        ),
        ("Varus", "Valgus"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Varus), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Valgus), MAD {left_mad} mm",
            **args,
        ),
        ("Varus", "Neutral"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Varus), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Neutral), MAD {left_mad} mm",
            **args,
        ),
        ("Valgus", "Varus"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Valgus), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Varus), MAD {left_mad} mm",
            **args,
        ),
        ("Valgus", "Valgus"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Valgus), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Valgus), MAD {left_mad} mm",
            **args,
        ),
        ("Valgus", "Neutral"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Valgus), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Neutral), MAD {left_mad} mm",
            **args,
        ),
        ("Neutral", "Varus"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Neutral), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Varus), MAD {left_mad} mm",
            **args,
        ),
        ("Neutral", "Valgus"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Neutral), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Valgus), MAD {left_mad} mm",
            **args,
        ),
        ("Neutral", "Neutral"): rp.tr(
            "Lower limb: Right HKA {right_hka}° (Neutral), MAD {right_mad} mm; "
            "Left HKA {left_hka}° (Neutral), MAD {left_mad} mm",
            **args,
        ),
    }[(results["Right"]["alignment"], results["Left"]["alignment"])]


@rp.tool("lower_limb")
def lower_limb(volume, ctx):
    k, sl = _active_slice(volume, ctx)
    ny, nx = sl.shape
    sx, sy = _spacing_xy(volume)
    c = ctx.controls
    pct = float(c.get("bone_percentile", ctx.params["bone_percentile"]))
    closing_mm = float(c.get("closing_mm", ctx.params["closing_mm"]))
    side_choice = c.get("side", "both")
    hip_frac = float(np.clip(c.get("hip_y_frac", 0.07), 0.02, 0.25))
    knee_frac = float(np.clip(c.get("knee_y_frac", 0.52), 0.35, 0.70))
    ankle_frac = float(np.clip(c.get("ankle_y_frac", 0.93), 0.75, 0.98))

    ctx.progress(0.05, rp.tr("Bone mask"))
    mask = _bone_mask_2d(sl, sx, sy, pct, closing_mm=closing_mm, min_area_mm2=40.0)
    if not mask.any():
        raise ValueError(
            "No lower-limb bone silhouette detected on slice %d: lower 'Bone intensity percentile'" % (k + 1)
        )

    # Split into right (image left, x < mid) and left (image right, x >= mid) limbs when two limbs are present.
    comps = _largest_components(mask, k=2, min_fraction=0.20)
    limbs = []
    if len(comps) == 2 and side_choice == "both":
        limbs = [("Right", comps[0], True), ("Left", comps[1], False)]
    elif len(comps) == 2 and side_choice == "right":
        limbs = [("Right", comps[0], True)]
    elif len(comps) == 2 and side_choice == "left":
        limbs = [("Left", comps[1], False)]
    else:
        comp = comps[0]
        mean_x = float(np.nonzero(comp)[1].mean())
        is_right = mean_x <= 0.5 * nx if side_choice == "both" else (side_choice == "right")
        limbs = [("Right" if is_right else "Left", comp, is_right)]

    probes_here = [r for r in ctx.rois if r.kind == "probe" and r.slice == k and r.points]
    lines_here = [r for r in ctx.rois if r.kind == "line" and r.slice == k and len(r.points) >= 2]

    results = {}
    for i, (name, lmask, is_right) in enumerate(limbs):
        ctx.progress(0.35 + 0.45 * i / len(limbs), rp.tr("Measuring"))
        if len(limbs) == 2:
            l_probes = [r for r in probes_here if (r.points[0][0] < 0.5 * nx) == is_right]
            l_lines = [r for r in lines_here if (0.5 * (r.points[0][0] + r.points[1][0]) < 0.5 * nx) == is_right]
        else:
            l_probes, l_lines = probes_here, lines_here
        results[name] = _analyze_single_limb(
            sl, lmask, is_right, sx, sy, hip_frac, knee_frac, ankle_frac, l_probes, l_lines
        )

    names = [n for n, _, _ in limbs]
    table = [[rp.tr("Measurement"), *[_side_text(n) for n in names], rp.tr("Unit")]]

    def _mad_text(r):
        mad = str(_r(r["mad_mm"], 1))
        return rp.tr("{mad} (medial)", mad=mad) if r["mad_dir"] == "medial" else rp.tr("{mad} (lateral)", mad=mad)

    rows_spec = [
        (rp.tr("HKA mechanical angle"), lambda r: _r(r["hka_deg"], 1), "°"),
        (rp.tr("Coronal deviation (+varus / −valgus)"), lambda r: _r(r["varus_deg"], 1), "°"),
        (rp.tr("Alignment classification"), lambda r: _alignment_text(r["alignment"]), ""),
        (rp.tr("Mechanical axis deviation (MAD)"), _mad_text, "mm"),
        (rp.tr("mLDFA (lateral distal femoral angle)"), lambda r: _r(r["mldfa_deg"], 1), "°"),
        (rp.tr("MPTA (medial proximal tibial angle)"), lambda r: _r(r["mpta_deg"], 1), "°"),
        (rp.tr("JLCA (joint line convergence angle)"), lambda r: _r(r["jlca_deg"], 1), "°"),
        (rp.tr("Femoral mechanical length"), lambda r: _r(r["fem_len_mm"], 1), "mm"),
        (rp.tr("Tibial mechanical length"), lambda r: _r(r["tib_len_mm"], 1), "mm"),
        (rp.tr("Total limb mechanical length"), lambda r: _r(r["total_len_mm"], 1), "mm"),
    ]
    for title, fn, unit in rows_spec:
        table.append([title, *[fn(results[n]) for n in names], unit])
    if len(names) == 2:
        lld = results["Right"]["total_len_mm"] - results["Left"]["total_len_mm"]
        longer = rp.tr("Right longer") if lld > 0 else rp.tr("Left longer") if lld < 0 else rp.tr("Equal")
        table.append([rp.tr("Leg length discrepancy (LLD)"), _r(abs(lld), 1), longer, "mm"])

    ctx.progress(0.85, rp.tr("Drawing the preview"))
    rgb = _canvas_rgb(sl, mask)
    rois = []
    for name in names:
        r = results[name]
        hip, knee, ankle = r["hip"], r["knee"], r["ankle"]
        f0, f1 = r["fem_line"]
        t0, t1 = r["tib_line"]
        _draw_line(rgb, hip, ankle, [90, 180, 255], thickness=1)
        _draw_line(rgb, hip, knee, [50, 235, 120], thickness=2)
        _draw_line(rgb, knee, ankle, [50, 235, 120], thickness=2)
        _draw_line(rgb, f0, f1, [255, 210, 40], thickness=2)
        _draw_line(rgb, t0, t1, [255, 140, 40], thickness=2)
        _draw_circle(rgb, hip, r["hip_radius_px"], r["hip_radius_px"], [255, 90, 90], thickness=1)
        for pt in (hip, knee, ankle):
            _draw_dot(rgb, pt, [255, 70, 70], radius=4)
        if _should_stamp_rois(ctx):
            rois += [
                rp.Roi("line", k, [hip, knee]),
                rp.Roi("line", k, [knee, ankle]),
                rp.Roi("line", k, [hip, ankle]),
                rp.Roi("line", k, [f0, f1]),
                rp.Roi("line", k, [t0, t1]),
                rp.Roi("probe", k, [hip]),
                rp.Roi("probe", k, [knee]),
                rp.Roi("probe", k, [ankle]),
                rp.Roi(
                    "text",
                    k,
                    [(knee[0] + 10.0, knee[1])],
                    text="%s: HKA %.1f° (%s) | MAD %.1f mm | L %.0f mm"
                    % (name, r["hka_deg"], r["alignment"], r["mad_mm"], r["total_len_mm"]),
                ),
            ]

    x_idx = np.arange(1, 4, dtype=np.float64)
    series = [
        rp.Series(
            _side_text(n),
            x_idx + (-0.15 if i == 0 and len(names) == 2 else 0.15 if len(names) == 2 else 0.0),
            [results[n]["fem_len_mm"], results[n]["tib_len_mm"], results[n]["total_len_mm"]],
            kind="bars",
        )
        for i, n in enumerate(names)
    ]
    plots = [
        rp.Plot(
            rp.tr("Segmental lower-limb lengths (1 Femur, 2 Tibia, 3 Total)"),
            series,
            x_label=rp.tr("Segment"),
            y_label=rp.tr("Length (mm)"),
        )
    ]
    image = rp.Image(rp.tr("Lower limb alignment (slice {slice})", slice=k + 1), nx, ny, rgb)
    nz = volume.dims[2]
    controls = [
        rp.Slider("slice", rp.tr("Slice"), k, 0, max(nz - 1, 1), step=1),
        rp.Choice("side", rp.tr("Analyzed limb"), [rp.tr("both"), rp.tr("right"), rp.tr("left")], side_choice),
        rp.Slider("bone_percentile", rp.tr("Bone intensity percentile (%)"), pct, 40.0, 98.0, step=1.0),
        rp.Slider("closing_mm", rp.tr("Close bone contour (mm)"), closing_mm, 0.0, 20.0, step=0.5),
        rp.Slider("hip_y_frac", rp.tr("Hip center level (0.02–0.25)"), hip_frac, 0.02, 0.25, step=0.01),
        rp.Slider("knee_y_frac", rp.tr("Knee center level (0.35–0.70)"), knee_frac, 0.35, 0.70, step=0.01),
        rp.Slider("ankle_y_frac", rp.tr("Ankle center level (0.75–0.98)"), ankle_frac, 0.75, 0.98, step=0.01),
        rp.Button(
            "stamp",
            rp.tr("Stamp ROIs on image"),
            help=rp.tr("Adds mechanical axes, joint lines and landmarks to the slice"),
        ),
    ]
    message = _limb_message(names, results)
    return rp.Result(table=table, plots=plots, images=[image], rois=rois, controls=controls, message=message)


# ------------------------------------------------------------------ 3. Tool: hip_pelvis


def _detect_hip_side(sl, mask, is_right, sx, sy, fixed_radius_mm, neck_frac, shaft_frac, ellipses, probes):
    """Detects femoral head, acetabular sourcil, neck axis and shaft axis for one side of the pelvis."""
    ny, nx = sl.shape
    x_lo, x_hi = (0, nx // 2) if is_right else (nx // 2, nx)
    side_mask = np.zeros_like(mask)
    side_mask[:, x_lo:x_hi] = mask[:, x_lo:x_hi]
    if not side_mask.any():
        side_mask = mask

    ys, xs = np.nonzero(side_mask)
    y_min, y_max = int(ys.min()), int(ys.max())
    x_min, x_max = int(xs.min()), int(xs.max())
    span_y = max(y_max - y_min, 10)
    span_x = max(x_max - x_min, 10)
    filled = np.where(np.isfinite(sl), sl, float(np.nanmin(sl)))

    # Default femoral head zone lies in the middle-upper pelvic region; EDT peak inside the corridor locates the dome.
    hy_lo = max(0, int(round(y_min + 0.22 * span_y)))
    hy_hi = min(ny - 1, int(round(y_min + 0.62 * span_y)))
    if is_right:
        hx_lo, hx_hi = max(0, int(round(x_min + 0.15 * span_x))), min(nx - 1, int(round(x_min + 0.80 * span_x)))
    else:
        hx_lo, hx_hi = max(0, int(round(x_min + 0.20 * span_x))), min(nx - 1, int(round(x_min + 0.85 * span_x)))

    edt = ndimage.distance_transform_edt(side_mask, sampling=(sy, sx))
    zone = np.zeros_like(side_mask)
    zone[hy_lo : hy_hi + 1, hx_lo : hx_hi + 1] = side_mask[hy_lo : hy_hi + 1, hx_lo : hx_hi + 1]
    if not zone.any():
        zone = side_mask
    score = edt * (filled - float(filled[zone].min()) + 1.0) * zone
    peak_flat = int(np.argmax(score))
    hy, hx = divmod(peak_flat, nx)
    hx, hy = float(hx), float(hy)
    r_mm = float(fixed_radius_mm) if fixed_radius_mm > 0 else float(np.clip(edt[int(hy), int(hx)], 14.0, 32.0))

    # Hybrid override: user-drawn ellipse or probe on this side of the slice sets the femoral head center and radius.
    if ellipses:
        (xa, ya), (xb, yb) = ellipses[-1].points[0], ellipses[-1].points[1]
        hx, hy = 0.5 * (xa + xb), 0.5 * (ya + yb)
        r_mm = 0.25 * (abs(xb - xa) * sx + abs(yb - ya) * sy)
    elif probes:
        hx, hy = float(probes[-1].points[0][0]), float(probes[-1].points[0][1])

    rx_px, ry_px = max(4.0, r_mm / sx), max(4.0, r_mm / sy)

    # Inferior teardrop / pelvic reference landmark (medial and slightly inferior to femoral head center).
    med_sign = 1.0 if is_right else -1.0  # towards midline (+x for right hip, -x for left hip)
    lat_sign = -med_sign
    td_x = float(np.clip(hx + med_sign * 1.15 * rx_px, 0, nx - 1))
    td_y = float(np.clip(hy + 0.85 * ry_px, 0, ny - 1))

    # Acetabular sourcil medial and lateral landmarks above the femoral head dome.
    med_sourcil = (
        float(np.clip(hx + med_sign * 0.45 * rx_px, 0, nx - 1)),
        float(np.clip(hy - 0.95 * ry_px, 0, ny - 1)),
    )
    # Refine lateral acetabular rim from bone contour just superior-lateral to the head.
    lat_angle_deg = 28.0
    rim_y_lo = max(0, int(round(hy - 1.35 * ry_px)))
    rim_y_hi = max(rim_y_lo + 1, int(round(hy - 0.55 * ry_px)))
    side_cols = np.nonzero(side_mask[rim_y_lo : rim_y_hi + 1])[1]
    if side_cols.size:
        lat_x = float(np.percentile(side_cols, 12 if is_right else 88))
        # Clamp lateral rim within anatomically plausible [0.25*r, 1.25*r] lateral to head center.
        dx_lat = (lat_x - hx) * lat_sign
        dx_lat = float(np.clip(dx_lat, 0.25 * rx_px, 1.25 * rx_px))
        lat_x = hx + lat_sign * dx_lat
    else:
        lat_x = hx + lat_sign * (rx_px * math.sin(math.radians(lat_angle_deg)))
    lat_y = float(np.clip(hy - 1.05 * ry_px, 0, ny - 1))
    lat_sourcil = (lat_x, lat_y)

    # Proximal femoral shaft axis in the lower part of the mask (below the femoral head).
    shaft_y0 = min(ny - 2, max(int(round(hy + 1.4 * ry_px)), int(round(y_min + shaft_frac * span_y))))
    shaft_y1 = y_max
    shaft_sub = side_mask[shaft_y0 : shaft_y1 + 1]
    sy_pts, sx_pts = np.nonzero(shaft_sub)
    if sx_pts.size >= 12:
        sy_pts = sy_pts + shaft_y0
        # Keep the lateral shaft cortex/medulla region when the ischium is also in the mask.
        lat_cut = np.percentile(sx_pts, 65 if is_right else 35)
        pick = (sx_pts <= lat_cut) if is_right else (sx_pts >= lat_cut)
        if pick.sum() >= 8:
            sx_pts, sy_pts = sx_pts[pick], sy_pts[pick]
        scx, scy, sux_mm, suy_mm, _, _ = _pca_axis_mm(sx_pts, sy_pts, sx, sy)
    else:
        scx = float(np.clip(hx + lat_sign * 1.6 * rx_px, 0, nx - 1))
        scy = float(np.clip(hy + 2.8 * ry_px, 0, ny - 1))
        sux_mm, suy_mm = 0.05 * lat_sign, 0.998

    # Neck center lies between the head center and the intertrochanteric shaft axis.
    neck_y = float(np.clip(hy + (0.6 + 0.8 * neck_frac) * ry_px, 0, ny - 1))
    neck_x = float(np.clip(0.55 * hx + 0.45 * scx, 0, nx - 1))
    shaft_top = (scx - (1.8 * r_mm * sux_mm) / sx, scy - (1.8 * r_mm * suy_mm) / sy)
    shaft_bot = (scx + (1.8 * r_mm * sux_mm) / sx, scy + (1.8 * r_mm * suy_mm) / sy)
    neck_end = (hx + 1.85 * (neck_x - hx), hy + 1.85 * (neck_y - hy))

    # Neck-shaft CCD angle (obtuse, 90-180°): 180° minus acute angle between neck vector and shaft vector.
    u_neck = np.array([(neck_end[0] - hx) * sx, (neck_end[1] - hy) * sy])
    u_shaft = np.array([sux_mm, suy_mm])
    if u_shaft[1] < 0:
        u_shaft = -u_shaft
    if u_neck[1] < 0:
        u_neck = -u_neck
    cos_ns = float(u_neck @ u_shaft) / max(float(np.hypot(*u_neck) * np.hypot(*u_shaft)), 1e-9)
    acute_ns = math.degrees(math.acos(np.clip(abs(cos_ns), 0.0, 1.0)))
    ccd_deg = 180.0 - acute_ns

    # Femoral offset: perpendicular distance in mm from head center to the shaft axis line.
    vec_hs = np.array([(hx - scx) * sx, (hy - scy) * sy])
    u_s_unit = u_shaft / max(float(np.hypot(*u_shaft)), 1e-9)
    fem_offset_mm = abs(float(vec_hs[0] * u_s_unit[1] - vec_hs[1] * u_s_unit[0]))

    return {
        "head": (hx, hy),
        "r_mm": r_mm,
        "rx_px": rx_px,
        "ry_px": ry_px,
        "teardrop": (td_x, td_y),
        "med_sourcil": med_sourcil,
        "lat_sourcil": lat_sourcil,
        "neck_line": ((hx, hy), neck_end),
        "shaft_line": (shaft_top, shaft_bot),
        "ccd_deg": ccd_deg,
        "fem_offset_mm": fem_offset_mm,
    }


@rp.tool("hip_pelvis")
def hip_pelvis(volume, ctx):
    k, sl = _active_slice(volume, ctx)
    ny, nx = sl.shape
    sx, sy = _spacing_xy(volume)
    c = ctx.controls
    pct = float(c.get("bone_percentile", ctx.params["bone_percentile"]))
    head_r_param = float(c.get("head_radius_mm", ctx.params["head_radius_mm"]))
    neck_frac = float(np.clip(c.get("neck_level_frac", 0.50), 0.20, 0.85))
    shaft_frac = float(np.clip(c.get("shaft_level_frac", 0.55), 0.30, 0.85))
    side_choice = c.get("side", "both")

    ctx.progress(0.05, rp.tr("Bone mask"))
    mask = _bone_mask_2d(sl, sx, sy, pct, closing_mm=3.5, min_area_mm2=40.0)
    if not mask.any():
        raise ValueError(
            "No pelvic or hip bone structure detected on slice %d: lower 'Bone intensity percentile'" % (k + 1)
        )

    ellipses_here = [r for r in ctx.rois if r.kind == "ellipse" and r.slice == k and len(r.points) >= 2]
    probes_here = [r for r in ctx.rois if r.kind == "probe" and r.slice == k and r.points]

    sides_to_run = []
    if side_choice in ("both", "right") and mask[:, : nx // 2].any():
        sides_to_run.append(("Right", True))
    if side_choice in ("both", "left") and mask[:, nx // 2 :].any():
        sides_to_run.append(("Left", False))
    if not sides_to_run:
        sides_to_run.append(("Right" if side_choice != "left" else "Left", side_choice != "left"))

    hips = {}
    for i, (name, is_right) in enumerate(sides_to_run):
        ctx.progress(0.35 + 0.45 * i / len(sides_to_run), rp.tr("Measuring"))
        if len(sides_to_run) == 2:
            e_side = [r for r in ellipses_here if (0.5 * (r.points[0][0] + r.points[1][0]) < 0.5 * nx) == is_right]
            p_side = [r for r in probes_here if (r.points[0][0] < 0.5 * nx) == is_right]
        else:
            e_side, p_side = ellipses_here, probes_here
        hips[name] = _detect_hip_side(sl, mask, is_right, sx, sy, head_r_param, neck_frac, shaft_frac, e_side, p_side)

    # Pelvic horizontal reference line (between right and left teardrops when bilateral, else image horizontal).
    if "Right" in hips and "Left" in hips:
        p_left_pt = hips["Right"]["teardrop"]
        p_right_pt = hips["Left"]["teardrop"]
        dx_p = (p_right_pt[0] - p_left_pt[0]) * sx
        dy_p = (p_right_pt[1] - p_left_pt[1]) * sy
        pelvic_tilt_deg = math.degrees(math.atan2(dy_p, max(abs(dx_p), 1e-6)))
        pelvic_step_mm = abs(dy_p)
    else:
        only = next(iter(hips.values()))
        td = only["teardrop"]
        p_left_pt = (max(0.0, td[0] - 40.0 / sx), td[1])
        p_right_pt = (min(float(nx - 1), td[0] + 40.0 / sx), td[1])
        pelvic_tilt_deg = 0.0
        pelvic_step_mm = 0.0

    pelv_rad = math.radians(pelvic_tilt_deg)
    # Unit upward vertical perpendicular to pelvic line in mm: (-sin(pelv), -cos(pelv)).
    v_up_mm = np.array([math.sin(pelv_rad), -math.cos(pelv_rad)])

    for name, h in hips.items():
        is_right = name == "Right"
        lat_sign = -1.0 if is_right else 1.0
        hx, hy = h["head"]
        lat_x, lat_y = h["lat_sourcil"]
        med_x, med_y = h["med_sourcil"]

        # Wiberg LCEA: angle between upward pelvic perpendicular through head center and ray to lateral sourcil.
        ray_lat = np.array([(lat_x - hx) * sx, (lat_y - hy) * sy])
        cos_ce = float(ray_lat @ v_up_mm) / max(float(np.hypot(*ray_lat)), 1e-9)
        lcea = math.degrees(math.acos(np.clip(cos_ce, -1.0, 1.0)))
        if (lat_x - hx) * lat_sign < 0:
            lcea = -lcea
        h["lcea_deg"] = lcea

        # Tönnis angle: inclination of sourcil line (medial -> lateral) relative to pelvic reference line.
        sourcil_vec = np.array([(lat_x - med_x) * sx * lat_sign, (med_y - lat_y) * sy])
        tonnis_deg = math.degrees(math.atan2(sourcil_vec[1], max(sourcil_vec[0], 1e-6))) - (
            pelvic_tilt_deg if is_right else -pelvic_tilt_deg
        )
        h["tonnis_deg"] = tonnis_deg

    names = [n for n, _ in sides_to_run]
    table = [
        [rp.tr("Measurement"), *[_hip_side_text(n) for n in names], rp.tr("Unit")],
        [rp.tr("Femoral head diameter"), *[_r(2.0 * hips[n]["r_mm"], 1) for n in names], "mm"],
        [rp.tr("Wiberg LCEA (lateral center-edge angle)"), *[_r(hips[n]["lcea_deg"], 1) for n in names], "°"],
        [rp.tr("Tönnis angle (acetabular index)"), *[_r(hips[n]["tonnis_deg"], 1) for n in names], "°"],
        [rp.tr("Neck-shaft CCD angle"), *[_r(hips[n]["ccd_deg"], 1) for n in names], "°"],
        [rp.tr("Femoral offset"), *[_r(hips[n]["fem_offset_mm"], 1) for n in names], "mm"],
        [rp.tr("Pelvic obliquity tilt"), _r(pelvic_tilt_deg, 1), *([""] if len(names) == 2 else []), "°"],
        [rp.tr("Pelvic obliquity step"), _r(pelvic_step_mm, 1), *([""] if len(names) == 2 else []), "mm"],
    ]

    ctx.progress(0.85, rp.tr("Drawing the preview"))
    rgb = _canvas_rgb(sl, mask)
    _draw_line(rgb, p_left_pt, p_right_pt, [100, 200, 255], thickness=1)
    rois = [rp.Roi("line", k, [p_left_pt, p_right_pt])] if _should_stamp_rois(ctx) else []
    for name in names:
        h = hips[name]
        hx, hy = h["head"]
        rx, ry = h["rx_px"], h["ry_px"]
        _draw_circle(rgb, (hx, hy), rx, ry, [60, 235, 130], thickness=2)
        _draw_line(rgb, (hx, hy), h["lat_sourcil"], [255, 220, 40], thickness=2)
        _draw_line(rgb, h["med_sourcil"], h["lat_sourcil"], [255, 140, 40], thickness=2)
        _draw_line(rgb, *h["neck_line"], [255, 90, 190], thickness=2)
        _draw_line(rgb, *h["shaft_line"], [255, 90, 190], thickness=2)
        _draw_dot(rgb, (hx, hy), [255, 70, 70], radius=3)
        if _should_stamp_rois(ctx):
            rois += [
                rp.Roi("ellipse", k, [(hx - rx, hy - ry), (hx + rx, hy + ry)]),
                rp.Roi("line", k, [(hx, hy), h["lat_sourcil"]]),
                rp.Roi("line", k, [h["med_sourcil"], h["lat_sourcil"]]),
                rp.Roi("line", k, list(h["neck_line"])),
                rp.Roi("line", k, list(h["shaft_line"])),
                rp.Roi(
                    "text",
                    k,
                    [(hx - 0.8 * rx, max(6.0, hy - 1.35 * ry))],
                    text="%s: LCEA %.1f° | Tönnis %.1f° | CCD %.1f°"
                    % (name, h["lcea_deg"], h["tonnis_deg"], h["ccd_deg"]),
                ),
            ]

    x_idx = np.arange(1, 4, dtype=np.float64)
    series = [
        rp.Series(
            _hip_side_text(n),
            x_idx + (-0.15 if i == 0 and len(names) == 2 else 0.15 if len(names) == 2 else 0.0),
            [hips[n]["lcea_deg"], hips[n]["tonnis_deg"], hips[n]["ccd_deg"]],
            kind="bars",
        )
        for i, n in enumerate(names)
    ]
    plots = [
        rp.Plot(
            rp.tr("Hip goniometry (1 LCEA °, 2 Tönnis °, 3 CCD °)"),
            series,
            x_label=rp.tr("Angle"),
            y_label=rp.tr("Degrees (°)"),
        )
    ]
    image = rp.Image(rp.tr("Hip and pelvis morphometry (slice {slice})", slice=k + 1), nx, ny, rgb)
    nz = volume.dims[2]
    controls = [
        rp.Slider("slice", rp.tr("Slice"), k, 0, max(nz - 1, 1), step=1),
        rp.Choice("side", rp.tr("Analyzed side"), [rp.tr("both"), rp.tr("right"), rp.tr("left")], side_choice),
        rp.Slider("bone_percentile", rp.tr("Bone intensity percentile (%)"), pct, 40.0, 98.0, step=1.0),
        rp.Slider("head_radius_mm", rp.tr("Femoral head radius (mm, 0 = auto)"), head_r_param, 0.0, 45.0, step=0.5),
        rp.Slider("neck_level_frac", rp.tr("Neck axis level (0.20–0.85)"), neck_frac, 0.20, 0.85, step=0.02),
        rp.Slider("shaft_level_frac", rp.tr("Shaft axis level (0.30–0.85)"), shaft_frac, 0.30, 0.85, step=0.02),
        rp.Button(
            "stamp",
            rp.tr("Stamp ROIs on image"),
            help=rp.tr("Adds femoral head ellipses, acetabular lines and CCD axes"),
        ),
    ]
    hip_args = {}
    for key, n in (("right", "Right"), ("left", "Left")):
        if n in hips:
            hip_args[key + "_lcea"] = "%.1f" % hips[n]["lcea_deg"]
            hip_args[key + "_tonnis"] = "%.1f" % hips[n]["tonnis_deg"]
            hip_args[key + "_ccd"] = "%.1f" % hips[n]["ccd_deg"]
    if len(names) == 2:
        msg = rp.tr(
            "Hip/pelvis: Right LCEA {right_lcea}°, Tönnis {right_tonnis}°, CCD {right_ccd}°; "
            "Left LCEA {left_lcea}°, Tönnis {left_tonnis}°, CCD {left_ccd}°",
            **hip_args,
        )
    elif names == ["Right"]:
        msg = rp.tr("Hip/pelvis: Right LCEA {right_lcea}°, Tönnis {right_tonnis}°, CCD {right_ccd}°", **hip_args)
    else:
        msg = rp.tr("Hip/pelvis: Left LCEA {left_lcea}°, Tönnis {left_tonnis}°, CCD {left_ccd}°", **hip_args)
    return rp.Result(table=table, plots=plots, images=[image], rois=rois, controls=controls, message=msg)


# ------------------------------------------------------------------ 4. Tool: bone_morphometry


def _extract_cortical_profile(sl, mask, cx, cy, ux_mm, uy_mm, level_offset_mm, sx, sy):
    """Samples a transverse intensity profile perpendicular to the shaft axis at ``level_offset_mm`` from (cx, cy).
    Returns (s_grid, profile, outer_left_mm, inner_left_mm, inner_right_mm, outer_right_mm, center_px, n_vec_mm)."""
    p_center_px = np.array([cx + (level_offset_mm * ux_mm) / sx, cy + (level_offset_mm * uy_mm) / sy])
    n_mm = np.array([-uy_mm, ux_mm])  # unit transverse vector in mm
    step_mm = 0.5 * min(sx, sy)
    half_span_mm = 45.0
    s_grid = np.arange(-half_span_mm, half_span_mm + step_mm, step_mm)

    # Average over 5 longitudinal strips within ±3 mm for low-noise radiogrammetry.
    offsets_long = np.linspace(-3.0, 3.0, 5)
    prof_accum = np.zeros_like(s_grid)
    mask_accum = np.zeros_like(s_grid)
    filled = np.where(np.isfinite(sl), sl, float(np.nanmin(sl)))
    for dl in offsets_long:
        base_x = p_center_px[0] + (dl * ux_mm) / sx
        base_y = p_center_px[1] + (dl * uy_mm) / sy
        xs_s = base_x + (s_grid * n_mm[0]) / sx
        ys_s = base_y + (s_grid * n_mm[1]) / sy
        prof_accum += ndimage.map_coordinates(filled, [ys_s, xs_s], order=1, mode="nearest")
        mask_accum += ndimage.map_coordinates(mask.astype(np.float64), [ys_s, xs_s], order=0, mode="constant")
    prof = prof_accum / len(offsets_long)
    in_bone = (mask_accum / len(offsets_long)) >= 0.5

    hits = np.nonzero(in_bone)[0]
    if hits.size < 4:
        p_min, p_max = float(prof.min()), float(prof.max())
        hits = np.nonzero(prof >= p_min + 0.4 * (p_max - p_min))[0]
    if hits.size < 4:
        raise ValueError("Transverse bone profile is too narrow at this level: adjust 'Diaphyseal level' or percentile")

    i_out_l, i_out_r = int(hits[0]), int(hits[-1])
    mid = (i_out_l + i_out_r) // 2
    if mid <= i_out_l + 1 or i_out_r <= mid + 1:
        outer_l, outer_r = float(s_grid[i_out_l]), float(s_grid[i_out_r])
        return s_grid, prof, outer_l, 0.5 * outer_l, 0.5 * outer_r, outer_r, p_center_px, n_mm

    # Locate left and right cortical intensity peaks and the medullary canal minimum between them.
    i_peak_l = i_out_l + int(np.argmax(prof[i_out_l : mid + 1]))
    i_peak_r = mid + int(np.argmax(prof[mid : i_out_r + 1]))
    if i_peak_r > i_peak_l + 1:
        i_med = i_peak_l + int(np.argmin(prof[i_peak_l : i_peak_r + 1]))
    else:
        i_med = mid

    med_val = float(prof[i_med])
    peak_l_val, peak_r_val = float(prof[i_peak_l]), float(prof[i_peak_r])
    # Endosteal margin lies at half-height between cortical peak and medullary minimum (or 28 % inward if solid).
    if peak_l_val > med_val + 1e-6 and peak_r_val > med_val + 1e-6:
        cut_l = 0.5 * (peak_l_val + med_val)
        cut_r = 0.5 * (peak_r_val + med_val)
        in_l_cand = np.nonzero(prof[i_peak_l : i_med + 1] <= cut_l)[0]
        in_r_cand = np.nonzero(prof[i_med : i_peak_r + 1] >= cut_r)[0]
        i_in_l = i_peak_l + int(in_l_cand[0]) if in_l_cand.size else int(0.6 * i_out_l + 0.4 * i_med)
        i_in_r = i_med + int(in_r_cand[0]) if in_r_cand.size else int(0.4 * i_med + 0.6 * i_out_r)
    else:
        span = i_out_r - i_out_l
        i_in_l = i_out_l + int(round(0.28 * span))
        i_in_r = i_out_r - int(round(0.28 * span))

    outer_l, inner_l = float(s_grid[i_out_l]), float(s_grid[i_in_l])
    inner_r, outer_r = float(s_grid[i_in_r]), float(s_grid[i_out_r])
    if inner_r <= inner_l:
        outer_w = max(outer_r - outer_l, step_mm)
        inner_l = outer_l + 0.28 * outer_w
        inner_r = outer_r - 0.28 * outer_w

    return s_grid, prof, outer_l, inner_l, inner_r, outer_r, p_center_px, n_mm


@rp.tool("bone_morphometry")
def bone_morphometry(volume, ctx):
    k, sl = _active_slice(volume, ctx)
    ny, nx = sl.shape
    sx, sy = _spacing_xy(volume)
    c = ctx.controls
    pct = float(c.get("bone_percentile", ctx.params["bone_percentile"]))
    level_frac = float(np.clip(c.get("level_frac", ctx.params["level_frac"]), 0.20, 0.80))

    # Hybrid region selection: closed ROI on slice k -> first segment -> largest bone island.
    ctx.progress(0.05, rp.tr("Bone mask"))
    closed_here = [r for r in ctx.rois if r.kind in CLOSED and r.slice == k]
    if closed_here:
        roi_m = _roi_mask_2d(closed_here[-1], ny, nx)
        mask = _bone_mask_2d(sl, sx, sy, pct, closing_mm=2.5, min_area_mm2=10.0) & roi_m
        if not mask.any():
            mask = roi_m
        if closed_here[-1].kind == "ellipse":
            source = rp.tr("ellipse ROI on slice {slice}", slice=k + 1)
        else:
            source = rp.tr("polygon ROI on slice {slice}", slice=k + 1)
    elif ctx.segments and ctx.segments[0].mask()[k].any():
        mask = ctx.segments[0].mask()[k]
        source = rp.tr("segment '{name}'", name=ctx.segments[0].name)
    else:
        raw = _bone_mask_2d(sl, sx, sy, pct, closing_mm=3.0, min_area_mm2=20.0)
        comps = _largest_components(raw, k=1)
        if not comps:
            raise ValueError("No bone silhouette found on slice %d: lower 'Bone intensity percentile'" % (k + 1))
        mask = comps[0]
        source = rp.tr("largest bone silhouette (P{percentile})", percentile="%g" % round(pct, 1))

    ctx.progress(0.4, rp.tr("Measuring"))
    ys, xs = np.nonzero(mask)
    if xs.size < 10:
        raise ValueError("Bone region has too few pixels (%d) for morphometry" % xs.size)

    cx, cy, ux_mm, uy_mm, length_mm, _ = _pca_axis_mm(xs, ys, sx, sy)
    pts_mm = np.column_stack([(xs - cx) * sx, (ys - cy) * sy])
    proj_u = pts_mm @ np.array([ux_mm, uy_mm])
    u_min, u_max = float(np.percentile(proj_u, 1.0)), float(np.percentile(proj_u, 99.0))
    level_offset_mm = u_min + level_frac * (u_max - u_min)

    s_grid, prof, out_l, in_l, in_r, out_r, p_lvl, n_mm = _extract_cortical_profile(
        sl, mask, cx, cy, ux_mm, uy_mm, level_offset_mm, sx, sy
    )

    outer_d = max(0.1, out_r - out_l)
    inner_d = max(0.0, in_r - in_l)
    cortex_l = max(0.0, in_l - out_l)
    cortex_r = max(0.0, out_r - in_r)
    cct = outer_d - inner_d
    cortical_index = 100.0 * cct / outer_d
    cm_ratio = cct / inner_d if inner_d > 1e-3 else None
    total_area = 0.25 * math.pi * outer_d**2
    medullary_area = 0.25 * math.pi * inner_d**2
    cortical_area = total_area - medullary_area
    exton_smith = (outer_d**2 - inner_d**2) / max(outer_d * length_mm, 1e-6)

    vals_bone = sl[mask & np.isfinite(sl)]
    mean_intensity = float(vals_bone.mean()) if vals_bone.size else 0.0
    sd_intensity = float(vals_bone.std()) if vals_bone.size else 0.0
    unit = volume.unit or rp.tr("intensity")

    table = [
        _quantity_header(),
        [rp.tr("Image"), k + 1, ""],
        [rp.tr("Source"), source, ""],
        [rp.tr("Bone length (longitudinal axis)"), _r(length_mm, 1), "mm"],
        [rp.tr("Diaphyseal sampling level"), _r(100.0 * level_frac, 0), rp.tr("% of length")],
        [rp.tr("Outer periosteal diameter (D)"), _r(outer_d, 2), "mm"],
        [rp.tr("Inner medullary diameter (d)"), _r(inner_d, 2), "mm"],
        [rp.tr("Combined cortical thickness (CCT = D − d)"), _r(cct, 2), "mm"],
        [rp.tr("Cortex 1 / Cortex 2 thickness"), "%s / %s" % (_r(cortex_l, 2), _r(cortex_r, 2)), "mm"],
        [rp.tr("Barnett-Nordin cortical index ((D − d) / D)"), _r(cortical_index, 1), "%"],
        [rp.tr("Corticomedullary ratio ((D − d) / d)"), _r(cm_ratio, 2), rp.tr("ratio")],
        [rp.tr("Cross-sectional total area"), _r(total_area, 1), "mm²"],
        [rp.tr("Cross-sectional cortical area"), _r(cortical_area, 1), "mm²"],
        [rp.tr("Cross-sectional medullary area"), _r(medullary_area, 1), "mm²"],
        [rp.tr("Exton-Smith dimensionless index"), _r(exton_smith, 3), ""],
        [rp.tr("Bone mean ± SD"), "%s ± %s" % (_r(mean_intensity, 1), _r(sd_intensity, 1)), unit],
    ]

    def _trans_pt(s_mm):
        return (float(p_lvl[0] + (s_mm * n_mm[0]) / sx), float(p_lvl[1] + (s_mm * n_mm[1]) / sy))

    p_top = (float(cx + (u_min * ux_mm) / sx), float(cy + (u_min * uy_mm) / sy))
    p_bot = (float(cx + (u_max * ux_mm) / sx), float(cy + (u_max * uy_mm) / sy))
    p_out_l, p_out_r = _trans_pt(out_l), _trans_pt(out_r)
    p_in_l, p_in_r = _trans_pt(in_l), _trans_pt(in_r)

    ctx.progress(0.85, rp.tr("Drawing the preview"))
    rgb = _canvas_rgb(sl, mask)
    _draw_line(rgb, p_top, p_bot, [80, 190, 255], thickness=1)
    _draw_line(rgb, p_out_l, p_out_r, [255, 215, 40], thickness=2)
    _draw_line(rgb, p_in_l, p_in_r, [255, 80, 120], thickness=2)
    for pt in (p_out_l, p_in_l, p_in_r, p_out_r):
        _draw_dot(rgb, pt, [60, 240, 120], radius=3)

    keep_band = (s_grid >= out_l - 8.0) & (s_grid <= out_r + 8.0)
    plot_title = rp.tr(
        "Transverse diaphyseal profile (D = {outer} mm, d = {inner} mm, CI = {ci}%)",
        outer="%.1f" % outer_d,
        inner="%.1f" % inner_d,
        ci="%.1f" % cortical_index,
    )
    plots = [
        rp.Plot(
            plot_title,
            [rp.Series(rp.tr("Intensity"), s_grid[keep_band], prof[keep_band])],
            x_label=rp.tr("Transverse position from shaft axis (mm)"),
            y_label=unit,
        )
    ]
    image = rp.Image(
        rp.tr("Bone morphometry (slice {slice}): CI {ci}%", slice=k + 1, ci="%.1f" % cortical_index), nx, ny, rgb
    )

    rois = []
    if _should_stamp_rois(ctx):
        rois = [
            rp.Roi("line", k, [p_top, p_bot]),
            rp.Roi("line", k, [p_out_l, p_out_r]),
            rp.Roi("line", k, [p_in_l, p_in_r]),
            rp.Roi(
                "text",
                k,
                [(p_out_r[0] + 6.0, p_out_r[1])],
                text="D %.1f mm | d %.1f mm | CCT %.1f mm | CI %.1f%%" % (outer_d, inner_d, cct, cortical_index),
            ),
        ]

    nz = volume.dims[2]
    controls = [
        rp.Slider("slice", rp.tr("Slice"), k, 0, max(nz - 1, 1), step=1),
        rp.Slider("bone_percentile", rp.tr("Bone intensity percentile (%)"), pct, 40.0, 98.0, step=1.0),
        rp.Slider("level_frac", rp.tr("Diaphyseal sampling level (0.20–0.80)"), level_frac, 0.20, 0.80, step=0.02),
        rp.Button(
            "stamp",
            rp.tr("Stamp ROIs on image"),
            help=rp.tr("Adds shaft axis, outer D and inner d lines to the slice"),
        ),
    ]
    msg = rp.tr(
        "Bone morphometry: length {length} mm, D {outer} mm, d {inner} mm, cortical index {ci}%",
        length="%.1f" % length_mm,
        outer="%.2f" % outer_d,
        inner="%.2f" % inner_d,
        ci="%.1f" % cortical_index,
    )
    return rp.Result(table=table, plots=plots, images=[image], rois=rois, controls=controls, message=msg)


# ------------------------------------------------------------------ 5. Tool: foot_hand


_VIEW_OF_PARAM = {"Foot AP": "foot_ap", "Foot lateral": "foot_lateral", "Hand / wrist AP": "hand_ap"}


def _infer_extremity_view(mask, sx, sy, mode_param, choice_str):
    """Resolves the extremity view mode from interactive choice, manifest param or silhouette geometry."""
    if choice_str and choice_str != "auto":
        return choice_str
    if mode_param in _VIEW_OF_PARAM:
        return _VIEW_OF_PARAM[mode_param]
    ys, xs = np.nonzero(mask)
    w_mm = (xs.max() - xs.min() + 1) * sx
    h_mm = (ys.max() - ys.min() + 1) * sy
    if w_mm > 1.25 * h_mm:
        return "foot_lateral"
    # Distinguish hand_ap vs foot_ap by counting separate digital/metacarpal rays across the mid-section.
    mid_y = int(round(0.45 * ys.min() + 0.55 * ys.max()))
    _, n_rays = ndimage.label(mask[max(0, mid_y - 2) : min(mask.shape[0], mid_y + 3)].any(axis=0))
    return "hand_ap" if n_rays >= 4 else "foot_ap"


def _ray_axes(mask, n_rays_wanted=2):
    """Finds tubular ray axes (metatarsals/phalanges) sorted medial-to-lateral by x centroid."""
    ys, xs = np.nonzero(mask)
    y_min, y_max = int(ys.min()), int(ys.max())
    span_y = max(y_max - y_min, 10)
    # Sample mid-shaft band [0.28, 0.75] of height and split into vertical ray strips.
    y0, y1 = int(round(y_min + 0.28 * span_y)), int(round(y_min + 0.75 * span_y))
    band = mask[y0 : y1 + 1]
    lab, n = ndimage.label(band)
    rays = []
    if n >= 2:
        sizes = np.bincount(lab.ravel())
        order = np.argsort(sizes[1:])[::-1] + 1
        for idx in order[: max(n_rays_wanted, 3)]:
            ry, rx = np.nonzero(lab == idx)
            if rx.size >= 8:
                rays.append((float(rx.mean()), rx, ry + y0))
        rays.sort(key=lambda item: item[0])
    if len(rays) < 2:
        # Split the forefoot/midfoot silhouette into medial (1st ray) and adjacent (2nd ray) corridors.
        x_min, x_max = int(xs.min()), int(xs.max())
        x_cut1 = int(round(x_min + 0.32 * (x_max - x_min)))
        x_cut2 = int(round(x_min + 0.62 * (x_max - x_min)))
        for c0, c1 in ((x_min, x_cut1), (x_cut1, x_cut2)):
            sub = np.zeros_like(mask)
            sub[y0 : y1 + 1, c0:c1] = mask[y0 : y1 + 1, c0:c1]
            ry, rx = np.nonzero(sub)
            if rx.size >= 6:
                rays.append((float(rx.mean()), rx, ry))
    return rays


@rp.tool("foot_hand")
def foot_hand(volume, ctx):
    k, sl = _active_slice(volume, ctx)
    ny, nx = sl.shape
    sx, sy = _spacing_xy(volume)
    c = ctx.controls
    pct = float(c.get("bone_percentile", ctx.params["bone_percentile"]))
    view_choice = c.get("view", "auto")

    ctx.progress(0.05, rp.tr("Bone mask"))
    mask = _bone_mask_2d(sl, sx, sy, pct, closing_mm=2.5, min_area_mm2=15.0)
    if not mask.any():
        raise ValueError(
            "No extremity bone structure detected on slice %d: lower 'Bone intensity percentile'" % (k + 1)
        )

    # The preview is drawn while measuring (each view adds its own marks), so one step covers both.
    ctx.progress(0.4, rp.tr("Measuring"))
    mode = _infer_extremity_view(mask, sx, sy, ctx.params["view_mode"], view_choice)
    drawn_lines = [r for r in ctx.rois if r.kind == "line" and r.slice == k and len(r.points) >= 2]
    rgb = _canvas_rgb(sl, mask)
    rois = []
    ys_all, xs_all = np.nonzero(mask)
    y_min, y_max = int(ys_all.min()), int(ys_all.max())
    x_min, x_max = int(xs_all.min()), int(xs_all.max())

    if mode == "foot_ap":
        rays = _ray_axes(mask, n_rays_wanted=2)
        if len(rays) >= 2:
            _, rx1, ry1 = rays[0]
            _, rx2, ry2 = rays[1]
            # Proximal half of 1st ray = 1st metatarsal; distal half of 1st ray = proximal phalanx of hallux.
            y_split = 0.5 * (ry1.min() + ry1.max())
            m1_pick = ry1 >= y_split
            p1_pick = ry1 < y_split
            if m1_pick.sum() < 4 or p1_pick.sum() < 4:
                m1_pick = np.ones_like(ry1, dtype=bool)
                p1_pick = np.ones_like(ry1, dtype=bool)
            cx_m1, cy_m1, ux_m1, uy_m1, len_m1, _ = _pca_axis_mm(rx1[m1_pick], ry1[m1_pick], sx, sy)
            cx_p1, cy_p1, ux_p1, uy_p1, len_p1, _ = _pca_axis_mm(rx1[p1_pick], ry1[p1_pick], sx, sy)
            cx_m2, cy_m2, ux_m2, uy_m2, len_m2, _ = _pca_axis_mm(rx2, ry2, sx, sy)
        else:
            span_x, span_y = x_max - x_min, y_max - y_min
            cx_m1, cy_m1, ux_m1, uy_m1, len_m1 = x_min + 0.25 * span_x, y_min + 0.65 * span_y, -0.15, 0.99, 55.0
            cx_p1, cy_p1, ux_p1, uy_p1, len_p1 = x_min + 0.22 * span_x, y_min + 0.28 * span_y, 0.12, 0.99, 30.0
            cx_m2, cy_m2, ux_m2, uy_m2, len_m2 = x_min + 0.45 * span_x, y_min + 0.60 * span_y, 0.0, 1.0, 62.0

        def _seg(cx0, cy0, ux0, uy0, l_mm):
            h = max(10.0, 0.45 * l_mm)
            return (cx0 - h * ux0 / sx, cy0 - h * uy0 / sy), (cx0 + h * ux0 / sx, cy0 + h * uy0 / sy)

        m1_a, m1_b = _seg(cx_m1, cy_m1, ux_m1, uy_m1, len_m1)
        p1_a, p1_b = _seg(cx_p1, cy_p1, ux_p1, uy_p1, len_p1)
        m2_a, m2_b = _seg(cx_m2, cy_m2, ux_m2, uy_m2, len_m2)
        if len(drawn_lines) >= 2:
            m1_a, m1_b = tuple(drawn_lines[-2].points[0]), tuple(drawn_lines[-2].points[1])
            p1_a, p1_b = tuple(drawn_lines[-1].points[0]), tuple(drawn_lines[-1].points[1])
        if len(drawn_lines) >= 3:
            m2_a, m2_b = tuple(drawn_lines[-3].points[0]), tuple(drawn_lines[-3].points[1])

        hva_deg = _acute_angle_deg(m1_a, m1_b, p1_a, p1_b, sx, sy)
        ima_deg = _acute_angle_deg(m1_a, m1_b, m2_a, m2_b, sx, sy)
        hva_classes = (
            rp.tr("Normal (< 15°)"),
            rp.tr("Mild (15–20°)"),
            rp.tr("Moderate (20–40°)"),
            rp.tr("Severe (≥ 40°)"),
        )
        hva_index = 0 if hva_deg < 15.0 else 1 if hva_deg < 20.0 else 2 if hva_deg < 40.0 else 3
        hva_class = hva_classes[hva_index]
        table = [
            _quantity_header(),
            [rp.tr("Image"), k + 1, ""],
            [rp.tr("View mode"), rp.tr("Foot AP (dorsoplantar)"), ""],
            [rp.tr("Hallux valgus angle (HVA)"), _r(hva_deg, 1), "°"],
            [rp.tr("HVA classification"), hva_class, ""],
            [rp.tr("1st–2nd intermetatarsal angle (IMA)"), _r(ima_deg, 1), "°"],
            [rp.tr("1st metatarsal shaft length"), _r(len_m1, 1), "mm"],
            [rp.tr("2nd metatarsal shaft length"), _r(len_m2, 1), "mm"],
        ]
        ray_Wait = ((m1_a, m1_b, [60, 235, 120]), (p1_a, p1_b, [255, 215, 40]), (m2_a, m2_b, [90, 190, 255]))
        for a_pt, b_pt, col in ray_Wait:
            _draw_line(rgb, a_pt, b_pt, col, thickness=2)
        if _should_stamp_rois(ctx):
            rois = [
                rp.Roi("line", k, [m1_a, m1_b]),
                rp.Roi("line", k, [p1_a, p1_b]),
                rp.Roi("line", k, [m2_a, m2_b]),
                rp.Roi("text", k, [m1_a], text="Foot AP: HVA %.1f° (%s) | IMA %.1f°" % (hva_deg, str(hva_class), ima_deg)),
            ]
        plot_vals = [hva_deg, ima_deg]
        plot_title = rp.tr("Foot AP angles (1 HVA °, 2 IMA °)")
        foot_args = {"hva": "%.1f" % hva_deg, "ima": "%.1f" % ima_deg}
        msg = (
            rp.tr("Foot AP: HVA {hva}° (Normal (< 15°)), 1–2 IMA {ima}°", **foot_args),
            rp.tr("Foot AP: HVA {hva}° (Mild (15–20°)), 1–2 IMA {ima}°", **foot_args),
            rp.tr("Foot AP: HVA {hva}° (Moderate (20–40°)), 1–2 IMA {ima}°", **foot_args),
            rp.tr("Foot AP: HVA {hva}° (Severe (≥ 40°)), 1–2 IMA {ima}°", **foot_args),
        )[hva_index]

    elif mode == "foot_lateral":
        # Extract superior and inferior calcaneal / hindfoot contour across columns x_min..x_max.
        cols = np.arange(x_min, x_max + 1)
        top_y = np.zeros_like(cols, dtype=np.float64)
        bot_y = np.zeros_like(cols, dtype=np.float64)
        for i, col in enumerate(cols):
            r_hits = np.nonzero(mask[:, col])[0]
            top_y[i] = float(r_hits[0]) if r_hits.size else float(y_min)
            bot_y[i] = float(r_hits[-1]) if r_hits.size else float(y_max)
        top_y = ndimage.gaussian_filter1d(top_y, sigma=max(1.0, 3.0 / sx), mode="nearest")
        bot_y = ndimage.gaussian_filter1d(bot_y, sigma=max(1.0, 3.0 / sx), mode="nearest")
        n_c = len(cols)
        # Landmarks along the calcaneal superior contour: tuberosity, posterior facet apex, sinus tarsi, anterior proc.
        i_tub = int(round(0.12 * (n_c - 1)))
        i_apex = int(round(0.42 * (n_c - 1)))
        i_nadir = int(round(0.58 * (n_c - 1)))
        i_ant = int(round(0.78 * (n_c - 1)))
        pt_tub = (float(cols[i_tub]), float(top_y[i_tub]))
        pt_apex = (float(cols[i_apex]), float(top_y[i_apex]) - 4.0 / sy)
        pt_nadir = (float(cols[i_nadir]), float(top_y[i_nadir]) + 3.0 / sy)
        pt_ant = (float(cols[i_ant]), float(top_y[i_ant]))
        plantar_a = (float(cols[i_tub]), float(bot_y[i_tub]))
        plantar_b = (float(cols[i_ant]), float(bot_y[i_ant]))

        if len(drawn_lines) >= 2:
            l1, l2 = drawn_lines[-2], drawn_lines[-1]
            bohler_deg = _acute_angle_deg(l1.points[0], l1.points[1], l2.points[0], l2.points[1], sx, sy)
        else:
            bohler_deg = _acute_angle_deg(pt_tub, pt_apex, pt_apex, pt_ant, sx, sy)
        gissane_deg = 180.0 - _acute_angle_deg(pt_apex, pt_nadir, pt_nadir, pt_ant, sx, sy)
        pitch_deg = math.degrees(
            math.atan2(abs(plantar_a[1] - plantar_b[1]) * sy, max(abs(plantar_b[0] - plantar_a[0]) * sx, 1e-6))
        )

        table = [
            _quantity_header(),
            [rp.tr("Image"), k + 1, ""],
            [rp.tr("View mode"), rp.tr("Foot Lateral"), ""],
            [rp.tr("Böhler calcaneal angle (normal 20–40°)"), _r(bohler_deg, 1), "°"],
            [rp.tr("Gissane crucial angle (normal 120–145°)"), _r(gissane_deg, 1), "°"],
            [rp.tr("Calcaneal pitch angle (normal 18–30°)"), _r(pitch_deg, 1), "°"],
        ]
        _draw_line(rgb, pt_tub, pt_apex, [255, 215, 40], thickness=2)
        _draw_line(rgb, pt_apex, pt_ant, [255, 215, 40], thickness=2)
        _draw_line(rgb, pt_apex, pt_nadir, [60, 235, 120], thickness=2)
        _draw_line(rgb, pt_nadir, pt_ant, [60, 235, 120], thickness=2)
        _draw_line(rgb, plantar_a, plantar_b, [90, 190, 255], thickness=2)
        if _should_stamp_rois(ctx):
            rois = [
                rp.Roi("line", k, [pt_tub, pt_apex]),
                rp.Roi("line", k, [pt_apex, pt_ant]),
                rp.Roi("line", k, [plantar_a, plantar_b]),
                rp.Roi(
                    "text",
                    k,
                    [pt_apex],
                    text="Foot Lat: Böhler %.1f° | Gissane %.1f° | Pitch %.1f°" % (bohler_deg, gissane_deg, pitch_deg),
                ),
            ]
        plot_vals = [bohler_deg, gissane_deg, pitch_deg]
        plot_title = rp.tr("Foot lateral angles (1 Böhler °, 2 Gissane °, 3 Calcaneal pitch °)")
        msg = rp.tr(
            "Foot lateral: Böhler {bohler}°, Gissane {gissane}°, calcaneal pitch {pitch}°",
            bohler="%.1f" % bohler_deg,
            gissane="%.1f" % gissane_deg,
            pitch="%.1f" % pitch_deg,
        )

    else:
        # Hand / Wrist AP: 2nd metacarpal radiogrammetry + radial inclination.
        rays = _ray_axes(mask, n_rays_wanted=3)
        if len(rays) >= 2:
            rx_mc, ry_mc = rays[1][1], rays[1][2]
        elif rays:
            rx_mc, ry_mc = rays[0][1], rays[0][2]
        else:
            rx_mc, ry_mc = xs_all, ys_all
        cx, cy, ux_mm, uy_mm, mc_len_mm, _ = _pca_axis_mm(rx_mc, ry_mc, sx, sy)
        _, _, out_l, in_l, in_r, out_r, p_lvl, n_mm = _extract_cortical_profile(
            sl, mask, cx, cy, ux_mm, uy_mm, 0.0, sx, sy
        )
        outer_d = max(0.1, out_r - out_l)
        inner_d = max(0.0, in_r - in_l)
        mci = 100.0 * (outer_d - inner_d) / outer_d

        # Distal radial articular inclination in the lower third of the hand/wrist radiograph.
        y_wrist = int(round(y_min + 0.78 * (y_max - y_min)))
        w_cols = np.nonzero(mask[max(0, y_wrist - 3) : min(ny, y_wrist + 4)].any(axis=0))[0]
        rx0 = float(np.percentile(w_cols, 15)) if w_cols.size else float(x_min)
        rx1 = float(np.percentile(w_cols, 85)) if w_cols.size else float(x_max)
        rad_a = (rx0, float(y_wrist) + 4.0 / sy)
        rad_b = (rx1, float(y_wrist) - 4.0 / sy)
        if drawn_lines:
            rad_a, rad_b = tuple(drawn_lines[-1].points[0]), tuple(drawn_lines[-1].points[1])
        radial_inc_deg = math.degrees(
            math.atan2(abs(rad_a[1] - rad_b[1]) * sy, max(abs(rad_b[0] - rad_a[0]) * sx, 1e-6))
        )

        table = [
            _quantity_header(),
            [rp.tr("Image"), k + 1, ""],
            [rp.tr("View mode"), rp.tr("Hand / Wrist AP"), ""],
            [rp.tr("2nd metacarpal length"), _r(mc_len_mm, 1), "mm"],
            [rp.tr("2nd metacarpal outer diameter (D)"), _r(outer_d, 2), "mm"],
            [rp.tr("2nd metacarpal medullary diameter (d)"), _r(inner_d, 2), "mm"],
            [rp.tr("Metacarpal cortical index (MCI = (D − d) / D)"), _r(mci, 1), "%"],
            [rp.tr("Radial inclination angle"), _r(radial_inc_deg, 1), "°"],
        ]
        p_out_l = (float(p_lvl[0] + (out_l * n_mm[0]) / sx), float(p_lvl[1] + (out_l * n_mm[1]) / sy))
        p_out_r = (float(p_lvl[0] + (out_r * n_mm[0]) / sx), float(p_lvl[1] + (out_r * n_mm[1]) / sy))
        _draw_line(rgb, p_out_l, p_out_r, [255, 215, 40], thickness=2)
        _draw_line(rgb, rad_a, rad_b, [60, 235, 120], thickness=2)
        if _should_stamp_rois(ctx):
            rois = [
                rp.Roi("line", k, [p_out_l, p_out_r]),
                rp.Roi("line", k, [rad_a, rad_b]),
                rp.Roi(
                    "text",
                    k,
                    [p_out_r],
                    text="Hand AP: MCI %.1f%% | D %.1f mm | Radial inc %.1f°" % (mci, outer_d, radial_inc_deg),
                ),
            ]
        plot_vals = [mci, radial_inc_deg]
        plot_title = rp.tr("Hand/wrist metrics (1 MCI %, 2 Radial inclination °)")
        msg = rp.tr(
            "Hand/wrist AP: MCI {mci}% (D {outer} mm, d {inner} mm), radial inclination {incl}°",
            mci="%.1f" % mci,
            outer="%.2f" % outer_d,
            inner="%.2f" % inner_d,
            incl="%.1f" % radial_inc_deg,
        )

    plots = [
        rp.Plot(
            plot_title,
            [rp.Series(rp.tr("Value"), np.arange(1, len(plot_vals) + 1, dtype=np.float64), plot_vals, kind="bars")],
            x_label=rp.tr("Metric"),
            y_label=rp.tr("Value"),
        )
    ]
    if mode == "foot_ap":
        image_title = rp.tr("Foot and hand goniometry (foot_ap, slice {slice})", slice=k + 1)
    elif mode == "foot_lateral":
        image_title = rp.tr("Foot and hand goniometry (foot_lateral, slice {slice})", slice=k + 1)
    else:
        image_title = rp.tr("Foot and hand goniometry (hand_ap, slice {slice})", slice=k + 1)
    image = rp.Image(image_title, nx, ny, rgb)
    nz = volume.dims[2]
    controls = [
        rp.Slider("slice", rp.tr("Slice"), k, 0, max(nz - 1, 1), step=1),
        rp.Choice(
            "view",
            rp.tr("Extremity view"),
            [rp.tr("auto"), rp.tr("foot_ap"), rp.tr("foot_lateral"), rp.tr("hand_ap")],
            view_choice,
        ),
        rp.Slider("bone_percentile", rp.tr("Bone intensity percentile (%)"), pct, 40.0, 98.0, step=1.0),
        rp.Button("stamp", rp.tr("Stamp ROIs on image"), help=rp.tr("Adds goniometric axes and labels to the slice")),
    ]
    return rp.Result(table=table, plots=plots, images=[image], rois=rois, controls=controls, message=msg)

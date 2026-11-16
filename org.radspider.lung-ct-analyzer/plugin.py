"""Lung CT analyzer: lung volumes by density, after the 3D Slicer extension LungCTAnalyzer (R. Bumm, Apache-2.0).

Own implementation with numpy and scipy; what is taken from the extension is what it computes and its default
Hounsfield limits (LungCTAnalyzer/LungCTAnalyzer.py, ``defaultThresholds`` and ``calculateStatistics``; the lung
threshold and the 12 mm / 2 mm post-processing from LungCTSegmenter/LungCTSegmenter.py). Research use: the
extension itself says its results are not clinically evaluated, and neither are these.
"""

import numpy as np
from scipy import ndimage

import radspider_plugin as rp

# Class names and limits of the extension: a voxel of class i has limits[i-1] <= HU < limits[i].
CLASSES = ("Emphysema", "Inflated", "Infiltration", "Collapsed", "Vessels")
LIMIT_PARAMS = ("emphysema_max", "inflated_max", "infiltrated_max", "collapsed_max")
LIMIT_DEFAULTS = (-950.0, -750.0, -400.0, 0.0)
LIMIT_RANGE = (-1100.0, 3000.0)

NOT_A_LUNG = (
    "vessel", "nodule", "tumor", "tumour", "lesion", "trachea", "airway", "bronch", "artery", "vein", "emphysema",
    "inflated", "infiltrat", "collapsed", "healthy", "opacity", "consolidation",
)
WHOLE_LUNGS = ("lung", "lungs", "lung mask", "lungs mask", "both lungs")


def _hu(volume):
    if volume.unit != "HU":
        raise ValueError(
            "This needs a CT in Hounsfield units; the series is in %s. Run it on a CT series."
            % (volume.unit or "no known unit")
        )
    return volume.numpy()


def _spacing_zyx(volume):
    return (volume.spacing[2], volume.spacing[1], volume.spacing[0])


def _left_right_axis(volume):
    """(array axis, sign): the axis of (slices, rows, columns) that runs right-left in the patient; sign > 0 when a
    larger index is further to the patient's left. Without a place in the patient: a standard axial image, columns
    growing towards the patient's left."""
    vectors = (volume.normal, volume.col, volume.row)
    if any(v is None for v in vectors):
        return 2, 1.0
    axis = int(np.argmax([abs(v[0]) for v in vectors]))
    return axis, 1.0 if vectors[axis][0] >= 0 else -1.0


def _cranial_first(volume):
    """True when slice 0 is the most cranial one, False when it is the most caudal, None when the slices are not
    axial or the viewer did not say."""
    n = volume.normal
    if n is None or abs(n[2]) < 0.7:
        return None
    return n[2] < 0


def _bbox(mask, margin=(0, 0, 0)):
    """Slices of the bounding box of a non-empty mask, grown by ``margin`` voxels and clipped to the array."""
    out = []
    for axis in range(3):
        other = tuple(a for a in range(3) if a != axis)
        hit = np.nonzero(mask.any(axis=other))[0]
        out.append(slice(max(0, int(hit[0]) - margin[axis]), min(mask.shape[axis], int(hit[-1]) + 1 + margin[axis])))
    return tuple(out)


def _ball_close(mask, radius_mm, sampling):
    """Morphological closing with a ball of ``radius_mm``, as two Euclidean distance transforms on the bounding
    box: a ball of 6 mm on 0.7 mm voxels is a 17-voxel kernel, far too slow as a plain dilation + erosion."""
    if radius_mm <= 0 or not mask.any():
        return mask
    box = _bbox(mask)
    # Zero padding wider than the ball: the dilation never reaches the border, so the erosion is not cut by it.
    pad = [int(np.ceil(radius_mm / s)) + 1 for s in sampling]
    crop = np.pad(mask[box], [(p, p) for p in pad])
    grown = ndimage.distance_transform_edt(~crop, sampling=sampling) <= radius_mm
    closed = ndimage.distance_transform_edt(grown, sampling=sampling) > radius_mm
    out = np.zeros_like(mask)
    out[box] = closed[tuple(slice(p, -p) for p in pad)]
    return out


def _largest(sizes):
    """Labels (1-based) by falling size."""
    return np.argsort(sizes[1:])[::-1] + 1


def _internal_air(a, upper, progress):
    """Air (HU < upper) enclosed by the body, slice by slice: the body is the largest piece of tissue of the slice
    with its holes filled, so the air around the patient and under the table is left out."""
    air = np.zeros(a.shape, dtype=bool)
    for z in range(a.shape[0]):
        tissue = a[z] >= upper  # NaN (no data) is neither tissue nor air
        lab, n = ndimage.label(tissue)
        if n == 0:
            continue
        sizes = np.bincount(lab.ravel())
        body = ndimage.binary_fill_holes(lab == _largest(sizes)[0])
        air[z] = body & (a[z] < upper)
        if z % 16 == 0:
            progress(0.35 * z / a.shape[0], rp.tr("Body outline"))
    return air


def _lung_air(air, voxel_ml):
    """The air of lungs and airways: the largest 3D piece, and the second one when it is of the same order (lungs
    that the threshold does not connect through the bronchi). Bowel and stomach gas are smaller and dropped."""
    lab, n = ndimage.label(air)
    if n == 0:
        return None
    sizes = np.bincount(lab.ravel())
    order = _largest(sizes)
    keep = [order[0]]
    if n > 1 and sizes[order[1]] >= 0.2 * sizes[order[0]]:
        keep.append(order[1])
    if sizes[keep].sum() * voxel_ml < 100.0:
        return None
    return np.isin(lab, keep)


def _track_airway(air, order, start, seed, pixel_mm2):
    """Follows a 2D piece of air from slice ``order[start]`` towards the feet while it stays an airway: in each next
    slice the pieces that overlap the previous ones are kept unless they are far larger than the trachea (then the
    airway has opened into a lung). Returns the mask and the tracked length in slices."""
    limit = min(1500.0, max(3.0 * seed.sum() * pixel_mm2, 400.0))
    out = np.zeros(air.shape, dtype=bool)
    out[order[start]] = seed
    previous, count = seed, 1
    for z in order[start + 1:]:
        lab, _ = ndimage.label(air[z])
        current = np.zeros_like(seed)
        for i in np.unique(lab[previous]):
            if i == 0:
                continue
            piece = lab == i
            if piece.sum() * pixel_mm2 <= limit:
                current |= piece
        if not current.any():
            break
        out[z] = current
        previous, count = current, count + 1
    return out, count


def _trachea(air, spacing, cranial_first, lr_axis):
    """The trachea and the main bronchi down to where they open into the lungs, or None. Looks in the cranial third
    for a compact piece of air of tracheal size near the midline that can be followed for at least 20 mm."""
    if lr_axis == 0:
        return None
    dz, dy, dx = spacing
    pixel_mm2 = dy * dx
    slices = np.nonzero(air.any(axis=(1, 2)))[0]
    order = slices if cranial_first else slices[::-1]
    side = lr_axis - 1  # axis of a slice that runs right-left
    extent = np.nonzero(air.any(axis=tuple(a for a in range(3) if a != lr_axis)))[0]
    middle, width = 0.5 * (extent[0] + extent[-1]), max(1, extent[-1] - extent[0])
    need = max(2, int(np.ceil(20.0 / dz)))
    tried = 0
    for start in range(max(1, len(order) // 3)):
        lab, n = ndimage.label(air[order[start]])
        candidates = []
        for i, box in enumerate(ndimage.find_objects(lab), 1):
            piece = lab[box] == i
            area = piece.sum() * pixel_mm2
            if not 30.0 <= area <= 1200.0 or piece.mean() < 0.4:  # too small, too large, or not compact
                continue
            centre = 0.5 * (box[side].start + box[side].stop - 1)
            if abs(centre - middle) <= 0.15 * width:
                candidates.append((abs(centre - middle), i))
        for _, i in sorted(candidates):
            mask, count = _track_airway(air, order, start, lab == i, pixel_mm2)
            if count >= need:
                return mask
            tried += 1
            if tried >= 40:
                return None
    return None


def _split_lungs(lungs, sampling, lr_axis):
    """Two lungs from one mask, as (lower index side, higher index side) along ``lr_axis``. Two large pieces: taken
    as they are. One piece (lungs touching behind the sternum): eroded mm by mm until it falls apart, then every
    voxel goes to the core that reaches it first. Never apart: cut where the mask is thinnest near the middle."""
    other = tuple(a for a in range(3) if a != lr_axis)
    lab, n = ndimage.label(lungs)
    sizes = np.bincount(lab.ravel())
    order = _largest(sizes) if n else []
    seeds, rounds = None, 2
    if n >= 2 and sizes[order[1]] >= 0.2 * sizes[order[0]]:
        seeds = (lab == order[0], lab == order[1])
    elif n:
        depth = ndimage.distance_transform_edt(lungs, sampling=sampling)
        for mm in range(1, 9):
            lab, n = ndimage.label(depth > mm)
            if n < 2:
                continue
            sizes = np.bincount(lab.ravel())
            order = _largest(sizes)
            if sizes[order[1]] >= 0.2 * sizes[order[0]]:
                seeds = (lab == order[0], lab == order[1])
                rounds = int(np.ceil(mm / min(sampling))) + 2
                break
    index = np.arange(lungs.shape[lr_axis]).reshape([-1 if a == lr_axis else 1 for a in range(3)])
    if seeds is None:
        profile = lungs.sum(axis=other)
        hit = np.nonzero(profile)[0]
        if hit.size < 2:
            return lungs, np.zeros_like(lungs)
        lo = hit[0] + (hit[-1] - hit[0]) // 3
        hi = max(lo + 1, hit[-1] - (hit[-1] - hit[0]) // 3)
        cut = lo + int(np.argmin(profile[lo:hi]))
        return lungs & (index < cut), lungs & (index >= cut)
    a, b = seeds
    for _ in range(rounds):
        a = ndimage.binary_dilation(a, mask=lungs & ~b) | a
        b = ndimage.binary_dilation(b, mask=lungs & ~a) | b
    # What neither core reached (small separate pieces): by the side of the midpoint between the cores it lies on.
    ca = float((a.sum(axis=other) * index.ravel()).sum()) / a.sum()
    cb = float((b.sum(axis=other) * index.ravel()).sum()) / b.sum()
    rest = lungs & ~a & ~b
    near_a = (index < 0.5 * (ca + cb)) == (ca < cb)
    a |= rest & near_a
    b |= rest & ~near_a
    return (a, b) if ca < cb else (b, a)


def _segment_lungs(volume, a, upper, closing_mm, smooth_mm, want_trachea, progress):
    """(right lung, left lung, trachea or None) as boolean masks, from thresholding and connected components."""
    sampling = _spacing_zyx(volume)
    voxel_ml = sampling[0] * sampling[1] * sampling[2] / 1000.0
    lr_axis, lr_sign = _left_right_axis(volume)
    air = _lung_air(_internal_air(a, upper, progress), voxel_ml)
    if air is None:
        raise ValueError(
            "No lungs found: less than 100 ml of air below %g HU inside the body. Run it on a chest CT, or raise "
            "the lung threshold." % upper
        )
    progress(0.45, rp.tr("Airways"))
    margin = tuple(int(np.ceil((0.5 * closing_mm + 3.0 * smooth_mm) / s)) + 2 for s in sampling)
    box = _bbox(air, margin)
    air_box = air[box]

    trachea = None
    if want_trachea:
        cranial = _cranial_first(volume)
        # Without the slice direction, try both ends: lung bases are far too large to pass for a trachea.
        for first in ((True, False) if cranial is None else (cranial,)):
            trachea = _trachea(air_box, sampling, first, lr_axis)
            if trachea is not None:
                break
        if trachea is None:
            print("No trachea found: nothing of tracheal size near the midline in the cranial third of the lungs")
    lungs = air_box if trachea is None else air_box & ~trachea

    progress(0.55, rp.tr("Splitting the lungs"))
    low, high = _split_lungs(lungs, sampling, lr_axis)
    right, left = (low, high) if lr_sign > 0 else (high, low)

    done = []
    for n, lung in enumerate((right, left)):
        progress(0.65 + 0.15 * n, rp.tr("Closing and smoothing"))
        # Slicer's kernel size is a diameter; closing fills the vessels and other holes the threshold left.
        lung = _ball_close(lung, 0.5 * closing_mm, sampling)
        if smooth_mm > 0 and lung.any():
            sigma = [smooth_mm / s for s in sampling]
            lung = ndimage.gaussian_filter(lung.astype(np.float32), sigma, mode="nearest") > 0.5
        done.append(lung)
    right, left = done
    left = left & ~right
    if trachea is not None:
        right, left = right & ~trachea, left & ~trachea

    def full(mask):
        out = np.zeros(a.shape, dtype=bool)
        out[box] = mask
        return out

    return full(right), full(left), None if trachea is None else full(trachea)


@rp.segmentation("lungs")
def lungs(volume, ctx):
    a = _hu(volume)
    p = ctx.params
    right, left, trachea = _segment_lungs(
        volume, a, p["upper_hu"], p["closing_mm"], p["smooth_mm"], p["trachea"], ctx.progress
    )
    labels = np.zeros(a.shape, dtype=np.uint8)
    labels[right] = 1
    labels[left] = 2
    names = ["Right lung", "Left lung"]
    if trachea is not None:
        labels[trachea] = 3
        names.append("Trachea")
    return labels, names


def _words(name):
    return " ".join(name.lower().replace("_", " ").replace("-", " ").split())


def _masks_from_segments(volume, segments):
    """Lung masks from the series' segments, by name: (right, left, lobes, names used, split) or None;
    ``split`` is True when one whole-lungs segment was cut in two. Understands
    'Right lung', 'left lung mask', 'lung_upper_lobe_left' (TotalSegmentator, MONAI), 'right upper lobe'; one segment
    named 'lungs' is split into two."""
    sides = {"right": None, "left": None}
    lobes, used, whole = [], [], None
    for s in segments or []:
        name = _words(s.name)
        words = name.split()
        if name in WHOLE_LUNGS:
            whole = s
            continue
        if any(bad in name for bad in NOT_A_LUNG) or not ("lung" in name or "lobe" in words):
            continue
        side = "right" if "right" in words else "left" if "left" in words else None
        if side is None:
            continue
        mask = s.mask()
        sides[side] = mask if sides[side] is None else sides[side] | mask
        used.append(s.name)
        if "lobe" in words:
            lobes.append((s.name, side, mask))
    if sides["right"] is None and sides["left"] is None:
        if whole is None:
            return None
        lr_axis, lr_sign = _left_right_axis(volume)
        low, high = _split_lungs(whole.mask(), _spacing_zyx(volume), lr_axis)
        right, left = (low, high) if lr_sign > 0 else (high, low)
        return right, left, [], [whole.name], True
    shape = (volume.dims[2], volume.dims[1], volume.dims[0])
    right = sides["right"] if sides["right"] is not None else np.zeros(shape, dtype=bool)
    left = sides["left"] if sides["left"] is not None else np.zeros(shape, dtype=bool)
    return right, left & ~right, lobes, used, False


def _limits(ctx):
    """The four class limits, from the window's sliders once it has them, else from the parameters; kept inside the
    sliders' range and in rising order (a limit below the one before it is raised to it)."""
    values = [ctx.controls.get(n, ctx.params.get(n, d)) for n, d in zip(LIMIT_PARAMS, LIMIT_DEFAULTS)]
    values = np.clip(np.asarray(values, dtype=np.float64), *LIMIT_RANGE)
    return [float(v) for v in np.maximum.accumulate(values)]


def _row(name, counts, voxel_ml, bullae):
    """One line of the extension's extended results table. ``counts``: voxels per class."""
    emphysema, inflated, infiltrated, collapsed, vessels = (float(c) * voxel_ml for c in counts)
    # As upstream: the vessels are not part of the lung volume the percentages refer to.
    total = emphysema + inflated + infiltrated + collapsed
    functional = inflated + (0.0 if bullae else emphysema)
    affected = infiltrated + collapsed + (emphysema if bullae else 0.0)

    def percent(v):
        return round(100.0 * v / total, 1) if total else 0.0

    row = [name, round(total, 1)]
    for v in (functional, emphysema, inflated, infiltrated, collapsed, affected):
        row += [round(v, 1), percent(v)]
    return row + [round(vessels, 1), round(affected / functional, 3) if functional else None]


@rp.tool("analyze")
def analyze(volume, ctx):
    a = _hu(volume)
    limits = _limits(ctx)
    bullae = bool(ctx.controls.get("count_bullae", False))
    sampling = _spacing_zyx(volume)
    voxel_ml = sampling[0] * sampling[1] * sampling[2] / 1000.0

    found = _masks_from_segments(volume, ctx.segments)
    if found is not None:
        right, left, lobes, used, split = found
        names = ", ".join(used)[:900]
        if split:
            message = rp.tr(
                "Lung masks: segment {names} split in two. "
                "Not clinically evaluated: do not base treatment decisions on these values.", names=names
            )
        else:
            message = rp.tr(
                "Lung masks: segments {names}. "
                "Not clinically evaluated: do not base treatment decisions on these values.", names=names
            )
    else:
        # The extension's own defaults for the threshold path (LungCTSegmenter.py).
        right, left, _ = _segment_lungs(volume, a, -400.0, 12.0, 2.0, True, ctx.progress)
        lobes = []
        message = rp.tr(
            "Lung masks: made by thresholding (the series has no segment named right / left lung or lobe). "
            "Not clinically evaluated: do not base treatment decisions on these values."
        )
    if not right.any() and not left.any():
        raise ValueError("The lung segments are empty: segment the lungs first, or delete the empty segments.")

    ctx.progress(0.9, rp.tr("Classifying"))
    # 1..5 right, 6..10 left; np.digitize gives the class with limits[i-1] <= HU < limits[i]. Upstream sets the
    # lower emphysema limit to the volume's minimum and its upper vessel limit (3000 HU) has no effect, so every
    # voxel of the masks that holds data gets a class.
    labels = np.zeros(a.shape, dtype=np.uint8)
    for offset, mask in ((0, right), (5, left)):
        values = a[mask]
        cls = np.where(np.isnan(values), 0, np.digitize(values, limits) + 1 + offset)
        labels[mask] = cls.astype(np.uint8)
    counts = np.bincount(labels.ravel(), minlength=11)
    right_counts, left_counts = counts[1:6], counts[6:11]

    header = [
        rp.tr("Lung area"), rp.tr("Total (ml)"),
        rp.tr("Functional (ml)"), rp.tr("Functional (%)"),
        rp.tr("Emphysema (ml)"), rp.tr("Emphysema (%)"),
        rp.tr("Inflated (ml)"), rp.tr("Inflated (%)"),
        rp.tr("Infiltrated (ml)"), rp.tr("Infiltrated (%)"),
        rp.tr("Collapsed (ml)"), rp.tr("Collapsed (%)"),
        rp.tr("Affected (ml)"), rp.tr("Affected (%)"),
        rp.tr("Vessels (ml)"), rp.tr("AF-Q (affected / functional)"),
    ]
    table = [
        header,
        _row(rp.tr("Total lungs"), right_counts + left_counts, voxel_ml, bullae),
        _row(rp.tr("Right lung"), right_counts, voxel_ml, bullae),
        _row(rp.tr("Left lung"), left_counts, voxel_ml, bullae),
    ]
    for name, side, mask in lobes:
        inside = labels[mask & (right if side == "right" else left)]
        per_class = np.bincount((inside[inside > 0] - 1) % 5, minlength=5)
        table.append(_row(name, per_class, voxel_ml, bullae))

    x = np.arange(1, 6, dtype=np.float64)
    in_lungs = a[labels > 0]
    hist, edges = np.histogram(in_lungs, bins=np.arange(-1100.0, 210.0, 10.0))
    plots = [
        rp.Plot(
            rp.tr("Volume per class"),
            [
                rp.Series(rp.tr("Right lung"), x - 0.2, right_counts * voxel_ml, kind="bars"),
                rp.Series(rp.tr("Left lung"), x + 0.2, left_counts * voxel_ml, kind="bars"),
            ],
            x_label=rp.tr("1 emphysema, 2 inflated, 3 infiltrated, 4 collapsed, 5 vessels"),
            y_label=rp.tr("ml"),
        ),
        rp.Plot(
            rp.tr("Density inside the lung masks"),
            [rp.Series(rp.tr("Voxels"), 0.5 * (edges[:-1] + edges[1:]), hist * voxel_ml, kind="line")],
            x_label=rp.tr("HU (10 HU bins)"),
            y_label=rp.tr("ml"),
        ),
    ]

    limit_labels = (
        rp.tr("Emphysema below (HU)"), rp.tr("Inflated below (HU)"), rp.tr("Infiltrated below (HU)"),
        rp.tr("Collapsed below (HU)"),
    )
    controls = [
        rp.Slider(n, label, v, LIMIT_RANGE[0], LIMIT_RANGE[1], step=1)
        for n, label, v in zip(LIMIT_PARAMS, limit_labels, limits)
    ]
    controls += [
        rp.Checkbox(
            "count_bullae", rp.tr("Count emphysema as affected"), bullae, help=rp.tr("Off: emphysema counts as functional")
        ),
        rp.Button(
            "segments", rp.tr("Add segments"), help=rp.tr("One segment per class and lung, with the limits shown")
        ),
    ]

    result = rp.Result(
        table=table,
        plots=plots,
        controls=controls,
        message=message,
    )
    # Segments are added on every run that returns them: only on the first run and on the button, not per slider move.
    if ctx.event in (None, "segments"):
        result.labels = (labels, ["%s %s" % (c, side) for side in ("right", "left") for c in CLASSES])
    return result

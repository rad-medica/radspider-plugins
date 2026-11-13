"""Density lung segmentation, after the 3D Slicer extension DensityLungSegmentation (P. Zaffino et al., Apache-2.0).

Own implementation with numpy and scipy of what LungCTGMMSegmentation/LungCTGMMSegmentation.py does: a lung mask
(threshold, opening, islands, closing), then a fixed 5-component Gaussian mixture on the Hounsfield values inside
it. The mixture's weights, means and variances below are the numbers stored in the extension's
Resources/GMM_parameters_COVID-19.joblib; having them here as constants means no pickle is loaded and scikit-learn
is not needed. Research use, not clinically evaluated.
"""

import numpy as np
from scipy import ndimage

import radspider_plugin as rp

NAMES = ["Air", "Healthy lungs", "Ground glass opacity", "Consolidation", "Other denser tissues"]

# (weight, mean HU, variance HU^2) by rising mean = label 1..5, from GMM_parameters_COVID-19.joblib (SHA-256
# 05297cce...2adc12): weights_, means_, covariances_ of a 1-D sklearn GaussianMixture with 5 components.
GMM = (
    (0.33915990642224586, -950.3544500042553, 1936.6595291347662),
    (0.3616389523334142, -828.9766503995246, 3413.06554291841),
    (0.13880556972106453, -652.2653037063887, 8927.180354615342),
    (0.054676443906238506, -337.0348141143251, 24547.223946213202),
    (0.10571912709486199, -12.538960369867898, 37633.97437359867),
)

CLOSING_RADII = (30, 20)  # voxels, one closing after the other, as upstream
MEDIAN_SIZE = 4  # voxels, the "averaged" output


def _hu(volume):
    if volume.unit != "HU":
        raise ValueError(
            "This needs a CT in Hounsfield units; the series is in %s. Run it on a CT series."
            % (volume.unit or "no known unit")
        )
    a = volume.numpy().copy()
    # Upstream clips at -1000 before anything else; no data (NaN) is treated as air outside the patient.
    a[np.isnan(a) | (a < -1000.0)] = -1000.0
    return a


def _bbox(mask, margin):
    """Slices of the bounding box of a non-empty mask, grown by ``margin`` voxels per axis, clipped to the array."""
    out = []
    for axis in range(3):
        other = tuple(a for a in range(3) if a != axis)
        hit = np.nonzero(mask.any(axis=other))[0]
        out.append(slice(max(0, int(hit[0]) - margin[axis]), min(mask.shape[axis], int(hit[-1]) + 1 + margin[axis])))
    return tuple(out)


def _ball_close(mask, radius):
    """Closing with a ball of ``radius`` voxels as two Euclidean distance transforms (a 61-voxel ball as a plain
    dilation + erosion would take hours). Zero padding wider than the ball keeps the erosion from being cut at the
    border, as SimpleITK's safe border does."""
    pad = radius + 1
    crop = np.pad(mask, pad)
    grown = ndimage.distance_transform_edt(~crop) <= radius
    closed = ndimage.distance_transform_edt(grown) > radius
    return closed[pad:-pad, pad:-pad, pad:-pad]


def _lung_mask(a, threshold, min_voxels, progress):
    """Upstream's lung mask: air below the threshold, opened three times, the islands of at least ``min_voxels``
    whose bounding box stays clear of the first and last row and column, closed with balls of 30 and 20 voxels."""
    progress(0.05, "Threshold and opening")
    air = ndimage.binary_opening(a < threshold, iterations=3)
    progress(0.25, "Islands")
    lab, n = ndimage.label(air)
    sizes = np.bincount(lab.ravel())
    lungs = np.zeros(a.shape, dtype=bool)
    # Upstream's loop stops one label short (range(nb_labels) over labels 0..nb_labels); every island is looked at
    # here, so the last one is not lost.
    for i, box in enumerate(ndimage.find_objects(lab), 1):
        if sizes[i] < min_voxels:
            continue
        rows, columns = box[1], box[2]
        if rows.start == 0 or columns.start == 0 or rows.stop == a.shape[1] or columns.stop == a.shape[2]:
            continue  # reaches the edge of the image: the air around the patient
        lungs[box] |= lab[box] == i
    if not lungs.any():
        raise ValueError(
            "No lung found: no region below %g HU of at least %d voxels that stays clear of the image's edges. "
            "On a small or thick-slice series lower 'Smallest lung island'; otherwise check this is a chest CT."
            % (threshold, min_voxels)
        )
    box = _bbox(lungs, (0, 0, 0))
    closed = lungs[box]
    for n, radius in enumerate(CLOSING_RADII):
        progress(0.4 + 0.2 * n, "Closing, %d voxels" % radius)
        closed = _ball_close(closed, radius)
    if closed.sum() <= 1000:
        raise ValueError("Lung mask of 1000 voxels or fewer after closing: this is not a usable chest CT.")
    out = np.zeros(a.shape, dtype=bool)
    out[box] = closed
    return out


def _classify(values):
    """Label 1..5 of the most likely mixture component for each HU value (what GaussianMixture.predict returns,
    renumbered by rising mean)."""
    labels = np.zeros(values.shape, dtype=np.uint8)
    best = np.full(values.shape, -np.inf)
    x = values.astype(np.float64)
    for k, (weight, mean, variance) in enumerate(GMM, 1):
        score = np.log(weight) - 0.5 * np.log(variance) - 0.5 * (x - mean) ** 2 / variance
        better = score > best
        labels[better] = k
        best[better] = score[better]
    return labels


def _median(labels, mask):
    """4 x 4 x 4 median of the labels. Only the box around the mask is filtered: beyond 4 voxels from it every
    window is all background."""
    box = _bbox(mask, (MEDIAN_SIZE,) * 3)
    out = np.zeros_like(labels)
    out[box] = ndimage.median_filter(labels[box], MEDIAN_SIZE)
    return out


def _segment(volume, ctx, averaged):
    a = _hu(volume)
    mask = _lung_mask(a, ctx.params["lung_threshold"], int(ctx.params["min_island_voxels"]), ctx.progress)
    ctx.progress(0.8, "Mixture classes")
    labels = np.zeros(a.shape, dtype=np.uint8)
    labels[mask] = _classify(a[mask])
    if averaged:
        ctx.progress(0.9, "Median filter")
        labels = _median(labels, mask)
    return a, labels


@rp.segmentation("gmm")
def gmm(volume, ctx):
    return _segment(volume, ctx, False)[1], NAMES


@rp.segmentation("gmm_averaged")
def gmm_averaged(volume, ctx):
    return _segment(volume, ctx, True)[1], NAMES


@rp.tool("volumes")
def volumes(volume, ctx):
    averaged = ctx.params["averaged"] >= 0.5
    a, labels = _segment(volume, ctx, averaged)
    voxel_ml = volume.spacing[0] * volume.spacing[1] * volume.spacing[2] / 1000.0
    counts = np.bincount(labels.ravel(), minlength=6)[1:6]
    sums = np.bincount(labels.ravel(), weights=a.ravel(), minlength=6)[1:6]
    total = int(counts.sum())
    table = [["Class", "Volume (ml)", "Share of the lung mask (%)", "Mean HU"]]
    for name, count, s in zip(NAMES, counts, sums):
        table.append([
            name,
            round(float(count) * voxel_ml, 1),
            round(100.0 * count / total, 1) if total else 0.0,
            round(float(s) / count, 1) if count else None,
        ])
    table.append(["Lung mask", round(total * voxel_ml, 1), 100.0 if total else 0.0, None])
    plot = rp.Plot(
        "Volume per class",
        [rp.Series("Volume", np.arange(1.0, 6.0), counts * voxel_ml, kind="bars")],
        x_label="1 air, 2 healthy lungs, 3 ground glass opacity, 4 consolidation, 5 other denser tissues",
        y_label="ml",
    )
    return rp.Result(
        table=table,
        plots=[plot],
        labels=(labels, NAMES),
        message="%s labels. The lung mask is closed with 30 and 20 voxel balls, so it holds vessels, hila and part of "
        "the mediastinum (class 5). Not clinically evaluated." % ("Averaged" if averaged else "Per-voxel"),
    )

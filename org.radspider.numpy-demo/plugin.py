"""Example plugin using numpy from its own venv."""

from collections import deque

import numpy as np

import radspider_plugin as rp


@rp.synth_node("zscore")
def zscore(volume, ctx):
    a = volume.numpy()
    valid = ~np.isnan(a)
    sd = a[valid].std() if valid.any() else 0.0
    if sd == 0:
        return np.full_like(a, np.nan)
    return (a - a[valid].mean()) / sd


@rp.segmentation("largest_above")
def largest_above(volume, ctx):
    a = volume.numpy() >= ctx.params["threshold"]
    labels = np.zeros(a.shape, dtype=np.int32)
    best, best_size, current = 0, 0, 0
    nz, ny, nx = a.shape
    for start in zip(*np.nonzero(a)):
        if labels[start]:
            continue
        current += 1
        size, todo = 0, deque([start])
        labels[start] = current
        while todo:
            z, y, x = todo.popleft()
            size += 1
            for dz, dy, dx in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                q = (z + dz, y + dy, x + dx)
                if 0 <= q[0] < nz and 0 <= q[1] < ny and 0 <= q[2] < nx and a[q] and not labels[q]:
                    labels[q] = current
                    todo.append(q)
        if size > best_size:
            best, best_size = current, size
        ctx.progress(min(0.99, current / 1000.0), rp.trn(current, "{n} region", "{n} regions"))
    return (labels == best).astype(np.uint8) if best else np.zeros(a.shape, np.uint8), ["Largest region"]


@rp.tool("percentiles")
def percentiles(volume, ctx):
    a = volume.numpy()
    a = a[~np.isnan(a)]
    rows = [[rp.tr("Percentile"), rp.tr("Value")]]
    for p in (5, 25, 50, 75, 95):
        rows.append([p, float(np.percentile(a, p)) if a.size else None])
    return rows

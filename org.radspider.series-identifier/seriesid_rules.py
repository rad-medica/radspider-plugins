"""Rules for org.radspider.series-identifier: pure Python, no radspider_plugin, no numpy."""

import math
from dataclasses import dataclass

AXIS_TOLERANCE_DEG = 10.0
_EPS = 1e-9

# DICOM patient axes: x = right -> left (sagittal normal), y = anterior -> posterior (coronal normal),
# z = feet -> head (axial normal).
# Order is the tie-break when the normal is equidistant from two axes: axial, then coronal, then sagittal.
_AXES = (("axial", (0.0, 0.0, 1.0)), ("coronal", (0.0, 1.0, 0.0)), ("sagittal", (1.0, 0.0, 0.0)))


@dataclass(frozen=True)
class Finding:
    """One conclusion. `result` and `explain` are English message ids; `evidence` is free-text data."""

    item: str  # series, plane, projection, region, laterality, contrast, model
    result: str
    evidence: str
    explain: tuple[str, ...]


def number(v):
    """First value of `v` as a finite float, or None."""
    if isinstance(v, (list, tuple)):
        if not v:
            return None
        v = v[0]
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(str(v).strip().split("\\")[0]) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def numbers(v):
    """All values of `v` as finite floats (strings split on backslash), or None if empty or any is invalid."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = [p for p in v.split("\\") if p.strip()]
    elif isinstance(v, (int, float)):
        v = [v]
    out = []
    for item in v:
        f = None if isinstance(item, (list, tuple)) else number(item)
        if f is None:
            return None
        out.append(f)
    return out or None


def text(v):
    """Stripped upper-case text of `v`; lists are backslash-joined. Empty or None gives None."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        parts = [t for t in (text(x) for x in v) if t]
        return "\\".join(parts) or None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = str(v).strip().upper()
    return s or None


def _unit(v):
    vec = numbers(v)
    if vec is None or len(vec) != 3:
        return None
    n = math.sqrt(sum(c * c for c in vec))
    return tuple(c / n for c in vec) if n > _EPS else None


def plane(row, col):
    """Classify the image plane from its row/column direction cosines.

    Returns (name, degrees_off_axis, nearest): `nearest` is the plane whose axis is closest to the normal and
    `degrees_off_axis` the angle to it. Within AXIS_TOLERANCE_DEG the name is `nearest`, otherwise "oblique".
    Missing or degenerate vectors give ("unknown", nan, "").
    """
    r, c = _unit(row), _unit(col)
    if r is None or c is None:
        return "unknown", math.nan, ""
    normal = (r[1] * c[2] - r[2] * c[1], r[2] * c[0] - r[0] * c[2], r[0] * c[1] - r[1] * c[0])
    n = math.sqrt(sum(x * x for x in normal))
    if n < _EPS:
        return "unknown", math.nan, ""
    best, best_cos = "", -1.0
    for name, axis in _AXES:
        cos = abs(sum(a * b for a, b in zip(normal, axis))) / n
        if cos > best_cos + _EPS:
            best, best_cos = name, cos
    deg = math.degrees(math.acos(min(1.0, best_cos)))
    return (best if deg <= AXIS_TOLERANCE_DEG + _EPS else "oblique"), deg, best

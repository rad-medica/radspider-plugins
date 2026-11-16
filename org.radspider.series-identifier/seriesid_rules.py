"""Rules for org.radspider.series-identifier: pure Python, no radspider_plugin, no numpy.

`identify` turns the tag values of the image on screen (keyed "gggg,eeee"), the series facts and the image
orientation into a list of `Finding`s. The data tables and explanations live in `seriesid_tables`.
"""

import math
import re
from dataclasses import dataclass

import seriesid_tables as T
from seriesid_tables import EXPLAIN, ITEMS, TAGS, all_result_ids, word_re

__all__ = ["EXPLAIN", "ITEMS", "TAGS", "Finding", "all_result_ids", "identify", "kernel_family", "number",
           "numbers", "plane", "text"]

AXIS_TOLERANCE_DEG = 10.0
_EPS = 1e-9

# DICOM patient axes: x = right -> left (sagittal normal), y = anterior -> posterior (coronal normal),
# z = feet -> head (axial normal).
# Order is the tie-break when the normal is equidistant from two axes: axial, then coronal, then sagittal.
_AXES = (("axial", (0.0, 0.0, 1.0)), ("coronal", (0.0, 1.0, 0.0)), ("sagittal", (1.0, 0.0, 0.0)))


@dataclass(frozen=True)
class Finding:
    """One conclusion.

    `result` and `explain` are English message ids (keys of EXPLAIN). `result` may be a template with `{name}`
    placeholders filled from `args` (pairs of name and data value, never words to translate); `english` renders it.
    `evidence` is free-text data.
    """

    item: str  # one of ITEMS
    result: str
    evidence: str
    explain: tuple[str, ...]
    args: tuple[tuple[str, str], ...] = ()

    @property
    def english(self):
        return self.result.format(**dict(self.args)) if self.args else self.result


def number(v):
    """First value of `v` as a finite float, or None."""
    if isinstance(v, (list, tuple)):
        if not v:
            return None
        v = v[0]
    if v is None or isinstance(v, (bool, bytes, bytearray, dict)):
        return None
    try:
        f = float(str(v).strip().split("\\")[0]) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def numbers(v):
    """All values of `v` as finite floats (strings split on backslash), or None if empty or any is invalid."""
    if v is None or isinstance(v, (bool, bytes, bytearray, dict)):
        return None
    if isinstance(v, str):
        v = [p for p in v.split("\\") if p.strip()]
    elif isinstance(v, (int, float)):
        v = [v]
    elif not isinstance(v, (list, tuple)):
        return None
    out = []
    for item in v:
        f = None if isinstance(item, (list, tuple)) else number(item)
        if f is None:
            return None
        out.append(f)
    return out or None


def text(v):
    """Stripped upper-case text of `v`; lists are backslash-joined, bytes decoded, NUL and space padding removed.

    None, empty, bool, NaN/inf and mappings give None.
    """
    if v is None or isinstance(v, (bool, dict)):
        return None
    if isinstance(v, (list, tuple)):
        parts = [t for t in (text(x) for x in v) if t]
        return "\\".join(parts) or None
    if isinstance(v, (bytes, bytearray)):
        try:
            v = bytes(v).decode("utf-8")
        except UnicodeDecodeError:
            v = bytes(v).decode("latin-1")
    elif isinstance(v, float):
        if not math.isfinite(v):
            return None
        if v.is_integer():
            v = int(v)
    s = str(v).strip(" \x00\t\r\n").upper()
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


# --- Tag access ----------------------------------------------------------------------------------------------------

IMAGE_TYPE, MANUFACTURER, SERIES_DESC, PROTOCOL = "0008,0008", "0008,0070", "0008,103E", "0018,1030"
BODY_PART, CONTRAST = "0018,0015", "0018,0010"
VIEW_POSITION, LATERALITY, IMAGE_LATERALITY, PATIENT_ORIENTATION = "0018,5101", "0020,0060", "0020,0062", "0020,0020"
PRIMARY_ANGLE, SECONDARY_ANGLE, KERNEL = "0018,1510", "0018,1511", "0018,1210"
SERIES_TYPE, UNITS = "0054,1000", "0054,1001"
SCANNING_SEQ, SEQ_VARIANT, SEQ_NAME, MR_ACQ = "0018,0020", "0018,0021", "0018,0024", "0018,0023"
TR, TE, TI, IMAGING_FREQ, ECHO_TRAIN, FLIP = "0018,0080", "0018,0081", "0018,0082", "0018,0084", "0018,0091", \
    "0018,1314"
DB_DT, B_VALUE = "0018,1318", "0018,9087"

# Tags whose presence says MR when ctx.series has no modality (Review Focus 5).
_MR_TAGS = (SCANNING_SEQ, SEQ_VARIANT, SEQ_NAME, MR_ACQ, TR, TE, TI, IMAGING_FREQ, ECHO_TRAIN, DB_DT, B_VALUE)


class _Tags:
    """Case-insensitive view of the tag dict with evidence formatting."""

    def __init__(self, tags):
        self._v = {}
        for k, v in (tags or {}).items():
            if isinstance(k, str):
                self._v[k.strip().upper()] = v

    def raw(self, tag):
        return self._v.get(tag)

    def text(self, tag):
        return text(self._v.get(tag))

    def number(self, tag):
        return number(self._v.get(tag))

    def words(self, tag):
        s = self.text(tag)
        return [w.strip() for w in s.split("\\") if w.strip()] if s else []

    def has(self, tag):
        return self.text(tag) is not None

    def ev(self, *tags):
        """'Name (gggg,eeee) = VALUE; ...' for each tag, 'missing' when absent."""
        parts = []
        for tag in tags:
            v = self.text(tag)
            parts.append(f"{TAGS[tag]} ({tag}) " + (f"= {v}" if v is not None else "missing"))
        return "; ".join(parts)


def _fmt(x):
    return str(int(round(x))) if abs(x - round(x)) < 1e-6 else f"{x:g}"


def _f(item, result, evidence, *extra, **args):
    """Finding whose explanation is the result itself plus `extra` ids."""
    return Finding(item, result, evidence, (result, *extra), tuple((k, str(v)) for k, v in args.items()))


def _search(pattern, s):
    return bool(s) and word_re(pattern).search(s) is not None


def _first(table, s):
    """First (pattern, value) of `table` whose pattern matches `s` as whole words."""
    if s:
        for pattern, value in table:
            if word_re(pattern).search(s):
                return value
    return None


def _description(t):
    """Series Description + Protocol Name, upper case, '_' read as a space."""
    parts = [t.text(SERIES_DESC), t.text(PROTOCOL)]
    return " | ".join(p for p in parts if p).replace("_", " ")


# --- Common rows ---------------------------------------------------------------------------------------------------


def _plane_row(row, col):
    name, deg, nearest = plane(row, col)
    if name == "unknown":
        return _f("plane", T.ND_GEOMETRY, "Image Orientation (Patient) missing or degenerate")
    if name == "oblique":
        return _f("plane", T.OBLIQUE_IDS[nearest], f"normal {deg:.1f}° from the {nearest} axis", deg=f"{deg:.0f}")
    return _f("plane", T.PLANE_IDS[name], f"normal {deg:.1f}° from the {name} axis")


def _region_row(t):
    part = t.text(BODY_PART)
    if part is None:
        return _f("region", T.ND_BODY_PART, t.ev(BODY_PART))
    key = part.replace(" ", "")
    if key in T.REGIONS:
        return _f("region", T.REGIONS[key], t.ev(BODY_PART))
    return _f("region", T.REGION_OTHER, t.ev(BODY_PART), part=part)


def _contrast_row(t, desc, allow_description=True):
    agent = t.text(CONTRAST)
    if agent is not None:
        return _f("contrast", T.CONTRAST_RECORDED, t.ev(CONTRAST), agent=agent)
    if allow_description and _post_contrast_words(desc):
        return _f("contrast", T.CONTRAST_DESCRIPTION, f"{t.ev(CONTRAST)}; description: {desc}")
    return _f("contrast", T.ND_CONTRAST, t.ev(CONTRAST))


def _post_contrast_words(desc):
    return _search(T.POST_CONTRAST_WORDS, desc) and not _search(T.CT_PHASE_WORDS[0][0], desc)


def _orientation_projection(t):
    """Frontal / lateral / axial from Patient Orientation principal letters (PS3.3 C.7.6.1.1.1), or None."""
    values = t.words(PATIENT_ORIENTATION)
    if len(values) != 2 or not all(values):
        return None
    pair = {values[0][0], values[1][0]}
    lr, ap, hf = pair & {"L", "R"}, pair & {"A", "P"}, pair & {"H", "F"}
    if lr and hf:
        return T.ORIENTATION_FRONTAL
    if ap and hf:
        return T.ORIENTATION_LATERAL
    if lr and ap:
        return T.ORIENTATION_AXIAL
    return None


# --- Modality ------------------------------------------------------------------------------------------------------


def _mg_code(code):
    """(view code, side from a prefix) for MG_VIEWS, accepting 'LMLO' / 'R CC' style prefixes; else (None, '')."""
    if not code:
        return None, ""
    c = code.replace(" ", "")
    if c in T.MG_VIEWS:
        return c, ""
    if c[:1] in T.MG_SIDES and c[1:] in T.MG_VIEWS:
        return c[1:], c[:1]
    return None, ""


def _modality(t, series):
    """(modality code or None, inference finding or None)."""
    m = text((series or {}).get("modality"))
    if m:
        return m, None
    present = [tag for tag in _MR_TAGS if t.has(tag)]
    if present:
        guess = "MR"
    elif t.has(UNITS) or t.has(SERIES_TYPE):
        guess, present = "PT", [tag for tag in (UNITS, SERIES_TYPE) if t.has(tag)]
    elif t.has(KERNEL):
        guess, present = "CT", [KERNEL]
    elif t.has(VIEW_POSITION):
        guess, present = ("MG" if _mg_code(t.text(VIEW_POSITION))[0] else "DX"), [VIEW_POSITION]
    elif t.has(PRIMARY_ANGLE) or t.has(SECONDARY_ANGLE):
        guess, present = "XA", [tag for tag in (PRIMARY_ANGLE, SECONDARY_ANGLE) if t.has(tag)]
    else:
        return None, None
    names = ", ".join(f"{TAGS[tag]} ({tag})" for tag in present)
    return guess, _f("series", T.MODALITY_INFERRED, f"ctx.series has no modality; present: {names}", modality=guess)


# --- CT ------------------------------------------------------------------------------------------------------------


def _vendor(manufacturer):
    return _first(T.MANUFACTURERS, manufacturer)


def kernel_family(manufacturer, kernel):
    """(family in bone|lung|soft|brain|other, or None; evidence) for a CT Convolution Kernel."""
    k, m = text(kernel), text(manufacturer)
    if k is None:
        return None, "Convolution Kernel missing"
    k = k.split("\\")[0]
    family = _first(T.KERNEL_WORDS, k)
    if family:
        return family, f"kernel {k}: name"
    vendor = _vendor(m)
    for pattern, fam in T.CT_KERNELS.get(vendor, ()):
        if re.fullmatch(pattern, k):
            return fam, f"kernel {k}: {vendor} naming"
    return None, f"kernel {k} not in the tables for manufacturer {m or 'missing'}"


def _ct(t, desc, row, col):
    out = []
    image_type = t.text(IMAGE_TYPE) or ""
    words = t.words(IMAGE_TYPE)
    if "LOCALIZER" in words:
        out.append(_f("series", T.CT_LOCALIZER, t.ev(IMAGE_TYPE)))
        name, _, _ = plane(row, col)
        if name == "unknown":
            out.append(_f("projection", T.ND_GEOMETRY, "Image Orientation (Patient) missing or degenerate"))
        elif name in T.LOCALIZER_VIEWS:
            out.append(_f("projection", T.LOCALIZER_VIEWS[name], f"image plane {name}"))
        else:
            out.append(_f("projection", T.ND_LOCALIZER, f"image plane {name}"))
        return out
    search = f"{image_type.replace(chr(92), ' ')} | {desc}"
    if words[:1] == ["DERIVED"]:
        derived = _first(T.CT_DERIVED_WORDS, search)
        if derived:
            out.append(_f("series", derived, f"{t.ev(IMAGE_TYPE)}; description: {desc or 'missing'}"))
    phase = _first(T.CT_PHASE_WORDS, desc)
    agent = t.text(CONTRAST)
    if phase:
        out.append(_f("series", phase, f"description: {desc}; {t.ev(CONTRAST)}"))
    elif agent is not None:
        out.append(_f("series", T.CT_PHASE_UNSTATED, f"{t.ev(CONTRAST)}; no phase word in the description"))
    else:
        out.append(_f("series", T.ND_CONTRAST, f"{t.ev(CONTRAST)}; no phase word in the description"))
    if _search(T.CT_DUAL_ENERGY_WORDS, search):
        out.append(_f("series", T.CT_DUAL_ENERGY, f"{t.ev(IMAGE_TYPE)}; description: {desc or 'missing'}"))
    kev = re.search(T.CT_KEV, desc or "")
    if kev:
        out.append(_f("series", T.CT_MONO, f"description: {desc}", kev=kev.group(1)))
    family, why = kernel_family(t.raw(MANUFACTURER), t.raw(KERNEL))
    if family:
        out.append(_f("series", T.KERNEL_IDS[family], f"{t.ev(KERNEL, MANUFACTURER)}; {why}"))
    elif t.has(KERNEL):
        out.append(_f("series", T.KERNEL_UNKNOWN, f"{t.ev(KERNEL, MANUFACTURER)}; {why}",
                      kernel=t.text(KERNEL)))
    else:
        out.append(_f("series", T.ND_KERNEL, t.ev(KERNEL)))
    if agent is not None:
        out.append(_contrast_row(t, desc))
    out.append(_plane_row(row, col))
    return out


# --- MR ------------------------------------------------------------------------------------------------------------


def _mr_kind(t, series, desc):
    """(result id, evidence) of the MR series kind."""
    words = set(t.words(IMAGE_TYPE))
    image_type = " ".join(sorted(words))
    names = " | ".join(p for p in (desc, (t.text(SEQ_NAME) or "").replace("_", " ")) if p)
    both = f"{image_type} | {names}"
    tr, te, ti, flip = t.number(TR), t.number(TE), t.number(TI), t.number(FLIP)
    seq = set(t.words(SCANNING_SEQ))
    timing = t.ev(TR, TE, TI, SCANNING_SEQ)
    post = t.has(CONTRAST) or _post_contrast_words(desc)

    if _search(T.MR_WORDS["eadc"], both):
        return T.MR["eadc"], f"{t.ev(IMAGE_TYPE)}; description: {names or 'missing'}"
    if _search(T.MR_WORDS["adc"], both):
        return T.MR["adc"], f"{t.ev(IMAGE_TYPE)}; description: {names or 'missing'}"
    if _search(T.MR_WORDS["fa"], image_type):
        return T.MR["fa"], t.ev(IMAGE_TYPE)

    s = series or {}
    b_values = numbers(s.get("b_values")) or []
    b_image = t.number(B_VALUE)
    directions = number(s.get("gradient_directions"))
    if ({"DIFFUSION", "TRACEW"} & words or (b_image or 0) > 0 or any(b > 0 for b in b_values)
            or _search(T.MR_WORDS["diffusion"], names)):
        ev = (f"{t.ev(IMAGE_TYPE, B_VALUE)}; series b-values "
              f"{', '.join(_fmt(b) for b in b_values) or 'missing'}; gradient directions "
              f"{_fmt(directions) if directions is not None else 'missing'}")
        if b_image is not None and b_image == 0:
            return T.MR["b0"], ev
        if "TRACEW" in words:
            return T.MR["trace"], ev
        if directions is not None and directions >= T.DTI_MIN_DIRECTIONS:
            return T.MR["dti"], ev
        if directions is not None and directions == T.TRACE_DIRECTIONS:
            return T.MR["trace"], ev
        return T.MR["dwi"], ev

    for key in ("perfusion", "tof", "pc"):
        if _search(T.MR_WORDS[key], names):
            return T.MR[key], f"description: {names}"
    if _search(T.MR_WORDS["mra"], names):
        return (T.MR["ce_mra"] if t.has(CONTRAST) or _search(r"CE ?-?MRA", names) else T.MR["mra"]), \
            f"description: {names}; {t.ev(CONTRAST)}"
    if _search(T.MR_WORDS["swi"], names):
        return T.MR["swi"], f"description: {names}"

    if ti is not None and ti > 0:
        if ti <= T.STIR_TI_MAX:
            return T.MR["stir"], timing
        if ti >= T.FLAIR_TI_MIN:
            return T.MR["flair"], timing
        return T.MR["t1_ir_post" if post else "t1_ir"], timing
    for key in ("flair", "stir", "t1ir"):
        if _search(T.MR_WORDS[key], names):
            rid = T.MR["t1_ir_post" if post else "t1_ir"] if key == "t1ir" else T.MR[key]
            return rid, f"{timing}; description: {names}"
    if _search(T.MR_WORDS["ssfp"], names):
        return T.MR["ssfp"], f"description: {names}"

    if "GR" in seq and te is not None:
        ev = f"{timing}; {t.ev(FLIP)}" if flip is not None else timing
        if te >= T.GRE_T2STAR_TE_MIN:
            return T.MR["t2star"], ev
        return T.MR["t1_gre_post" if post else "t1_gre"], ev
    if tr is not None and te is not None:
        if tr < T.TR_SHORT_MAX and te < T.TE_SHORT_MAX:
            return T.MR["t1_post" if post else "t1"], timing
        if tr >= T.TR_LONG_MIN and te >= T.TE_LONG_MIN:
            return T.MR["t2"], timing
        if tr >= T.TR_LONG_MIN and te < T.TE_SHORT_MAX:
            return T.MR["pd"], timing
    keyword = _first(((T.MR_WORDS["t2star"], "t2star"), (T.MR_WORDS["t1"], "t1"), (T.MR_WORDS["t2"], "t2"),
                      (T.MR_WORDS["pd"], "pd")), names)
    if keyword:
        if keyword == "t1" and post:
            keyword = "t1_post"
        return T.MR[keyword], f"{timing}; description: {names}"
    if tr is not None and te is not None:
        return T.ND_TR_TE_RANGE, timing
    return T.ND_TR_TE, timing


def _mr(t, series, desc, row, col):
    kind, ev = _mr_kind(t, series, desc)
    out = [_f("series", kind, ev)]
    acq = t.text(MR_ACQ)
    if acq in ("2D", "3D"):
        out.append(_f("series", T.MR[acq.lower()], t.ev(MR_ACQ)))
    if kind != T.MR["stir"] and _search(T.MR_WORDS["fatsat"], desc):
        out.append(_f("series", T.MR["fatsat"], f"description: {desc}"))
    out.append(_contrast_row(t, desc))
    out.append(_plane_row(row, col))
    return out


# --- PET / NM ------------------------------------------------------------------------------------------------------


def _pt(t, desc, row, col):
    out = []
    image_type = (t.text(IMAGE_TYPE) or "").replace("\\", " ")
    search = f"{image_type} | {desc}"
    units = t.text(UNITS)
    if _search(T.PET_NAC_WORDS, search):
        out.append(_f("series", T.PET_NAC, f"{t.ev(IMAGE_TYPE)}; description: {desc or 'missing'}"))
    elif _search(T.PET_AC_WORDS, search):
        out.append(_f("series", T.PET_AC, f"{t.ev(IMAGE_TYPE)}; description: {desc or 'missing'}"))
    elif units in T.PET_UNITS_AC:
        out.append(_f("series", T.PET_AC, f"{t.ev(UNITS)}: quantitative units; no AC/NAC word"))
    elif units in T.PET_UNITS_NAC:
        out.append(_f("series", T.PET_NAC, f"{t.ev(UNITS)}: uncalibrated units; no AC/NAC word"))
    elif units is None:
        out.append(_f("series", T.ND_UNITS, f"{t.ev(UNITS)}; no AC/NAC word"))
    else:
        out.append(_f("series", T.PET_AC_UNSTATED, f"{t.ev(UNITS)}; no AC/NAC word"))
    if units is not None:
        if units in T.PET_UNITS:
            out.append(_f("series", T.PET_UNITS[units], t.ev(UNITS)))
        else:
            out.append(_f("series", T.PET_UNITS_OTHER, t.ev(UNITS), units=units))
    series_type = t.words(SERIES_TYPE)
    if series_type and series_type[0] in T.PET_SERIES_TYPES:
        out.append(_f("series", T.PET_SERIES_TYPES[series_type[0]], t.ev(SERIES_TYPE)))
    if "MIP" in t.words(IMAGE_TYPE):
        out.append(_f("plane", T.PET_MIP, t.ev(IMAGE_TYPE)))
    else:
        out.append(_plane_row(row, col))
    return out


def _nm(t, desc, row, col):
    out = []
    values = t.words(IMAGE_TYPE)
    kind = values[2] if len(values) >= 3 else None
    if kind is None:
        out.append(_f("series", T.ND_IMAGE_TYPE, t.ev(IMAGE_TYPE) + " (value 3 needed)"))
    elif kind in T.NM_KINDS:
        out.append(_f("series", T.NM_KINDS[kind], t.ev(IMAGE_TYPE)))
    else:
        out.append(_f("series", T.NM_KIND_UNKNOWN, t.ev(IMAGE_TYPE), kind=kind))
    if kind is not None and kind.startswith("RECON"):
        out.append(_plane_row(row, col))
        return out
    view = _first(T.NM_VIEW_WORDS, desc)
    if view:
        out.append(_f("projection", view, f"description: {desc}"))
        return out
    oriented = _orientation_projection(t)
    if oriented:
        out.append(_f("projection", oriented, t.ev(PATIENT_ORIENTATION)))
    else:
        out.append(_f("projection", T.NM_VIEW_UNKNOWN, f"{t.ev(PATIENT_ORIENTATION)}; description: "
                                                       f"{desc or 'missing'}"))
    return out


# --- Projection radiography, mammography, XA, US ---------------------------------------------------------------


def _xr(t, modality):
    out = [_f("series", T.XR_MODALITIES[modality], f"Modality {modality}")]
    code = t.text(VIEW_POSITION)
    if code is not None:
        code = code.replace(" ", "")
        if code in T.XR_VIEWS:
            out.append(_f("projection", T.XR_VIEWS[code], t.ev(VIEW_POSITION)))
        else:
            out.append(_f("projection", T.VIEW_UNKNOWN, t.ev(VIEW_POSITION), code=code))
    else:
        oriented = _orientation_projection(t)
        if oriented:
            out.append(_f("projection", oriented, t.ev(VIEW_POSITION, PATIENT_ORIENTATION)))
        else:
            out.append(_f("projection", T.ND_XR_VIEW, t.ev(VIEW_POSITION, PATIENT_ORIENTATION)))
    for tag in (IMAGE_LATERALITY, LATERALITY):
        side = t.text(tag)
        if side in T.LATERALITY:
            out.append(_f("laterality", T.LATERALITY[side], t.ev(tag)))
            break
    out.append(_region_row(t))
    return out


def _mg(t, desc):
    out = []
    search = f"{(t.text(IMAGE_TYPE) or '').replace(chr(92), ' ')} | {desc}"
    if _search(T.MG_SYNTHETIC_WORDS, search):
        out.append(_f("series", T.MG_SYNTHETIC, f"{t.ev(IMAGE_TYPE)}; description: {desc or 'missing'}"))
    elif _search(T.MG_TOMO_WORDS, search):
        out.append(_f("series", T.MG_TOMO, f"{t.ev(IMAGE_TYPE)}; description: {desc or 'missing'}"))
    else:
        out.append(_f("series", T.MG_SERIES, "Modality MG"))
    side_tag = next((tag for tag in (IMAGE_LATERALITY, LATERALITY) if t.text(tag) in T.MG_LATERALITY), None)
    side = t.text(side_tag) if side_tag else ""
    raw = t.text(VIEW_POSITION)
    code, prefix = _mg_code(raw)
    if not side and prefix:
        side, side_tag = prefix, VIEW_POSITION
    if raw is None:
        out.append(_f("projection", T.ND_VIEW, t.ev(VIEW_POSITION)))
    elif code is None:
        out.append(_f("projection", T.VIEW_UNKNOWN, t.ev(VIEW_POSITION), code=raw))
    else:
        ev = t.ev(VIEW_POSITION, side_tag) if side_tag and side_tag != VIEW_POSITION else t.ev(VIEW_POSITION)
        out.append(_f("projection", T.mg_view_id(code, side), ev))
    if side:
        out.append(_f("laterality", T.MG_LATERALITY[side], t.ev(side_tag)))
    else:
        out.append(_f("laterality", T.ND_LATERALITY, t.ev(IMAGE_LATERALITY, LATERALITY)))
    return out


def _xa(t, desc):
    out = [_f("series", T.XA_SERIES, "Modality XA")]
    primary, secondary = t.number(PRIMARY_ANGLE), t.number(SECONDARY_ANGLE)
    ev = t.ev(PRIMARY_ANGLE, SECONDARY_ANGLE)
    if primary is None:
        out.append(_f("projection", T.ND_PRIMARY, ev))
    elif secondary is None:
        out.append(_f("projection", T.ND_SECONDARY, ev))
    else:
        p, s = round(primary), round(secondary)
        side = "LAO" if p > 0 else "RAO" if p < 0 else ""
        tilt = "cranial" if s > 0 else "caudal" if s < 0 else ""
        args = {}
        if side:
            args["primary"] = abs(p)
        if tilt:
            args["secondary"] = abs(s)
        out.append(_f("projection", T.XA_VIEWS[(side, tilt)], ev, **args))
    if t.has(CONTRAST):
        out.append(_contrast_row(t, desc, allow_description=False))
    out.append(_region_row(t))
    return out


def _us(t, color):
    return [
        _f("series", T.US_COLOUR if color else T.US_GREY, "image is colour" if color else "image is greyscale"),
        _f("projection", T.US_NO_VIEW, "no standard tag holds the ultrasound view"),
        _region_row(t),
    ]


# --- Entry point ---------------------------------------------------------------------------------------------------


def identify(tags, series, row, col, color):
    """Findings for the image on screen.

    `tags`: tag values keyed "gggg,eeee" (any case); `series`: the ctx.series fields as a dict (modality, images,
    frames, phases, phase_axis, b_values, gradient_directions, image_types) or None; `row`, `col`: the image's
    direction cosines or None; `color`: whether the image is colour.
    """
    t = _Tags(tags)
    modality, inferred = _modality(t, series)
    out = [inferred] if inferred else []
    if modality is None:
        return [_f("series", T.ND_MODALITY, "ctx.series has no modality and no modality-specific tag is present")]
    desc = _description(t)
    if modality == "CT":
        out += _ct(t, desc, row, col)
        out.append(_region_row(t))
    elif modality == "MR":
        out += _mr(t, series, desc, row, col)
        out.append(_region_row(t))
    elif modality == "PT":
        out += _pt(t, desc, row, col)
        out.append(_region_row(t))
    elif modality == "NM":
        out += _nm(t, desc, row, col)
        out.append(_region_row(t))
    elif modality in T.XR_MODALITIES:
        out += _xr(t, modality)
    elif modality == "MG":
        out += _mg(t, desc)
    elif modality == "XA":
        out += _xa(t, desc)
    elif modality == "US":
        out += _us(t, color)
    else:
        out.append(_f("series", T.NO_RULES, f"Modality {modality}", modality=modality))
    return out

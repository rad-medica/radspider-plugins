"""Rules for org.radspider.series-identifier: pure Python, no radspider_plugin, no numpy.

`identify` turns the tag values of the image on screen (keyed "gggg,eeee"), the series facts and the image
orientation into a list of `Finding`s. The data tables and explanations live in `seriesid_tables`.
`features` builds the 28-value input of the dcm-classifier model (run by `seriesid_model`).
"""

import math
import re
from dataclasses import dataclass

import seriesid_tables as T
from seriesid_tables import (CT_KERNELS, CT_PHASE_WORDS, EXPLAIN, ITEMS, MG_VIEWS, MR_WORDS, NM_KINDS, TAGS,
                             XR_VIEWS, all_explain_ids, all_result_ids, explain_for, word_re)

__all__ = ["CT_KERNELS", "CT_PHASE_WORDS", "EXPLAIN", "FEATURES", "ITEMS", "MG_VIEWS", "MISSING", "MR_WORDS",
           "NM_KINDS", "TAGS", "XR_VIEWS", "Finding", "all_explain_ids", "all_result_ids", "bvalue", "explain_for",
           "features", "identify", "kernel_family", "number", "numbers", "plane", "series_class", "text"]

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


def _f(item, result, evidence, **args):
    """Finding whose explanation ids come from seriesid_tables.explain_for(result)."""
    return Finding(item, result, evidence, T.explain_for(result), tuple((k, str(v)) for k, v in args.items()))


def _search(pattern, s):
    return bool(s) and word_re(pattern).search(s) is not None


def _first(table, s):
    """First (pattern, value) of `table` whose pattern matches `s` as whole words."""
    if s:
        for pattern, value in table:
            if word_re(pattern).search(s):
                return value
    return None


class _Desc(str):
    """Description text for keywords (upper case, '_' read as a space) that remembers the tag it came from."""

    def __new__(cls, value, tag):
        obj = super().__new__(cls, (value or "").replace("_", " "))
        obj.tag = tag
        return obj


def _descriptions(t):
    """(kind text, series text).

    Kind keywords read Series Description; Protocol Name (exam-level, shared by every series of the exam) only when
    Series Description is missing. The series text is Series Description alone: Protocol Name never decides
    pre/post-contrast.
    """
    sd = t.text(SERIES_DESC)
    series_desc = _Desc(sd, SERIES_DESC)
    return (series_desc if sd else _Desc(t.text(PROTOCOL), PROTOCOL)), series_desc


def _dev(desc):
    """Evidence for a description text."""
    if not desc:
        return "Series Description (0008,103E) and Protocol Name (0018,1030) missing"
    return f"{TAGS[desc.tag]} ({desc.tag}) = {desc}"


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


def _contrast_row(t, series_desc, allow_description=True):
    agent = t.text(CONTRAST)
    if agent is not None:
        return _f("contrast", T.CONTRAST_RECORDED, t.ev(CONTRAST), agent=agent)
    if allow_description and _post_contrast_words(series_desc):
        return _f("contrast", T.CONTRAST_DESCRIPTION, f"{t.ev(CONTRAST)}; {_dev(series_desc)}")
    return _f("contrast", T.ND_CONTRAST, t.ev(CONTRAST))


def _post_contrast_words(series_desc):
    """Series Description says post-contrast and does not also say no or pre contrast."""
    return _search(T.POST_CONTRAST_WORDS, series_desc) and not _search(T.NEGATED_CONTRAST, series_desc)


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
    # A radiography code is never split into side + view ("LAT" is lateral, not Left + AT).
    if c not in T.XR_VIEWS and c[:1] in T.MG_SIDES and c[1:] in T.MG_VIEWS:
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


def _ct(t, desc, series_desc, row, col):
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
            out.append(_f("series", derived, f"{t.ev(IMAGE_TYPE)}; {_dev(desc)}"))
    phase = _first(T.CT_PHASE_WORDS, desc)
    agent = t.text(CONTRAST)
    if phase:
        out.append(_f("series", phase, f"{_dev(desc)}; {t.ev(CONTRAST)}"))
    elif agent is not None:
        out.append(_f("series", T.CT_PHASE_UNSTATED, f"{t.ev(CONTRAST)}; no phase word in the description"))
    else:
        out.append(_f("series", T.ND_CONTRAST, f"{t.ev(CONTRAST)}; no phase word in the description"))
    if _search(T.CT_DUAL_ENERGY_IMAGE_TYPE, " ".join(words)) or _search(T.CT_DUAL_ENERGY_WORDS, desc):
        out.append(_f("series", T.CT_DUAL_ENERGY, f"{t.ev(IMAGE_TYPE)}; {_dev(desc)}"))
    kev = re.search(T.CT_KEV, desc or "")
    if kev:
        out.append(_f("series", T.CT_MONO, f"{_dev(desc)}", kev=kev.group(1)))
    family, why = kernel_family(t.raw(MANUFACTURER), t.raw(KERNEL))
    if family:
        out.append(_f("series", T.KERNEL_IDS[family], f"{t.ev(KERNEL, MANUFACTURER)}; {why}"))
    elif t.has(KERNEL):
        out.append(_f("series", T.KERNEL_UNKNOWN, f"{t.ev(KERNEL, MANUFACTURER)}; {why}",
                      kernel=t.text(KERNEL)))
    else:
        out.append(_f("series", T.ND_KERNEL, t.ev(KERNEL)))
    if agent is not None:
        out.append(_contrast_row(t, series_desc))
    out.append(_plane_row(row, col))
    return out


# --- MR ------------------------------------------------------------------------------------------------------------


def _mr_kind(t, series, desc, series_desc):
    """(result id, evidence) of the MR series kind."""
    words = set(t.words(IMAGE_TYPE))
    names = " | ".join(p for p in (desc, (t.text(SEQ_NAME) or "").replace("_", " ")) if p)
    names_ev = f"{_dev(desc)}; {t.ev(SEQ_NAME)}" if t.has(SEQ_NAME) else _dev(desc)
    tr, te, ti, flip = t.number(TR), t.number(TE), t.number(TI), t.number(FLIP)
    seq = set(t.words(SCANNING_SEQ))
    timing = t.ev(TR, TE, TI, SCANNING_SEQ)
    post = t.has(CONTRAST) or _post_contrast_words(series_desc)

    # Diffusion maps: Image Type decides; the description only when Image Type says neither map nor diffusion
    # and no b-value is above 0 (a "DWI ADC" description on a DIFFUSION image is the diffusion series).
    for key in ("eadc", "adc", "fa"):
        if key.upper() in words:
            return T.MR[key], t.ev(IMAGE_TYPE)
    s = series or {}
    b_values = numbers(s.get("b_values")) or []
    b_image = t.number(B_VALUE)
    directions = number(s.get("gradient_directions"))
    diffusion_tags = bool({"DIFFUSION", "TRACEW"} & words) or (b_image or 0) > 0 or any(b > 0 for b in b_values)
    if not diffusion_tags:
        for key in ("eadc", "adc"):
            if _search(T.MR_WORDS[key], names):
                return T.MR[key], f"{t.ev(IMAGE_TYPE)}; {names_ev}"
    if diffusion_tags or _search(T.MR_WORDS["diffusion"], names):
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
            return T.MR[key], names_ev
    if _search(T.MR_WORDS["mra"], names):
        return (T.MR["ce_mra"] if t.has(CONTRAST) or _search(r"CE ?-?MRA", names) else T.MR["mra"]), \
            f"{names_ev}; {t.ev(CONTRAST)}"
    if _search(T.MR_WORDS["swi"], names):
        return T.MR["swi"], names_ev

    if ti is not None and ti > 0:
        if ti <= T.STIR_TI_MAX:
            return T.MR["stir"], timing
        if ti >= T.FLAIR_TI_MIN:
            return T.MR["flair"], timing
        return T.MR["t1_ir_post" if post else "t1_ir"], timing
    for key in ("t1flair", "flair", "stir", "t1ir"):
        if _search(T.MR_WORDS[key], names):
            rid = T.MR["t1_ir_post" if post else "t1_ir"] if key in ("t1ir", "t1flair") else T.MR[key]
            return rid, f"{timing}; {names_ev}"
    if _search(T.MR_WORDS["ssfp"], names):
        return T.MR["ssfp"], names_ev

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
        return T.MR[keyword], f"{timing}; {names_ev}"
    if tr is not None and te is not None:
        return T.ND_TR_TE_RANGE, timing
    return T.ND_TR_TE, timing


def _mr(t, series, desc, series_desc, row, col):
    kind, ev = _mr_kind(t, series, desc, series_desc)
    out = [_f("series", kind, ev)]
    acq = t.text(MR_ACQ)
    if acq in ("2D", "3D"):
        out.append(_f("series", T.MR[acq.lower()], t.ev(MR_ACQ)))
    if kind != T.MR["stir"] and _search(T.MR_WORDS["fatsat"], desc):
        out.append(_f("series", T.MR["fatsat"], f"{_dev(desc)}"))
    out.append(_contrast_row(t, series_desc))
    out.append(_plane_row(row, col))
    return out


# --- PET / NM ------------------------------------------------------------------------------------------------------


def _pt(t, desc, row, col):
    out = []
    image_type = (t.text(IMAGE_TYPE) or "").replace("\\", " ")
    search = f"{image_type} | {desc}"
    units = t.text(UNITS)
    if _search(T.PET_NAC_WORDS, search):
        out.append(_f("series", T.PET_NAC, f"{t.ev(IMAGE_TYPE)}; {_dev(desc)}"))
    elif _search(T.PET_AC_WORDS, search):
        out.append(_f("series", T.PET_AC, f"{t.ev(IMAGE_TYPE)}; {_dev(desc)}"))
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
        out.append(_f("projection", view, f"{_dev(desc)}"))
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
        out.append(_f("series", T.MG_SYNTHETIC, f"{t.ev(IMAGE_TYPE)}; {_dev(desc)}"))
    elif _search(T.MG_TOMO_WORDS, search):
        out.append(_f("series", T.MG_TOMO, f"{t.ev(IMAGE_TYPE)}; {_dev(desc)}"))
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
    elif code is None and raw.replace(" ", "") in T.XR_VIEWS:
        out.append(_f("projection", T.XR_VIEWS[raw.replace(" ", "")], t.ev(VIEW_POSITION)))
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
    desc, series_desc = _descriptions(t)
    if modality == "CT":
        out += _ct(t, desc, series_desc, row, col)
        out.append(_region_row(t))
    elif modality == "MR":
        out += _mr(t, series, desc, series_desc, row, col)
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


# --- dcm-classifier features ---------------------------------------------------------------------------------------
# Reference: BRAINSia/dcm-classifier at commit 5dcb37384572416da806db69c90bbabcec9819c9, src/dcm_classifier/; every
# `file:line` below is at that commit. The reference reads a pydicom Dataset of the first file of a volume. Here the
# values come from the host: numbers as float or list of floats, text as str with "\"-joined values, absent as None.
# `_element` turns them back into what pydicom would hold (one value, or a list for a multi-valued element).
# Not reproducible: the private b-value and gradient tags (the host refuses private tags), so only the standard
# b-value 0018,9087 is read, and 0018,9089 (Diffusion Gradient Orientation) stands in for the gradient tags.

MISSING = -12345  # dicom_config.py:24 MISSING_VALUE

# dicom_config.py:84-113 inference_features, in that order: the columns of the ONNX input.
FEATURES = (
    "Diffusionb-valueBool", "EchoTime", "EchoTrainLength", "FlipAngle", "HasDiffusionGradientOrientation",
    "ImageType_ADC", "ImageType_DERIVED", "ImageType_DIFFUSION", "ImageType_EADC", "ImageType_FA",
    "ImageType_ORIGINAL", "ImageType_TRACEW", "ImagingFrequency", "InversionTime", "Manufacturer_siemens",
    "NumberOfAverages", "PixelBandwidth", "RepetitionTime", "SAR", "ScanningSequence_GR", "ScanningSequence_IR",
    "ScanningSequence_SE", "SequenceVariant_MP", "SequenceVariant_SP", "dBdt", "has_b0", "has_pos_b0",
    "likely_diffusion",
)

# Classes the reference never rewrites from the b-values (image_type_inference.py:510).
DIFFUSION_CLASSES = ("tracew", "adc", "fa", "eadc", "dwig")

SLICE_THICKNESS, NUM_AVERAGES, PIXEL_BANDWIDTH = "0018,0050", "0018,0083", "0018,0095"
SAR_TAG, GRADIENT = "0018,1316", "0018,9089"

# Optional numbers: absent, None or not convertible by float() -> MISSING (utility_functions.py:517-535 SAR,
# :583-597, :637-666, :680-709, all through validate_numerical_dataset_element :757-774).
_OPTIONAL_NUMBERS = (("EchoTrainLength", ECHO_TRAIN), ("ImagingFrequency", IMAGING_FREQ), ("InversionTime", TI),
                     ("NumberOfAverages", NUM_AVERAGES), ("SAR", SAR_TAG), ("dBdt", DB_DT))

# The ImageType words are derived from FEATURES as the reference does (utility_functions.py:778-780): names containing
# "ADC" are excluded, they have their own branch.
_IMAGE_TYPE_WORDS = tuple(f for f in FEATURES if "ImageType_" in f and "ADC" not in f)
_CODED = (
    # (feature prefix, tag, default when absent or None)
    ("Manufacturer_", MANUFACTURER, "UnknownManufacturer"),  # utility_functions.py:536-548
    ("ScanningSequence_", SCANNING_SEQ, "UnknownScanningSequence"),  # :598-610
    ("SequenceVariant_", SEQ_VARIANT, "UnknownSequenceVariant"),  # :611-623
)


def _element(v):
    """The value as pydicom holds it: None, a single value, or a list when the element has several values."""
    if isinstance(v, (list, tuple)):
        if not v:
            return None
        return v[0] if len(v) == 1 else list(v)
    if isinstance(v, str) and "\\" in v:
        return v.split("\\")
    return v


def _is_number(v):
    """utility_functions.py:134-150 is_number: float() succeeds (on a list, as on a pydicom MultiValue, it fails)."""
    try:
        float(v)
    except Exception:
        return False
    return True


def _empty(v):
    return v is None or str(v).strip() == ""


def _lower_str(t, tag, default):
    """`str(value).lower()` as the reference tests it (utility_functions.py:818, 848, 856, 864).

    `default` replaces an absent or None value only (:537, :550, :599, :612); a present but empty value stays "".
    pydicom's str() of a MultiValue is the list repr; of a single value, the value itself.
    """
    v = t.raw(tag)
    if v is None:
        return default.lower()
    v = _element(v)
    if v is None:
        return ""
    return (str([str(x) for x in v]) if isinstance(v, list) else str(v)).lower()


def _bvalue(t):
    v = _element(t.raw(B_VALUE))
    if v is None:
        return MISSING  # utility_functions.py:275-277
    try:
        b = float(v)  # a multi-valued element raises: MISSING (:291-293)
    except (TypeError, ValueError):
        return MISSING  # :282-290
    if b > 5000:
        return MISSING  # :280-281, tested before rounding
    if not math.isfinite(b):
        return MISSING  # the reference raises in round() here; no b-value is the safe reading
    # :294-295 Python round (half to even) of b / 10, times 10; int() at dicom_volume.py:454.
    return int(round(b / 10.0) * 10)


def bvalue(tags):
    """The b-value the reference derives from the standard tag 0018,9087 (utility_functions.py:191-297), or MISSING."""
    return _bvalue(_Tags(tags))


def _gradient_valid(t):
    """utility_functions.py:362-368: exactly 3 components and |norm - 1| <= 0.01 (ensure_magnitude_of_1, :300-311).

    The reference's standard tag is 0018,9076 (:328), a sequence; the vector it finds in practice comes from the
    private tags (:329-334). 0018,9089 is the standard vector the host can deliver, read in their place.
    """
    v = numbers(t.raw(GRADIENT))
    if v is None or len(v) != 3:
        return False
    return not abs(1 - math.sqrt(sum(c * c for c in v))) > 0.01


def features(tags, has_geometry, has_spacing):
    """The 28 model inputs in FEATURES order, or (None, reason) when the reference marks the volume INVALID.

    `tags` keyed "gggg,eeee" as for `identify`; `has_geometry`: the image has an Image Orientation; `has_spacing`:
    it has a pixel spacing. Returns (vector, None) or (None, "<Keyword> missing" / "<Keyword> not a number").
    """
    t = _Tags(tags)
    # Required fields in the order of dicom_config.py:45-56, checked as sanitize_dicom_dataset does
    # (utility_functions.py:458-506). StudyInstanceUID, SeriesInstanceUID and SeriesNumber are not among the tags
    # this plugin reads; a series loaded by the host has them.
    if not has_geometry:
        return None, "Image Orientation missing"
    pixel_bandwidth = _element(t.raw(PIXEL_BANDWIDTH))
    if _empty(pixel_bandwidth):
        return None, "PixelBandwidth missing"
    if not _is_number(pixel_bandwidth):
        return None, "PixelBandwidth not a number"  # :484-490
    f = {"PixelBandwidth": float(pixel_bandwidth)}
    for name, tag in (("EchoTime", TE), ("RepetitionTime", TR)):
        v = _element(t.raw(tag))
        if _empty(v):
            f[name] = MISSING  # :460-470: an absent or empty TE/TR is MISSING, not INVALID (ADC images)
        elif not _is_number(v):
            return None, f"{name} not a number"  # :471-474
        else:
            f[name] = float(v)
    flip = _element(t.raw(FLIP))
    if _empty(flip):
        return None, "FlipAngle missing"  # :501-504
    if not _is_number(flip):
        return None, "FlipAngle not a number"  # kept as text, float32 cast fails: image_type_inference.py:401-406
    f["FlipAngle"] = float(flip)
    if not has_spacing:
        return None, "Pixel Spacing missing"  # :491-499
    slice_thickness = _element(t.raw(SLICE_THICKNESS))
    if _empty(slice_thickness):
        return None, "SliceThickness missing"
    if not _is_number(slice_thickness):
        return None, "SliceThickness not a number"  # :484-490

    for name, tag in _OPTIONAL_NUMBERS:
        v = _element(t.raw(tag))
        f[name] = float(v) if v is not None and _is_number(v) else MISSING

    # ImageType (utility_functions.py:817-842): "eadc" wins over "adc"; the other words are plain substring tests,
    # so FAT, for one, sets ImageType_FA.
    image_type = _lower_str(t, IMAGE_TYPE, "UnknownImageType")  # default: :549-561
    adc = "adc" in image_type
    f["ImageType_EADC"] = int(adc and "eadc" in image_type)
    f["ImageType_ADC"] = int(adc and not f["ImageType_EADC"])
    for name in _IMAGE_TYPE_WORDS:
        f[name] = int(name[len("ImageType_"):].lower() in image_type)
    # Manufacturer, ScanningSequence, SequenceVariant (:847-870): substring tests on the lower-case text, so the
    # default "UnknownScanningSequence" contains "se" and a missing ScanningSequence gives ScanningSequence_SE = 1.
    for prefix, tag, default in _CODED:
        s = _lower_str(t, tag, default)
        for name in FEATURES:
            if name.startswith(prefix):
                f[name] = int(name[len(prefix):].lower() in s)

    # Diffusion (dicom_volume.py:453-475).
    b = _bvalue(t)
    f["Diffusionb-valueBool"] = 0 if b == MISSING else 1
    f["has_b0"] = int(b == 0)
    f["has_pos_b0"] = int(b > 0)
    f["HasDiffusionGradientOrientation"] = int(_gradient_valid(t))
    f["likely_diffusion"] = int(
        any(f[k] == 1 for k in ("ImageType_DIFFUSION", "ImageType_ADC", "ImageType_EADC", "ImageType_TRACEW",
                                "ImageType_FA", "HasDiffusionGradientOrientation"))
        or b > 0
    )
    return [f[name] for name in FEATURES], None


def series_class(label, series):
    """The model's class after the reference's series step (image_type_inference.py:504-511).

    `LOW_PROBABILITY_` is dropped (:506). When the series has a b-value > 0 and the class is not a diffusion class,
    the class becomes `dwig` with >= 3 distinct gradient directions, else `tracew` (utility_functions.py:398-402).
    The reference takes the b-value of the volume; here `series["b_values"]` (ctx.series) holds those of the series.
    """
    label = label.replace("LOW_PROBABILITY_", "")
    if label in DIFFUSION_CLASSES or not series:
        return label
    b_values = series.get("b_values")
    if not isinstance(b_values, (list, tuple)):
        b_values = [b_values]
    if not any(b is not None and b > 0 for b in (number(x) for x in b_values)):
        return label
    directions = number(series.get("gradient_directions"))
    return "dwig" if directions is not None and directions >= 3 else "tracew"

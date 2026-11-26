"""LI-RADS structured liver CT/MRI report: the user draws observations on a Couinaud schematic of the liver (api 8
sketch) in patients at high risk for hepatocellular carcinoma. Each observation gets its segment from where it sits,
its size and major features, the LI-RADS v2018 diagnostic category (computed from the diagnostic table, adjusted by
ancillary features) or the category the reader assigns before the table (LR-NC, LR-1, LR-2, LR-M, LR-TIV), and the
management of each category.

The viewer holds the marks; each mark's descriptors live in its ``data``. The editor below the schematic shows the
selected mark through controls named <key>_<mark id>; every run writes the controls present back into their mark.
The report is a two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

MAX_OBSERVATIONS = 9  # mark labels such as "O9 LRTIV" stay within the host's 8 characters

W, H = 460, 270  # schematic units: patient's right on the left of the image
OUTLINE = [[20, 100], [60, 45], [200, 32], [330, 40], [440, 72], [425, 112], [330, 158], [230, 205], [120, 236],
           [52, 206], [20, 150]]
CAUDATE = (245, 132, 16)  # segment I: centre x, y and radius

MODALITIES = [rp.tr("CT"), rp.tr("MRI with extracellular contrast"), rp.tr("MRI with hepatobiliary contrast")]
TABLE = rp.tr("Diagnostic table")
PATHS = [  # the steps of the v2018 algorithm before the diagnostic table, in order, then the table itself
    TABLE,
    rp.tr("LR-NC: not categorizable (image degradation or omission)"),
    rp.tr("LR-TIV: tumour in vein"),
    rp.tr("LR-1: definitely benign"),
    rp.tr("LR-2: probably benign"),
    rp.tr("LR-M: probably or definitely malignant, not HCC specific"),
]
APHE = [rp.tr("No arterial phase hyperenhancement"), rp.tr("Nonrim arterial phase hyperenhancement")]
FEATURES = [  # (control name, label): the additional major features
    ("washout", rp.tr("Nonperipheral washout")),
    ("capsule", rp.tr("Enhancing capsule")),
    ("growth", rp.tr("Threshold growth")),
]
ANCILLARY = [
    rp.tr("No ancillary features"),
    rp.tr("Ancillary features favouring malignancy"),
    rp.tr("Ancillary features favouring benignity"),
    rp.tr("Ancillary features favouring both (no adjustment)"),
]
CATEGORIES = {  # code: (name, management); management after the LI-RADS v2018 CT/MRI management table
    "LR-NC": (rp.tr("LR-NC: not categorizable"), rp.tr("Repeat or alternative diagnostic imaging in 3 months or less")),
    "LR-1": (rp.tr("LR-1: definitely benign"), rp.tr("Return to surveillance in 6 months")),
    "LR-2": (
        rp.tr("LR-2: probably benign"),
        rp.tr("Return to surveillance in 6 months; consider repeat diagnostic imaging in 6 months or less"),
    ),
    "LR-3": (
        rp.tr("LR-3: intermediate probability of malignancy"),
        rp.tr("Repeat or alternative diagnostic imaging in 3 to 6 months"),
    ),
    "LR-4": (
        rp.tr("LR-4: probably HCC"),
        rp.tr("Multidisciplinary discussion for tailored workup, which may include biopsy"),
    ),
    "LR-5": (rp.tr("LR-5: definitely HCC"), rp.tr("Multidisciplinary discussion for consensus management")),
    "LR-M": (
        rp.tr("LR-M: probably or definitely malignant, not HCC specific"),
        rp.tr("Multidisciplinary discussion for tailored workup, which often includes biopsy"),
    ),
    "LR-TIV": (
        rp.tr("LR-TIV: tumour in vein"),
        rp.tr("Multidisciplinary discussion for tailored workup, which may include biopsy"),
    ),
}
ORDER = ["LR-1", "LR-2", "LR-NC", "LR-3", "LR-4", "LR-5", "LR-M", "LR-TIV"]  # for the most worrying observation


def table_category(aphe, size, washout, capsule, growth):
    """LI-RADS v2018 diagnostic table: `aphe` nonrim arterial phase hyperenhancement, `size` in mm, the additional
    major features as booleans. Returns "LR-3", "LR-4" or "LR-5"."""
    extra = washout + capsule + growth
    if not aphe:
        if size < 20:
            return "LR-4" if extra >= 2 else "LR-3"
        return "LR-4" if extra >= 1 else "LR-3"
    if size < 10:
        return "LR-4" if extra >= 1 else "LR-3"
    if size < 20:
        if extra >= 2 or washout or growth:
            return "LR-5"
        return "LR-4" if capsule else "LR-3"
    return "LR-5" if extra >= 1 else "LR-4"


def adjust(code, ancillary):
    """Ancillary features: favouring malignancy upgrade by one up to LR-4 (never to LR-5); favouring benignity
    downgrade by one; both, or none, change nothing. `ancillary`: the English id of the option."""
    steps = ["LR-1", "LR-2", "LR-3", "LR-4", "LR-5"]
    i = steps.index(code)
    if ancillary == "Ancillary features favouring malignancy" and i < 3:
        return steps[i + 1]
    if ancillary == "Ancillary features favouring benignity" and i > 0:
        return steps[i - 1]
    return code


def inside(x, y, poly):
    """Even-odd point-in-polygon test."""
    hit = False
    for (xi, yi), (xj, yj) in zip(poly, poly[-1:] + poly[:-1]):
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
    return hit


def locate(x, y):
    """Couinaud segment of a point of the schematic, or None outside the liver. Vertical planes at x 110 (right
    hepatic vein), 200 (middle) and 290 (falciform); portal plane at y 135 on the right, y 105 on the left lobe."""
    if not inside(x, y, OUTLINE):
        return None
    cx, cy, r = CAUDATE
    if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
        return "I"
    if x >= 290:
        return "II" if y < 105 else "III"
    upper = y < 135
    if x < 110:
        return "VII" if upper else "VI"
    if x < 200:
        return "VIII" if upper else "V"
    return "IVa" if upper else "IVb"


def pick(c, name, options):
    """The option whose English id `c` holds for `name`, else the first."""
    return next((o for o in options if str(o) == c.get(name)), options[0])


def encode(value):
    """A control value as mark data: one-line strings, booleans as "1" / "0"."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return "%g" % value if isinstance(value, (int, float)) else str(value)


def size_of(data):
    """Largest diameter in mm from mark data, clamped to 0..300; anything unreadable is 0."""
    try:
        return min(max(float(data.get("size", 0)), 0.0), 300.0)
    except (TypeError, ValueError):
        return 0.0


KEYS = ["size", "path", "aphe", "ancillary"] + [k for k, _ in FEATURES]


def observation(data, rows):
    """Report rows of one observation appended to `rows`; returns its category code or None (no size yet)."""
    size = size_of(data)
    if size > 0:
        rows.append([rp.tr("Largest diameter"), "%g mm" % size])
    path = pick(data, "path", PATHS)
    if path is not TABLE:
        code = str(path).split(":")[0]
    else:
        aphe = pick(data, "aphe", APHE)
        rows.append([rp.tr("Arterial phase"), aphe])
        on = {k: data.get(k) == "1" for k, _ in FEATURES}
        rows += [[rp.tr("Additional major features"), label] for k, label in FEATURES if on[k]] or [
            [rp.tr("Additional major features"), rp.tr("None")]
        ]
        anc = pick(data, "ancillary", ANCILLARY)
        rows.append([rp.tr("Ancillary features"), anc])
        code = None
        if size > 0:
            code = adjust(table_category(str(aphe) == str(APHE[1]), size, on["washout"], on["capsule"], on["growth"]),
                          str(anc))
    rows.append([rp.tr("LI-RADS"), CATEGORIES[code][0] if code else rp.tr("Not assigned")])
    if code:
        rows.append([rp.tr("Management"), CATEGORIES[code][1]])
    return code


def editor(data, mid):
    """Controls describing observation `mid`, filled from its data; each is named <data key>_<mark id>."""
    def n(k):
        return "%s_%d" % (k, mid)

    size = size_of(data)
    path = pick(data, "path", PATHS)
    blocks = [rp.Row([rp.Number(n("size"), rp.tr("Largest diameter (mm)"), size, min=0, max=300, step=1),
                      rp.Choice(n("path"), rp.tr("Category"), PATHS, str(path))])]
    if path is TABLE:
        blocks += [
            rp.Choice(n("aphe"), rp.tr("Arterial phase"), APHE, str(pick(data, "aphe", APHE))),
            rp.Section(rp.tr("Additional major features"),
                       [rp.Checkbox(n(k), label, data.get(k) == "1") for k, label in FEATURES]),
            rp.Choice(n("ancillary"), rp.tr("Ancillary features"), ANCILLARY, str(pick(data, "ancillary", ANCILLARY))),
        ]
        if size <= 0:
            blocks.append(rp.Label(rp.tr("Enter the size: the diagnostic table needs it."), weak=True))
    return blocks


def schematic():
    """The liver outline, the three hepatic vein planes, the portal plane, the caudate lobe and segment names."""
    shapes = [
        {"kind": "polygon", "points": OUTLINE, "style": "area"},
        # plane lines clipped to the outline by hand (its edges at these x and y)
        {"kind": "line", "points": [[110, 41], [110, 231]], "style": "guide"},
        {"kind": "line", "points": [[200, 33], [200, 213]], "style": "guide"},
        {"kind": "line", "points": [[290, 38], [290, 176]], "style": "guide"},
        {"kind": "line", "points": [[21, 135], [290, 135]], "style": "guide"},
        {"kind": "line", "points": [[290, 105], [427, 105]], "style": "guide"},
        {"kind": "ellipse", "x": CAUDATE[0], "y": CAUDATE[1], "rx": CAUDATE[2], "ry": CAUDATE[2], "style": "guide"},
    ]
    for text, x, y, size in (("VII", 70, 96, 13), ("VIII", 155, 86, 13), ("IVa", 230, 86, 13), ("II", 350, 74, 13),
                             ("VI", 80, 181, 13), ("V", 155, 181, 13), ("IVb", 220, 171, 13), ("III", 330, 131, 13),
                             ("I", 245, 132, 11)):
        shapes.append({"kind": "text", "x": x, "y": y, "text": text, "style": "muted", "size": size})
    shapes.append({"kind": "text", "x": 230, "y": 256, "size": 10, "style": "muted",
                   "text": rp.tr("Patient's right on the left; horizontal lines: portal plane")})
    return shapes


TONES = {"LR-1": "ok", "LR-2": "ok", "LR-NC": "accent", "LR-3": "accent", "LR-4": "warn", "LR-5": "error",
         "LR-M": "error", "LR-TIV": "error"}


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    modality = pick(c, "modality", MODALITIES)
    rows = [[rp.tr("Exam"), modality]]
    risk = bool(c.get("at_risk", True))
    sketch = c.get("liver") or {"marks": [], "selected": None}
    marks = sorted(sketch.get("marks", []), key=lambda m: m["id"])
    if ctx.event == "delete":
        marks = [m for m in marks if m["id"] != sketch.get("selected")]
        sketch["selected"] = None
    selected = next((m for m in marks if m["id"] == sketch.get("selected")), None)
    for m in marks:  # editor controls are named by mark id, so an edit survives a selection change in flight
        names = {k: "%s_%d" % (k, m["id"]) for k in KEYS}
        if any(v in c for v in names.values()):
            m["data"] = {k: encode(c[v]) for k, v in names.items() if v in c}

    found, outside, count = [], False, 0
    for m in marks:
        data = m.setdefault("data", {})
        m["form"], m["segment"] = "circle", locate(m["x"], m["y"])
        if m["segment"] is None:
            outside = True
            m["label"], m["tone"], m["title"] = "?", "muted", None
            continue
        count += 1
        m["title"] = rp.tr("Observation {n}", n=count)
        code = None
        if risk:
            rows += [[m["title"], ""], [rp.tr("Segment"), m["segment"]]]
            code = observation(data, rows)
            found.append(code)
        m["label"] = "O%d %s" % (count, code.replace("-", "")) if code else "O%d" % count
        m["tone"] = TONES[code] if code else "accent"
    if not risk:
        rows.append([rp.tr("LI-RADS"), rp.tr("Not applicable: the patient is not in the LI-RADS population")])
    elif not found:
        rows.append([rp.tr("Observations"), rp.tr("None")])
    elif None in found:
        rows.append([rp.tr("Most worrying observation"), rp.tr("Not assigned: an observation has no category yet")])
    else:
        rows.append([rp.tr("Most worrying observation"), CATEGORIES[max(found, key=ORDER.index)][0]])
    comment = str(c.get("comment", "")).strip()
    if comment:
        rows.append([rp.tr("Comment"), comment])

    value = {"marks": [{k: m[k] for k in ("id", "x", "y", "r", "label", "tone", "form", "data")} for m in marks],
             "selected": selected["id"] if selected is not None else None}
    blocks = [
        rp.Choice("modality", rp.tr("Exam"), MODALITIES, str(modality)),
        rp.Checkbox("at_risk", rp.tr("Patient at high risk for HCC (cirrhosis, chronic hepatitis B, current or prior "
                                     "HCC)"), risk),
        rp.Sketch("liver", rp.tr("Liver segments (Couinaud)"), W, H, schematic(), value=value,
                  max_marks=MAX_OBSERVATIONS),
        rp.Label(rp.tr("Drag on the liver to draw an observation; click a mark to describe it."), weak=True),
    ]
    if outside:
        blocks.append(rp.Label(rp.tr("A mark outside the liver is not reported: move it or delete it."), weak=True))
    if selected is not None:
        head = [rp.Label(selected["title"] or rp.tr("Outside the schematic"))]
        if selected["title"] is not None:
            head.append(rp.Label(rp.tr("Segment {s}", s=selected["segment"]), weak=True))
        head.append(rp.Button("delete", rp.tr("Delete"), icon="trash"))
        blocks += [rp.Separator(), rp.Row(head)]
        if selected["title"] is not None and risk:
            blocks += editor(selected["data"], selected["id"])
    blocks += [
        rp.TextField("comment", rp.tr("Comment"), comment, max_length=500),
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(rows),
        rp.Label(
            rp.tr(
                "LI-RADS CT/MRI v2018 diagnostic algorithm. LR-NC, LR-TIV, LR-1, LR-2 and LR-M are the "
                "reader's call before the table; treated observations (LR-TR) are not covered. Not a medical "
                "device: check every line before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("LI-RADS report"), blocks, size=(560, 900))])

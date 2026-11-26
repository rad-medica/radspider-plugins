"""TI-RADS structured thyroid report: the user draws nodules on the thyroid and lymph nodes in the neck levels of a
schematic (api 8 sketch). Nodules are scored with ACR TI-RADS (Tessler et al., JACR 2017), lymph nodes classed with
ETA 2013, and an optional clinical TNM stage of differentiated thyroid carcinoma follows (AJCC 8th edition).

The viewer holds the marks; each mark's descriptors live in its ``data``. The editor below the schematic shows the
selected mark through controls named <key>_<mark id>; every run writes the controls present back into their mark. The report is a
two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

W, H = 460, 304  # schematic units: anterior view, patient's right on the left
LOBES = (195, 265)  # centre x of the right and left lobe ellipses (y 140, rx 26, ry 62)
THIRDS = (119, 161)  # y of the upper/middle and middle/lower third boundaries
ISTHMUS = (208, 160, 44, 22)  # x, y, w, h

LOCATIONS = [
    rp.tr("Right lobe, upper third"),
    rp.tr("Right lobe, middle third"),
    rp.tr("Right lobe, lower third"),
    rp.tr("Isthmus"),
    rp.tr("Left lobe, upper third"),
    rp.tr("Left lobe, middle third"),
    rp.tr("Left lobe, lower third"),
]
# (option, points), ACR TI-RADS 2017 chart. "Cannot be determined" rows as the chart scores them.
COMPOSITION = [
    (rp.tr("Solid or almost completely solid"), 2),
    (rp.tr("Mixed cystic and solid"), 1),
    (rp.tr("Cystic or almost completely cystic"), 0),
    (rp.tr("Spongiform"), 0),
    (rp.tr("Cannot be determined because of calcification"), 2),
]
ECHOGENICITY = [
    (rp.tr("Hypoechoic"), 2),
    (rp.tr("Very hypoechoic"), 3),
    (rp.tr("Hyperechoic or isoechoic"), 1),
    (rp.tr("Anechoic"), 0),
    (rp.tr("Echogenicity cannot be determined"), 1),
]
SHAPE = [(rp.tr("Wider-than-tall"), 0), (rp.tr("Taller-than-wide"), 3)]
MARGIN = [
    (rp.tr("Smooth"), 0),
    (rp.tr("Ill-defined"), 0),
    (rp.tr("Lobulated or irregular"), 2),
    (rp.tr("Extra-thyroidal extension"), 3),
    (rp.tr("Margin cannot be determined"), 0),
]
FEATURES = [("comp", rp.tr("Composition"), COMPOSITION), ("echo", rp.tr("Echogenicity"), ECHOGENICITY),
            ("shape", rp.tr("Shape"), SHAPE), ("margin", rp.tr("Margin"), MARGIN)]
DIAMETERS = [("ap", rp.tr("Anteroposterior (mm)")), ("tv", rp.tr("Transverse (mm)")), ("cc", rp.tr("Longitudinal (mm)"))]
FOCI = [  # (data key, label, points): echogenic foci add up; none or large comet-tail artifacts score 0
    ("macro", rp.tr("Macrocalcifications"), 1),
    ("rim", rp.tr("Peripheral (rim) calcifications"), 2),
    ("punctate", rp.tr("Punctate echogenic foci"), 3),
]
NO_FOCI = rp.tr("None or large comet-tail artifacts")
# Composition that makes a nodule TR1 with no further points (Tessler 2017: inherently benign).
BENIGN_COMPOSITION = ("Cystic or almost completely cystic", "Spongiform")

# TR level: (name, FNA from mm, follow-up from mm, follow-up schedule); Tessler 2017 recommendations.
LEVELS = {
    1: (rp.tr("TR1: benign"), None, None, None),
    2: (rp.tr("TR2: not suspicious"), None, None, None),
    3: (rp.tr("TR3: mildly suspicious"), 25, 15, rp.tr("Follow-up ultrasound at 1, 3 and 5 years")),
    4: (rp.tr("TR4: moderately suspicious"), 15, 10, rp.tr("Follow-up ultrasound at 1, 2, 3 and 5 years")),
    5: (rp.tr("TR5: highly suspicious"), 10, 5, rp.tr("Follow-up ultrasound every year for up to 5 years")),
}

NODE_STATES = [rp.tr("Normal"), rp.tr("Indeterminate"), rp.tr("Suspicious")]
NODE_LEVELS = [  # (key, label, short text, central: VI and VII give N1a, the lateral levels N1b, rect x y w h)
    ("r1", rp.tr("Right level I"), "I", False, (120, 14, 90, 40)),
    ("l1", rp.tr("Left level I"), "I", False, (250, 14, 90, 40)),
    ("r2", rp.tr("Right level II"), "II", False, (40, 62, 100, 58)),
    ("l2", rp.tr("Left level II"), "II", False, (320, 62, 100, 58)),
    ("r3", rp.tr("Right level III"), "III", False, (40, 124, 100, 58)),
    ("l3", rp.tr("Left level III"), "III", False, (320, 124, 100, 58)),
    ("r4", rp.tr("Right level IV"), "IV", False, (40, 186, 100, 58)),
    ("l4", rp.tr("Left level IV"), "IV", False, (320, 186, 100, 58)),
    ("r5", rp.tr("Right level V"), "V", False, (4, 62, 32, 182)),
    ("l5", rp.tr("Left level V"), "V", False, (424, 62, 32, 182)),
    ("c6", rp.tr("Level VI (central)"), "VI", True, (160, 226, 140, 34)),
    ("c7", rp.tr("Level VII (upper mediastinum)"), "VII", True, (160, 266, 140, 34)),
]
HILUM = ("hilum", rp.tr("Fatty hilum present"))
SIGNS = [  # ETA 2013 suspicious features: any one makes the node suspicious
    ("micro", rp.tr("Microcalcifications")),
    ("cystic", rp.tr("Cystic change")),
    ("vasc", rp.tr("Peripheral or diffuse increased vascularity")),
    ("hyper", rp.tr("Hyperechoic tissue like thyroid")),
]
OTHER = [("round", rp.tr("Round shape")), ("cvasc", rp.tr("Increased central vascularity"))]  # reported, not scored

NODULE_KEYS = [k for k, _ in DIAMETERS] + [k for k, _, _ in FEATURES] + [k for k, _, _ in FOCI]
NODE_KEYS = ["short", HILUM[0]] + [k for k, _ in SIGNS + OTHER]

STAGING = [rp.tr("Not staged"), rp.tr("Differentiated thyroid carcinoma (AJCC 8th edition)")]
EXTENSION = [
    rp.tr("Confined to the thyroid"),
    rp.tr("Gross extension into strap muscles"),
    rp.tr("Invasion of subcutaneous tissue, larynx, trachea, esophagus or recurrent laryngeal nerve"),
    rp.tr("Invasion of prevertebral fascia, or encasing the carotid artery or mediastinal vessels"),
]
AGES = [rp.tr("Younger than 55 years"), rp.tr("55 years or older")]
METASTASES = [rp.tr("M0: no distant metastases"), rp.tr("M1: distant metastases")]


def points(composition, echogenicity, shape, margin, foci):
    """ACR TI-RADS points of one nodule from the English ids of its options and the names of its foci."""
    if composition in BENIGN_COMPOSITION:
        return 0
    score = sum(
        dict((str(o), p) for o, p in table)[v]
        for table, v in ((COMPOSITION, composition), (ECHOGENICITY, echogenicity), (SHAPE, shape), (MARGIN, margin))
    )
    return score + sum(p for name, _, p in FOCI if name in foci)


def level(score):
    """TR level of a point total: 0 TR1, 2 TR2, 3 TR3, 4-6 TR4, 7+ TR5 (ACR chart). The chart has no 1-point row
    (mixed cystic and solid, anechoic, nothing else); only 0 points is TR1, so 1 point is TR2 here."""
    return 1 if score == 0 else 2 if score <= 2 else 3 if score == 3 else 4 if score <= 6 else 5


def advice(tr, size):
    """(FNA recommended, follow-up schedule or None) for TR level `tr` and maximum diameter `size` in mm."""
    _, fna, follow, schedule = LEVELS[tr]
    if fna is None or size <= 0:
        return False, None
    if size >= fna:
        return True, None
    return False, schedule if size >= follow else None


def t_category(size, extension):
    """AJCC 8 T of differentiated thyroid carcinoma from the largest diameter (mm) and the extension's English id."""
    gross = [str(e) for e in EXTENSION].index(extension)
    if gross:
        return ("T3b", "T4a", "T4b")[gross - 1]
    if size <= 0:
        return "TX"
    return "T1a" if size <= 10 else "T1b" if size <= 20 else "T2" if size <= 40 else "T3a"


def n_category(suspicious):
    """cN from the `central` flags of the suspicious nodes: a lateral one N1b, else a central one N1a, else N0."""
    return "N1b" if False in suspicious else "N1a" if suspicious else "N0"


def stage(t, n, old, m1):
    """AJCC 8 stage group of differentiated thyroid carcinoma; `old`: 55 years or older."""
    if not old:
        return "II" if m1 else "I"
    if m1:
        return "IVB"
    if t == "T4b":
        return "IVA"
    if t == "T4a":
        return "III"
    if t.startswith("T3") or n != "N0":
        return "II"
    return "I"


def locate(x, y):
    """("nodule", location index) on a lobe or the isthmus, ("node", NODE_LEVELS entry) in a level, else (None, None)."""
    for side, cx in enumerate(LOBES):
        if ((x - cx) / 26) ** 2 + ((y - 140) / 62) ** 2 <= 1:
            return "nodule", side * 4 + (0 if y < THIRDS[0] else 1 if y < THIRDS[1] else 2)
    ix, iy, iw, ih = ISTHMUS
    if ix <= x <= ix + iw and iy <= y <= iy + ih:
        return "nodule", 3
    for entry in NODE_LEVELS:
        lx, ly, lw, lh = entry[4]
        if lx <= x <= lx + lw and ly <= y <= ly + lh:
            return "node", entry
    return None, None


def node_state(data):
    """ETA 2013 class of a node's data: any suspicious feature, else no hilum = indeterminate, else normal."""
    if any(data.get(k) == "1" for k, _ in SIGNS):
        return "Suspicious"
    return "Normal" if data.get(HILUM[0], "1") == "1" else "Indeterminate"


def pick(c, name, options):
    """The option whose English id `c` holds for `name`, else the first."""
    return next((o for o in options if str(o) == c.get(name)), options[0])


def number(data, key, hi=150):
    """A diameter in mm from mark data (strings), clamped to 0..hi; anything unreadable is 0."""
    try:
        return min(max(float(data.get(key, 0)), 0.0), hi)
    except (TypeError, ValueError):
        return 0.0


def encode(value):
    """A control value as mark data: one-line strings, booleans as "1" / "0"."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return "%g" % value if isinstance(value, (int, float)) else str(value)


def nodule(data, rows):
    """Report rows of one nodule appended to `rows`; returns its TR level."""
    dims = [number(data, k) for k, _ in DIAMETERS]
    dims = [v for v in dims if v > 0]
    if dims:
        rows.append([rp.tr("Size"), " × ".join("%g" % v for v in dims) + " mm"])
    ids = []
    for key, label, table in FEATURES:
        value = pick(data, key, [o for o, _ in table])
        rows.append([label, value])
        ids.append(str(value))
    foci = [k for k, _, _ in FOCI if data.get(k) == "1"]
    rows += [[rp.tr("Echogenic foci"), label] for k, label, _ in FOCI if k in foci] or [[rp.tr("Echogenic foci"), NO_FOCI]]
    score = points(*ids, foci)
    tr = level(score)
    size = max(dims, default=0.0)
    fna, schedule = advice(tr, size)
    rows.append([rp.tr("ACR TI-RADS"), LEVELS[tr][0]])
    rows.append([rp.tr("Points"), score])
    if LEVELS[tr][1] is None:
        rows.append([rp.tr("Recommendation"), rp.tr("No FNA")])
    elif not dims:
        rows.append([rp.tr("Recommendation"), rp.tr("Enter the size to get the recommendation")])
    elif fna:
        rows.append([rp.tr("Recommendation"), rp.tr("FNA (from {mm} mm at this level)", mm=LEVELS[tr][1])])
    else:
        rows.append([rp.tr("Recommendation"), schedule or rp.tr("No FNA or follow-up for its size")])
    return tr


def editor(kind, data, mid):
    """Controls describing mark `mid`, filled from its data; each is named <data key>_<mark id>."""
    def n(k):
        return "%s_%d" % (k, mid)

    if kind == "nodule":
        def choice(k, label, t):
            return rp.Choice(n(k), label, [o for o, _ in t], str(pick(data, k, [o for o, _ in t])))

        return [
            rp.Row([rp.Number(n(k), label, number(data, k), min=0, max=150, step=1) for k, label in DIAMETERS]),
            rp.Row([choice(*f) for f in FEATURES[:2]]),
            rp.Row([choice(*f) for f in FEATURES[2:]]),
            rp.Section(rp.tr("Echogenic foci (all that apply)"),
                       [rp.Checkbox(n(k), label, data.get(k) == "1") for k, label, _ in FOCI]),
        ]
    return [
        rp.Row([rp.Number(n("short"), rp.tr("Short axis (mm)"), number(data, "short", 100), min=0, max=100, step=1),
                rp.Checkbox(n(HILUM[0]), HILUM[1], data.get(HILUM[0], "1") == "1")]),
        rp.Section(rp.tr("Suspicious features (ETA 2013)"),
                   [rp.Checkbox(n(k), label, data.get(k) == "1") for k, label in SIGNS]),
        rp.Section(rp.tr("Other findings (reported, not scored)"),
                   [rp.Checkbox(n(k), label, data.get(k) == "1") for k, label in OTHER]),
    ]


def schematic(worst):
    """The neck drawing: levels tinted by their worst node, the thyroid lobes with third guides, the isthmus."""
    tint = {"Normal": "area", "Indeterminate": "warn", "Suspicious": "error"}
    shapes = []
    for key, _, short, _, (x, y, w, h) in NODE_LEVELS:
        shapes.append({"kind": "rect", "x": x, "y": y, "w": w, "h": h, "style": tint[worst.get(key, "Normal")]})
        shapes.append({"kind": "text", "x": x + w / 2, "y": y + 9, "text": short, "style": "muted", "size": 10})
    for cx in LOBES:
        shapes.append({"kind": "ellipse", "x": cx, "y": 140, "rx": 26, "ry": 62, "style": "line"})
        shapes += [{"kind": "line", "points": [[cx - 26, y], [cx + 26, y]], "style": "guide"} for y in THIRDS]
    ix, iy, iw, ih = ISTHMUS
    shapes.append({"kind": "rect", "x": ix, "y": iy, "w": iw, "h": ih, "style": "line"})
    shapes.append({"kind": "text", "x": 80, "y": 34, "text": rp.tr("Right"), "style": "label", "size": 11})
    shapes.append({"kind": "text", "x": 380, "y": 34, "text": rp.tr("Left"), "style": "label", "size": 11})
    return shapes


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    sketch = c.get("neck") or {"marks": [], "selected": None}
    marks = sorted(sketch.get("marks", []), key=lambda m: m["id"])
    if ctx.event == "delete":
        marks = [m for m in marks if m["id"] != sketch.get("selected")]
        sketch["selected"] = None
    selected = next((m for m in marks if m["id"] == sketch.get("selected")), None)
    for m in marks:  # editor controls are named by mark id, so an edit survives a selection change in flight
        kind = locate(m["x"], m["y"])[0]
        keys = NODULE_KEYS if kind == "nodule" else NODE_KEYS if kind == "node" else []
        if any("%s_%d" % (k, m["id"]) in c for k in keys):
            m["data"] = {k: encode(c["%s_%d" % (k, m["id"])]) for k in keys if "%s_%d" % (k, m["id"]) in c}

    rows, nodes, worst, outside = [], [], {}, False
    nodules = 0
    for m in marks:
        kind, where = locate(m["x"], m["y"])
        data = m.setdefault("data", {})
        if kind == "nodule":
            nodules += 1
            m["form"], m["title"] = "circle", rp.tr("Nodule {n}", n=nodules)
            rows += [[m["title"], ""], [rp.tr("Location"), LOCATIONS[where]]]
            tr = nodule(data, rows)
            m["label"], m["tone"] = "N%d TR%d" % (nodules, tr), "error" if tr == 5 else "warn" if tr == 4 else "accent"
            m["where"] = LOCATIONS[where]
        elif kind == "node":
            nodes.append((m, where))
        else:
            outside = True
            m["label"], m["tone"], m["title"], m["where"] = "?", "muted", None, None
    if not nodules:
        rows.append([rp.tr("Thyroid nodules"), rp.tr("None")])

    rank = {"Normal": 0, "Indeterminate": 1, "Suspicious": 2}
    suspicious = []
    for k, (m, (key, label, _, central, _)) in enumerate(nodes, 1):
        data, state = m["data"], node_state(m["data"])
        if rank[state] > rank[worst.get(key, "Normal")]:
            worst[key] = state
        if state == "Suspicious":
            suspicious.append(central)
        m["form"], m["title"], m["where"] = "square", rp.tr("Lymph node {n}", n=k), label
        m["label"] = ("L%d %s" % (k, {"Normal": "", "Indeterminate": "I", "Suspicious": "S"}[state])).strip()
        m["tone"] = {"Normal": "ok", "Indeterminate": "warn", "Suspicious": "error"}[state]
        rows += [[m["title"], ""], [rp.tr("Level"), label]]
        if number(data, "short", 100):
            rows.append([rp.tr("Short axis"), "%g mm" % number(data, "short", 100)])
        rows.append([rp.tr("ETA 2013"), NODE_STATES[rank[state]]])
        rows += [[rp.tr("Suspicious feature"), lb] for s, lb in SIGNS if data.get(s) == "1"]
        rows += [[rp.tr("Other finding"), lb] for s, lb in OTHER if data.get(s) == "1"]
    if not nodes:
        rows.append([rp.tr("Cervical lymph nodes"), rp.tr("No indeterminate or suspicious lymph nodes in levels I to VII")])

    staged = pick(c, "staging", STAGING)
    staging = [rp.Choice("staging", rp.tr("TNM staging"), STAGING, str(staged))]
    if str(staged) != "Not staged":
        size = min(max(float(c.get("t_size", 0.0)), 0), 200)
        ext, age, m_ = pick(c, "t_ext", EXTENSION), pick(c, "age", AGES), pick(c, "m", METASTASES)
        t = t_category(size, str(ext))
        n = n_category(suspicious)
        m_code = "M1" if str(m_).startswith("M1") else "M0"
        group = stage(t, n, str(age) == "55 years or older", m_code == "M1")
        staging += [
            rp.Row([rp.Number("t_size", rp.tr("Tumour largest diameter (mm)"), size, min=0, max=200, step=1),
                    rp.Choice("age", rp.tr("Age at diagnosis"), AGES, str(age))]),
            rp.Choice("t_ext", rp.tr("Extension"), EXTENSION, str(ext)),
            rp.Choice("m", rp.tr("Distant metastases"), METASTASES, str(m_)),
        ]
        rows += [
            [rp.tr("Clinical TNM (AJCC 8th edition)"), "c%s c%s c%s" % (t, n, m_code)],
            [rp.tr("Stage (differentiated thyroid carcinoma)"), group],
        ]

    comment = str(c.get("comment", "")).strip()
    if comment:
        rows.append([rp.tr("Comment"), comment])

    value = {"marks": [{k: m[k] for k in ("id", "x", "y", "r", "label", "tone", "form", "data")} for m in marks],
             "selected": selected["id"] if selected is not None else None}
    blocks = [
        rp.Sketch("neck", rp.tr("Thyroid and cervical lymph node levels"), W, H, schematic(worst), value=value,
                  max_marks=16),
        rp.Label(rp.tr("Drag on a lobe to draw a nodule, or inside a level to draw a lymph node; click a mark to "
                       "describe it."), weak=True),
    ]
    if outside:
        blocks.append(rp.Label(rp.tr("A mark outside the thyroid and the lymph node levels is not reported: move it "
                                     "or delete it."), weak=True))
    if value["selected"] is not None:
        kind = locate(selected["x"], selected["y"])[0]
        head = [rp.Label(selected["title"] or rp.tr("Outside the schematic")), rp.Button("delete", rp.tr("Delete"),
                                                                                         icon="trash")]
        if selected["where"] is not None:
            head.insert(1, rp.Label(selected["where"], weak=True))
        blocks += [rp.Separator(), rp.Row(head)] + (editor(kind, selected["data"], selected["id"]) if kind else [])
    blocks += [
        rp.Section(rp.tr("Cervical lymph node classes"), [rp.Label(rp.tr(
            "Suspicious: microcalcifications, cystic change, peripheral or diffuse increased vascularity, or "
            "hyperechoic tissue like thyroid. Indeterminate: no hilum and none of these. Normal: hilum present "
            "(ETA 2013)."), weak=True)], open=False),
        rp.Section(rp.tr("Staging"), staging),
        rp.TextField("comment", rp.tr("Comment"), comment, max_length=500),
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(rows),
        rp.Label(
            rp.tr(
                "ACR TI-RADS (Tessler et al., JACR 2017); lymph nodes: ETA 2013; TNM: AJCC 8th "
                "edition, clinical, for differentiated carcinoma only. Not a medical device: "
                "check every line before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("TI-RADS report"), blocks, size=(560, 900))])

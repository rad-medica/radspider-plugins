"""PI-RADS structured prostate MRI report: prostate volume (ellipsoid) and PSA density, lesions drawn on an axial
sector map of base, midgland and apex (api 8 sketch) with their size and T2W / DWI / DCE scores, the PI-RADS v2.1
assessment category computed per lesion (dominant sequence by zone), local staging findings and the overall category.

The viewer holds the marks; each lesion's descriptors live in its mark's ``data``, and its side, level and sector come
from where the mark sits. The editor below the map shows the selected lesion through controls named <key>_<mark id>;
every run writes the controls present back into their mark. The report is a two-column table; *Copy table* puts it on
the clipboard as tab-separated lines."""

import radspider_plugin as rp

W, H = 460, 220  # map units: three axial sections, anterior at the top, patient's right on the left

SIDES = [rp.tr("Right"), rp.tr("Left"), rp.tr("Midline")]
LEVELS = [rp.tr("Base"), rp.tr("Midgland"), rp.tr("Apex")]
# Per level: centre x, centre y, rx, ry of the gland; centre y, rx, ry of the transition zone (canvas design).
SECTIONS = [(80, 120, 62, 48, 114, 34, 24), (230, 120, 62, 48, 114, 34, 24), (380, 120, 52, 40, 116, 22, 16)]
CZ_ELLIPSE = (80, 146, 22, 12)  # drawn on the base; the hit-test uses |dx| < 22 and dy > 14 there
SECTORS = {  # short code -> (option, zone the v2.1 assessment rules use)
    "PZpl": (rp.tr("Peripheral zone, posterolateral (PZpl)"), "PZ"),
    "PZpm": (rp.tr("Peripheral zone, posteromedial (PZpm)"), "PZ"),
    "PZa": (rp.tr("Peripheral zone, anterior (PZa)"), "PZ"),
    "TZa": (rp.tr("Transition zone, anterior (TZa)"), "TZ"),
    "TZp": (rp.tr("Transition zone, posterior (TZp)"), "TZ"),
    "CZ": (rp.tr("Central zone (CZ)"), "CZ"),
    "AS": (rp.tr("Anterior fibromuscular stroma (AS)"), "AS"),
}
SCORES = ["1", "2", "3", "4", "5"]
DWI = SCORES + [rp.tr("Inadequate")]
DCE = [rp.tr("Negative"), rp.tr("Positive"), rp.tr("Not performed or inadequate")]
EPE = [rp.tr("Not seen"), rp.tr("Suspected"), rp.tr("Present")]
# Plain text: options are told apart by their English id, and one "PI-RADS {n}" id would make them one option.
MANUAL = [rp.tr("Assign manually")] + ["PI-RADS %d" % n for n in range(1, 6)]
LESION_KEYS = ["size", "t2", "dwi", "dce", "manual", "epe", "svi"]
CATEGORIES = {
    1: rp.tr("PI-RADS 1: very low (clinically significant cancer is highly unlikely to be present)"),
    2: rp.tr("PI-RADS 2: low (clinically significant cancer is unlikely to be present)"),
    3: rp.tr("PI-RADS 3: intermediate (the presence of clinically significant cancer is equivocal)"),
    4: rp.tr("PI-RADS 4: high (clinically significant cancer is likely to be present)"),
    5: rp.tr("PI-RADS 5: very high (clinically significant cancer is highly likely to be present)"),
}


def category(zone, t2, dwi, dce):
    """PI-RADS v2.1 assessment category of one lesion, or None where these rules give none and the reader assigns it:
    central zone, anterior stroma (scored with the zone the lesion arises from), inadequate DWI.
    `t2`, `dwi`: 1-5 (`dwi` None when inadequate); `dce`: True positive, False negative, None not available.
    PZ: DWI decides; DWI 3 with positive DCE is 4 (without DCE it stays 3).
    TZ: T2W decides; T2W 2 with DWI 4-5 is 3, T2W 3 with DWI 5 is 4; DCE plays no part."""
    if dwi is None:
        return None
    if zone == "PZ":
        return 4 if dwi == 3 and dce else dwi
    if zone == "TZ":
        if t2 == 2 and dwi >= 4:
            return 3
        if t2 == 3 and dwi == 5:
            return 4
        return t2
    return None


def volume_ml(ap, tv, cc):
    """Prostate volume (ml) by the ellipsoid formula of PI-RADS v2.1: AP x transverse x craniocaudal (mm) x 0.52."""
    return ap * tv * cc * 0.52 / 1000


def locate(x, y):
    """(level index, side index, sector code) of a point on the map, or None outside the three sections."""
    for lvl, (cx, cy, rx, ry, ty, trx, tr_y) in enumerate(SECTIONS):
        dx, dy = x - cx, y - cy
        if (dx / rx) ** 2 + (dy / ry) ** 2 > 1.05:
            continue
        side = 2 if abs(dx) < 4 else 0 if dx < 0 else 1
        if dy < -(ry - 18):
            sector = "AS"
        elif (dx / trx) ** 2 + ((y - ty) / tr_y) ** 2 <= 1:
            sector = "TZa" if y < ty else "TZp"
        elif lvl == 0 and abs(dx) < 22 and dy > 14:
            sector = "CZ"
        elif dy < -6:
            sector = "PZa"
        else:
            sector = "PZpm" if abs(dx) < 22 else "PZpl"
        return lvl, side, sector
    return None


def pick(c, name, options):
    """The option whose English id `c` holds for `name`, else the first."""
    return next((o for o in options if str(o) == c.get(name)), options[0])


def number(c, key, hi):
    """A number from controls or mark data (strings), clamped to 0..hi; anything unreadable is 0."""
    try:
        return min(max(float(c.get(key, 0)), 0.0), hi)
    except (TypeError, ValueError):
        return 0.0


def encode(value):
    """A control value as mark data: one-line strings, booleans as "1" / "0"."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return "%g" % value if isinstance(value, (int, float)) else str(value)


def lesion(data, zone, rows):
    """Report rows of one lesion appended to `rows`; returns (category or None, the reader must assign it)."""
    size = number(data, "size", 100)
    if size > 0:
        rows.append([rp.tr("Largest diameter"), "%g mm" % size])
    t2, dwi, dce = pick(data, "t2", SCORES), pick(data, "dwi", DWI), pick(data, "dce", DCE)
    rows += [[rp.tr("T2W score"), t2], [rp.tr("DWI score"), dwi], [rp.tr("DCE"), dce]]
    dce_value = {"Negative": False, "Positive": True}.get(str(dce))
    auto = category(zone, int(t2), int(dwi) if str(dwi) in SCORES else None, dce_value)
    manual = auto is None
    if manual:
        auto = MANUAL.index(pick(data, "manual", MANUAL)) or None
    rows.append([rp.tr("Extraprostatic extension"), pick(data, "epe", EPE)])
    if data.get("svi") == "1":
        rows.append([rp.tr("Seminal vesicle invasion"), rp.tr("Present")])
    rows.append([rp.tr("PI-RADS"), CATEGORIES[auto] if auto else rp.tr("Not assigned")])
    return auto, manual


def editor(data, mid, manual):
    """Controls describing lesion mark `mid`, filled from its data; each is named <data key>_<mark id>."""
    def n(k):
        return "%s_%d" % (k, mid)

    blocks = [
        rp.Number(n("size"), rp.tr("Largest diameter (mm)"), number(data, "size", 100), min=0, max=100, step=1),
        rp.Row([rp.Choice(n("t2"), rp.tr("T2W score"), SCORES, str(pick(data, "t2", SCORES))),
                rp.Choice(n("dwi"), rp.tr("DWI score"), DWI, str(pick(data, "dwi", DWI))),
                rp.Choice(n("dce"), rp.tr("DCE"), DCE, str(pick(data, "dce", DCE)))]),
    ]
    if manual:
        blocks += [
            rp.Label(
                rp.tr(
                    "No PI-RADS v2.1 rule applies (central zone, inadequate DWI) or the anterior stroma lesion is "
                    "scored with the zone it arises from: assign the category."
                ),
                weak=True,
            ),
            rp.Choice(n("manual"), rp.tr("Category"), MANUAL, str(pick(data, "manual", MANUAL))),
        ]
    return blocks + [
        rp.Choice(n("epe"), rp.tr("Extraprostatic extension"), EPE, str(pick(data, "epe", EPE))),
        rp.Checkbox(n("svi"), rp.tr("Seminal vesicle invasion"), data.get("svi") == "1"),
    ]


def schematic():
    """Three axial sections (base, midgland, apex): gland, transition zone, central zone, midline and AS guides."""
    shapes = []
    for lvl, (cx, cy, rx, ry, ty, trx, tr_y) in enumerate(SECTIONS):
        shapes += [
            {"kind": "ellipse", "x": cx, "y": cy, "rx": rx, "ry": ry, "style": "area"},
            {"kind": "ellipse", "x": cx, "y": ty, "rx": trx, "ry": tr_y, "style": "line"},
            {"kind": "line", "points": [[cx, cy - ry], [cx, cy + ry]], "style": "guide"},
            {"kind": "line", "points": [[cx - rx + 12, cy - ry + 18], [cx + rx - 12, cy - ry + 18]], "style": "guide"},
            {"kind": "text", "x": cx, "y": 22, "text": LEVELS[lvl], "style": "label", "size": 12},
            {"kind": "text", "x": cx, "y": cy - ry - 8, "text": "AS", "style": "muted", "size": 10},
            {"kind": "text", "x": cx, "y": ty - 6, "text": "TZ", "style": "muted", "size": 10},
            {"kind": "text", "x": cx - rx - 8, "y": cy, "text": rp.tr("R"), "style": "muted", "size": 10},
            {"kind": "text", "x": cx + rx + 8, "y": cy, "text": rp.tr("L"), "style": "muted", "size": 10},
        ]
    x, y, rx, ry = CZ_ELLIPSE
    shapes += [
        {"kind": "ellipse", "x": x, "y": y, "rx": rx, "ry": ry, "style": "line"},
        {"kind": "text", "x": x, "y": y, "text": "CZ", "style": "muted", "size": 10},
        {"kind": "text", "x": 200, "y": 158, "text": "PZ", "style": "muted", "size": 10},
        {"kind": "text", "x": 260, "y": 158, "text": "PZ", "style": "muted", "size": 10},
        {"kind": "text", "x": 230, "y": 204, "text": rp.tr("R: patient's right. Anterior at the top."), "style": "muted",
         "size": 10},
    ]
    return shapes


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    rows = []
    dims = [
        (name, label, number(c, name, 150))
        for name, label in (
            ("ap", rp.tr("Anteroposterior (mm)")),
            ("tv", rp.tr("Transverse (mm)")),
            ("cc", rp.tr("Craniocaudal (mm)")),
        )
    ]
    psa = number(c, "psa", 1000)
    ml = volume_ml(*(v for _, _, v in dims))
    if ml > 0:
        rows.append([rp.tr("Prostate volume"), "%.1f ml" % ml])
        if psa > 0:
            rows.append([rp.tr("PSA density"), "%.2f ng/ml/ml" % (psa / ml)])

    sketch = c.get("map") or {"marks": [], "selected": None}
    marks = sorted(sketch.get("marks", []), key=lambda m: m["id"])
    if ctx.event == "delete":
        marks = [m for m in marks if m["id"] != sketch.get("selected")]
        sketch["selected"] = None
    selected = next((m for m in marks if m["id"] == sketch.get("selected")), None)
    for m in marks:  # editor controls are named by mark id, so an edit survives a selection change in flight
        m.setdefault("data", {})
        m["data"].update({k: encode(c["%s_%d" % (k, m["id"])]) for k in LESION_KEYS if "%s_%d" % (k, m["id"]) in c})

    found, outside, count = [], False, 0
    for m in marks:
        where, m["form"] = locate(m["x"], m["y"]), "circle"
        if where is None:
            outside = True
            m["label"], m["tone"], m["title"], m["manual"] = "?", "muted", None, False
            continue
        count += 1
        lvl, side, code = where
        sector, zone = SECTORS[code]
        m["title"], m["where"] = rp.tr("Lesion {n}", n=count), [SIDES[side], LEVELS[lvl], sector]
        rows += [[m["title"], ""], [rp.tr("Side"), SIDES[side]], [rp.tr("Level"), LEVELS[lvl]],
                 [rp.tr("Sector"), sector]]
        cat, m["manual"] = lesion(m["data"], zone, rows)
        found.append(cat)
        m["label"] = "L%d P%s" % (count, cat or "?")
        m["tone"] = {5: "error", 4: "warn", 3: "accent", 2: "ok", 1: "ok"}.get(cat, "accent")

    staging = []
    for name, label in (("nodes", rp.tr("Suspicious pelvic lymph nodes")), ("bone", rp.tr("Suspicious bone lesions"))):
        on = bool(c.get(name, False))
        staging.append(rp.Checkbox(name, label, on))
        rows.append([label, rp.tr("Present") if on else rp.tr("Not seen")])
    if None in found:
        overall = rp.tr("Not assigned: a lesion has no category yet")
    else:
        overall = CATEGORIES[max(found)] if found else rp.tr("No lesion entered")
    rows.append([rp.tr("Overall assessment"), overall])
    comment = str(c.get("comment", "")).strip()
    if comment:
        rows.append([rp.tr("Comment"), comment])

    value = {"marks": [{k: m[k] for k in ("id", "x", "y", "r", "label", "tone", "form", "data")} for m in marks],
             "selected": selected["id"] if selected is not None else None}
    blocks = [
        rp.Row([rp.Number(name, label, v, min=0, max=150, step=1) for name, label, v in dims]),
        rp.Number("psa", rp.tr("PSA (ng/ml)"), psa, min=0, max=1000, step=0.1),
        rp.Sketch("map", rp.tr("Sector map (axial sections)"), W, H, schematic(), value=value, max_marks=12),
        rp.Label(rp.tr("Drag on a section to draw a lesion; click a lesion to describe it."), weak=True),
    ]
    if outside:
        blocks.append(rp.Label(rp.tr("A mark outside the three sections is not reported: move it or delete it."),
                               weak=True))
    if selected is not None:
        head = [rp.Label(selected["title"] or rp.tr("Outside the map")),
                rp.Button("delete", rp.tr("Delete"), icon="trash")]
        if selected["title"] is not None:  # three labels: a marked text cannot be an argument of another
            head[1:1] = [rp.Label(t, weak=True) for t in selected["where"]]
        blocks += [rp.Separator(), rp.Row(head)]
        if selected["title"] is not None:
            blocks += editor(selected["data"], selected["id"], selected["manual"])
    blocks += [
        rp.Separator(),
        rp.Row(staging),
        rp.TextField("comment", rp.tr("Comment"), comment, max_length=500),
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(rows),
        rp.Label(
            rp.tr(
                "PI-RADS v2.1 (Turkbey et al., Eur Urol 2019). The category is computed from the scores the "
                "reader enters. Not a medical device: check every line "
                "before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("PI-RADS report"), blocks, size=(560, 880))])

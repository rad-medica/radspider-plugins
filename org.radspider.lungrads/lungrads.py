"""Lung-RADS structured lung cancer screening CT report: the user draws nodules or atypical cysts on a frontal lung
schematic (api 8 sketch); each takes its lobe from where it sits and has its type, behaviour since the prior exam and
mean diameters, the Lung-RADS v2022 category computed from them (or assigned by the reader where the rules give none),
the 4X and S modifiers, category 0, and the management of the exam.

The viewer holds the marks; each mark's descriptors live in its ``data``. The editor below the schematic shows the
selected mark through controls named <key>_<mark id>; every run writes the controls present back into their mark.
The report is a two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

W, H = 460, 270  # schematic units: frontal view, patient's right on the left
RIGHT = [[40, 60], [90, 25], [150, 30], [185, 80], [195, 230], [40, 240], [25, 150]]
LEFT = [[420, 60], [370, 25], [310, 30], [275, 80], [265, 230], [420, 240], [435, 150]]

LOBES = [
    rp.tr("Right upper lobe"),
    rp.tr("Middle lobe"),
    rp.tr("Right lower lobe"),
    rp.tr("Left upper lobe"),
    rp.tr("Lingula"),
    rp.tr("Left lower lobe"),
]
TYPES = [  # option English id -> rule key
    (rp.tr("Solid"), "solid"),
    (rp.tr("Part-solid"), "part"),
    (rp.tr("Non-solid (ground glass)"), "gg"),
    (rp.tr("Juxtapleural or perifissural, solid, smooth, oval or triangular"), "juxta"),
    (rp.tr("Airway nodule, subsegmental"), "airway_sub"),
    (rp.tr("Airway nodule, segmental or more proximal"), "airway_seg"),
    (rp.tr("Benign calcification or fat"), "benign"),
    (rp.tr("Atypical cyst: thick-walled, or multilocular, or became multilocular"), "cyst_4a"),
    (rp.tr("Atypical cyst: growing cystic component of a thick-walled cyst"), "cyst_3"),
    (
        rp.tr("Atypical cyst: growing wall or nodularity, growing or more loculated, new or increased opacity"),
        "cyst_4b",
    ),
]
STATUSES = [  # option English id -> rule key
    (rp.tr("Baseline"), "baseline"),
    (rp.tr("New"), "new"),
    (rp.tr("Growing (more than 1.5 mm in 12 months)"), "growing"),
    (rp.tr("Slow-growing over several exams"), "slow"),
    (rp.tr("Stable at annual screening (category 2 before)"), "stable"),
    (rp.tr("Stable or smaller at the 6-month exam of a category 3"), "after3"),
    (rp.tr("Stable or smaller at the 3-month exam of a category 4A"), "after4a"),
]
INCOMPLETE = [
    rp.tr("No"),
    rp.tr("Prior chest CT being located for comparison"),
    rp.tr("Part or all of the lungs cannot be evaluated"),
    rp.tr("Findings suggestive of an inflammatory or infectious process"),
]
CODES = ["0", "1", "2", "3", "4A", "4B", "4X"]
MANUAL = [rp.tr("Computed")] + ["Lung-RADS %s" % k for k in CODES[1:]]  # plain: told apart by their English id
CATEGORIES = {  # code: (name, management), Lung-RADS v2022
    "0": (rp.tr("Lung-RADS 0: incomplete"), rp.tr("Comparison with the prior chest CT, or LDCT in 1 to 3 months")),
    "1": (rp.tr("Lung-RADS 1: negative"), rp.tr("Continue annual screening with LDCT in 12 months")),
    "2": (
        rp.tr("Lung-RADS 2: benign appearance or behaviour"),
        rp.tr("Continue annual screening with LDCT in 12 months"),
    ),
    "3": (rp.tr("Lung-RADS 3: probably benign"), rp.tr("LDCT in 6 months")),
    "4A": (
        rp.tr("Lung-RADS 4A: suspicious"),
        rp.tr(
            "LDCT in 3 months; PET/CT may be considered if there is a solid nodule or solid component of 8 mm or more"
        ),
    ),
    "4B": (
        rp.tr("Lung-RADS 4B: very suspicious"),
        rp.tr(
            "Diagnostic chest CT with or without contrast; PET/CT may be considered if there is a solid nodule "
            "or solid component of 8 mm or more; tissue sampling; and/or referral for further clinical "
            "evaluation"
        ),
    ),
    "4X": (
        rp.tr("Lung-RADS 4X: very suspicious, with additional features"),
        rp.tr(
            "Diagnostic chest CT with or without contrast; PET/CT may be considered if there is a solid nodule "
            "or solid component of 8 mm or more; tissue sampling; and/or referral for further clinical "
            "evaluation"
        ),
    ),
}


def solid_category(status, d):
    """Solid nodule of mean diameter `d` mm."""
    if status == "baseline":
        return "2" if d < 6 else "3" if d < 8 else "4A" if d < 15 else "4B"
    if status == "new":
        return "2" if d < 4 else "3" if d < 6 else "4A" if d < 8 else "4B"
    if status == "growing":
        return "4A" if d < 8 else "4B"
    return None


def category(kind, status, d, solid):
    """Lung-RADS v2022 category of one finding, or None where the rules give none and the reader assigns it.
    `kind`, `status`: rule keys of TYPES and STATUSES; `d`: mean diameter (mm); `solid`: mean diameter of the solid
    component (mm, part-solid only)."""
    fixed = {"benign": "1", "cyst_4a": "4A", "cyst_3": "3", "cyst_4b": "4B"}
    if kind in fixed:
        return fixed[kind]
    if kind == "airway_seg":
        return "4A" if status in ("baseline", "new") else "4B"
    if status == "after3":
        return "2"
    if status == "after4a":
        return "3"
    if kind == "airway_sub":
        return "2" if status in ("baseline", "new", "stable") else None
    if status == "stable":
        return "2"
    if kind == "gg":
        if status == "slow" or d < 30:
            return "2"
        return "3" if status in ("baseline", "new") else None
    if status == "slow":
        return "4B"
    if kind == "juxta":
        if status in ("baseline", "new") and d < 10:
            return "2"
        return solid_category(status, d)
    if kind == "solid":
        return solid_category(status, d)
    # part-solid: without its solid component there is no row to read
    if solid <= 0:
        return None
    if status == "baseline":
        return "2" if d < 6 else "3" if solid < 6 else "4A" if solid < 8 else "4B"
    if solid >= 4:
        return "4B"
    return "3" if status == "new" and d < 6 else "4A"


def inside(x, y, poly):
    """Even-odd point-in-polygon test."""
    hit = False
    for (xi, yi), (xj, yj) in zip(poly, poly[-1:] + poly[:-1]):
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
    return hit


def locate(x, y):
    """Index into LOBES of a point on the schematic, or None outside both lungs. Fissures are approximate: right
    horizontal y = 115, right oblique (30, 115)-(170, 240), left oblique (430, 110)-(290, 240), lingula below y = 150."""
    if inside(x, y, RIGHT):
        if y < 115:
            return 0
        return 2 if y > 115 + (x - 30) * 125 / 140 else 1
    if inside(x, y, LEFT):
        if y > 110 + (430 - x) * 130 / 140:
            return 5
        return 4 if y > 150 else 3
    return None


def pick(c, name, options):
    """The option whose English id `c` holds for `name`, else the first."""
    return next((o for o in options if str(o) == c.get(name)), options[0])


def number(data, key, hi):
    """A diameter in mm from mark data (strings), clamped to 0..hi and rounded to 0.1 (v2022); unreadable is 0."""
    try:
        return round(min(max(float(data.get(key, 0)), 0.0), hi), 1)
    except (TypeError, ValueError):
        return 0.0


def encode(value):
    """A control value as mark data: one-line strings, booleans as "1" / "0"."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return "%g" % value if isinstance(value, (int, float)) else str(value)


KEYS = ["type", "status", "d", "solid", "x", "manual"]
TONES = {"1": "ok", "2": "ok", "3": "accent", "4A": "warn", "4B": "error", "4X": "error", None: "warn"}


def nodule(data, rows):
    """Report rows of one finding appended to `rows`; returns its category code (None: not assigned)."""
    kind_opt = pick(data, "type", [o for o, _ in TYPES])
    status_opt = pick(data, "status", [o for o, _ in STATUSES])
    kind, status = dict(TYPES)[kind_opt], dict(STATUSES)[status_opt]
    d = number(data, "d", 300.0)
    solid = min(number(data, "solid", 300.0), d)
    rows += [[rp.tr("Type"), kind_opt], [rp.tr("Since the prior exam"), status_opt]]
    if d > 0:
        rows.append([rp.tr("Mean diameter"), "%.1f mm" % d])
    if kind == "part" and solid > 0:
        rows.append([rp.tr("Solid component"), "%.1f mm" % solid])
    sized = kind in ("solid", "part", "gg", "juxta")
    code = category(kind, status, d, solid) if d > 0 or not sized else None
    manual = pick(data, "manual", MANUAL)
    if str(manual) != "Computed":
        code = str(manual).split()[-1]
    if data.get("x") == "1" and code in ("3", "4A", "4B"):
        code = "4X"
    rows.append([rp.tr("Lung-RADS"), CATEGORIES[code][0] if code else rp.tr("Not assigned")])
    return code


def editor(data, mid, code):
    """Controls describing finding `mid`, filled from its data; each is named <data key>_<mark id>."""
    def n(k):
        return "%s_%d" % (k, mid)

    types, statuses = [o for o, _ in TYPES], [o for o, _ in STATUSES]
    kind_opt = pick(data, "type", types)
    d = number(data, "d", 300.0)
    solid = [rp.Number(n("solid"), rp.tr("Solid component (mm)"), min(number(data, "solid", 300.0), d), min=0,
                       max=300, step=0.1)]
    blocks = [
        rp.Choice(n("type"), rp.tr("Type"), types, str(kind_opt)),
        rp.Choice(n("status"), rp.tr("Since the prior exam"), statuses, str(pick(data, "status", statuses))),
        rp.Row([rp.Number(n("d"), rp.tr("Mean diameter (mm)"), d, min=0, max=300, step=0.1)]
               + (solid if dict(TYPES)[kind_opt] == "part" else [])),
    ]
    manual = pick(data, "manual", MANUAL)
    if code is None and str(manual) == "Computed":
        blocks.append(
            rp.Label(
                rp.tr(
                    "Enter the mean diameter, or assign the category: Lung-RADS v2022 has no row for this combination."
                ),
                weak=True,
            )
        )
    return blocks + [
        rp.Checkbox(n("x"), rp.tr("Additional features that increase the suspicion of cancer (4X)"),
                    data.get("x") == "1"),
        rp.Choice(n("manual"), rp.tr("Category"), MANUAL, str(manual)),
        rp.Label(CATEGORIES[code][0] if code else rp.tr("Not assigned")),
    ]


def schematic():
    """Both lungs, the approximate fissures and the lobe names."""
    def text(x, y, t, style="muted", size=12):
        return {"kind": "text", "x": x, "y": y, "text": t, "style": style, "size": size}

    return [
        {"kind": "polygon", "points": RIGHT, "style": "area"},
        {"kind": "polygon", "points": LEFT, "style": "area"},
        {"kind": "line", "points": [[28, 115], [188, 115]], "style": "guide"},
        {"kind": "line", "points": [[30, 115], [170, 240]], "style": "guide"},
        {"kind": "line", "points": [[430, 110], [290, 240]], "style": "guide"},
        {"kind": "line", "points": [[300, 150], [405, 150]], "style": "guide"},
        text(110, 76, rp.tr("RUL")),
        text(150, 156, rp.tr("ML")),
        text(70, 201, rp.tr("RLL")),
        text(345, 86, rp.tr("LUL")),
        text(320, 181, rp.tr("Lingula")),
        text(395, 211, rp.tr("LLL")),
        text(110, 12, rp.tr("Right lung"), "label"),
        text(350, 12, rp.tr("Left lung"), "label"),
        text(230, 258, rp.tr("Fissures are approximate: confirm the lobe on the CT"), size=10),
    ]


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    sketch = c.get("lungs") or {"marks": [], "selected": None}
    marks = sorted(sketch.get("marks", []), key=lambda m: m["id"])
    if ctx.event == "delete":
        marks = [m for m in marks if m["id"] != sketch.get("selected")]
        sketch["selected"] = None
    selected = next((m for m in marks if m["id"] == sketch.get("selected")), None)
    for m in marks:  # editor controls are named by mark id, so an edit survives a selection change in flight
        edits = {k: encode(c["%s_%d" % (k, m["id"])]) for k in KEYS if "%s_%d" % (k, m["id"]) in c}
        m["data"] = {**m.get("data", {}), **edits}

    rows, found, outside, seen = [], [], False, {}
    for m in marks:
        lobe = locate(m["x"], m["y"])
        if lobe is None:
            outside = True
            m["label"], m["tone"], m["form"] = "?", "muted", "circle"
            continue
        n = len(found) + 1
        rows += [[rp.tr("Nodule {n}", n=n), ""], [rp.tr("Lobe"), LOBES[lobe]]]
        code = nodule(m["data"], rows)
        found.append(code)
        seen[m["id"]] = (n, lobe, code)
        m["label"], m["tone"], m["form"] = "N%d %s" % (n, code or "?"), TONES[code], "circle"
    if not found:
        rows.append([rp.tr("Lung nodules"), rp.tr("None")])
    incomplete = pick(c, "incomplete", INCOMPLETE)
    if str(incomplete) != "No":
        code = "0"
        rows.append([rp.tr("Incomplete"), incomplete])
    else:
        # One finding without a category leaves the exam without one: never a category the findings do not support.
        code = None if None in found else max(found, key=CODES.index, default="1")
    s = bool(c.get("s", False))
    s_text = str(c.get("s_text", "")).strip()
    if code:
        rows += [[rp.tr("Lung-RADS category"), CATEGORIES[code][0]], [rp.tr("Management"), CATEGORIES[code][1]]]
    else:
        rows.append([rp.tr("Lung-RADS category"), rp.tr("Not assigned: a finding has no category yet")])
    if s:
        rows.append(
            [rp.tr("S modifier: clinically significant or potentially significant finding"), s_text or rp.tr("Present")]
        )
    comment = str(c.get("comment", "")).strip()
    if comment:
        rows.append([rp.tr("Comment"), comment])

    value = {"marks": [{k: m[k] for k in ("id", "x", "y", "r", "label", "tone", "form", "data")} for m in marks],
             "selected": selected["id"] if selected is not None else None}
    blocks = [
        rp.Sketch("lungs", rp.tr("Lung lobes (frontal view)"), W, H, schematic(), value=value, max_marks=16),
        rp.Label(rp.tr("Drag on a lobe to draw a nodule or cyst; click a mark to describe it."), weak=True),
    ]
    if outside:
        blocks.append(rp.Label(rp.tr("A mark outside the lungs is not reported: move it or delete it."), weak=True))
    if selected is not None:
        delete = rp.Button("delete", rp.tr("Delete"), icon="trash")
        if selected["id"] in seen:
            n, lobe, sel_code = seen[selected["id"]]
            head = [rp.Label(rp.tr("Nodule {n}", n=n)), rp.Label(LOBES[lobe], weak=True), delete]
            blocks += [rp.Separator(), rp.Row(head)] + editor(selected["data"], selected["id"], sel_code)
        else:
            blocks += [rp.Separator(), rp.Row([rp.Label(rp.tr("Outside the schematic")), delete])]
    blocks += [
        rp.Choice("incomplete", rp.tr("Incomplete exam (category 0)"), INCOMPLETE, str(incomplete)),
        rp.Row(
            [
                rp.Checkbox("s", rp.tr("S modifier"), s),
                rp.TextField("s_text", rp.tr("Significant finding"), s_text, max_length=300),
            ]
        ),
        rp.TextField("comment", rp.tr("Comment"), comment, max_length=500),
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(rows),
        rp.Label(
            rp.tr(
                "Lung-RADS v2022. The exam category is that of the most suspicious finding; without "
                "findings it is 1. Not a medical device: check every line before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("Lung-RADS report"), blocks, size=(560, 900))])

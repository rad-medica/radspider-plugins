"""Lung-RADS structured lung cancer screening CT report: up to six nodules or atypical cysts, each with its lobe, type,
behaviour since the prior exam and mean diameters, the Lung-RADS v2022 category computed from them (or assigned by
the reader where the rules give none), the 4X and S modifiers, category 0, and the management of the exam.

Each nodule has a window of its own: a window holds at most 32 controls, and controls left out of an answer lose
their values. The report is a two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

MAX_NODULES = 6  # 5 exam controls + 6 x 7 nodule controls stay under the host's 64 controls per instance

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
    # part-solid
    if status == "baseline":
        return "2" if d < 6 else "3" if solid < 6 else "4A" if solid < 8 else "4B"
    if solid >= 4:
        return "4B"
    return "3" if status == "new" and d < 6 else "4A"


def pick(c, name, options):
    """The option whose English id ctx.controls holds for `name`, else the first."""
    return next((o for o in options if str(o) == c.get(name)), options[0])


def nodule(c, rows, i):
    """The controls of nodule `i` (they fill `rows`) and its category code (None: not assigned)."""
    rows.append([rp.tr("Nodule {n}", n=i), ""])
    lobe = pick(c, "lobe_%d" % i, LOBES)
    types = [o for o, _ in TYPES]
    statuses = [o for o, _ in STATUSES]
    kind_opt, status_opt = pick(c, "type_%d" % i, types), pick(c, "status_%d" % i, statuses)
    kind, status = dict(TYPES)[kind_opt], dict(STATUSES)[status_opt]
    d = round(min(max(float(c.get("d_%d" % i, 0.0)), 0.0), 300.0), 1)  # v2022: mean diameter to one decimal
    solid = round(min(max(float(c.get("solid_%d" % i, 0.0)), 0.0), d), 1)
    rows += [[rp.tr("Lobe"), lobe], [rp.tr("Type"), kind_opt], [rp.tr("Since the prior exam"), status_opt]]
    blocks = [
        rp.Choice("lobe_%d" % i, rp.tr("Lobe"), LOBES, str(lobe)),
        rp.Choice("type_%d" % i, rp.tr("Type"), types, str(kind_opt)),
        rp.Choice("status_%d" % i, rp.tr("Since the prior exam"), statuses, str(status_opt)),
        rp.Row(
            [rp.Number("d_%d" % i, rp.tr("Mean diameter (mm)"), d, min=0, max=300, step=0.1)]
            + (
                [rp.Number("solid_%d" % i, rp.tr("Solid component (mm)"), solid, min=0, max=300, step=0.1)]
                if kind == "part"
                else []
            )
        ),
    ]
    if d > 0:
        rows.append([rp.tr("Mean diameter"), "%.1f mm" % d])
    if kind == "part" and solid > 0:
        rows.append([rp.tr("Solid component"), "%.1f mm" % solid])
    sized = kind in ("solid", "part", "gg", "juxta")
    code = category(kind, status, d, solid) if d > 0 or not sized else None
    manual = pick(c, "manual_%d" % i, MANUAL)
    if code is None and str(manual) == "Computed":
        blocks.append(
            rp.Label(
                rp.tr(
                    "Enter the mean diameter, or assign the category: Lung-RADS v2022 has no row for this combination."
                ),
                weak=True,
            )
        )
    if str(manual) != "Computed":
        code = str(manual).split()[-1]
    x = bool(c.get("x_%d" % i, False))
    if x and code in ("3", "4A", "4B"):
        code = "4X"
    blocks += [
        rp.Checkbox("x_%d" % i, rp.tr("Additional features that increase the suspicion of cancer (4X)"), x),
        rp.Choice("manual_%d" % i, rp.tr("Category"), MANUAL, str(manual)),
        rp.Label(CATEGORIES[code][0] if code else rp.tr("Not assigned")),
    ]
    rows.append([rp.tr("Lung-RADS"), CATEGORIES[code][0] if code else rp.tr("Not assigned")])
    return blocks, code


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    rows = []
    count = int(min(max(c.get("count", 1), 0), MAX_NODULES))
    windows, found = [], []
    for i in range(1, count + 1):
        blocks, code = nodule(c, rows, i)
        if code:
            found.append(code)
        windows.append(
            rp.Window("nodule_%d" % i, rp.tr("Nodule {n}", n=i), blocks, size=(480, 400), reopen=ctx.event == "count")
        )
    if not count:
        rows.append([rp.tr("Lung nodules"), rp.tr("None")])
    incomplete = pick(c, "incomplete", INCOMPLETE)
    if str(incomplete) != "No":
        code = "0"
        rows.append([rp.tr("Incomplete"), incomplete])
    else:
        code = max(found, key=CODES.index, default="1")
    s = bool(c.get("s", False))
    s_text = str(c.get("s_text", "")).strip()
    name, management = CATEGORIES[code]
    rows += [[rp.tr("Lung-RADS category"), name], [rp.tr("Management"), management]]
    if s:
        rows.append(
            [rp.tr("S modifier: clinically significant or potentially significant finding"), s_text or rp.tr("Present")]
        )
    comment = str(c.get("comment", "")).strip()
    if comment:
        rows.append([rp.tr("Comment"), comment])
    blocks = [
        rp.Number("count", rp.tr("Nodules"), count, min=0, max=MAX_NODULES, step=1),
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
    return rp.Result(windows=[rp.Window("main", rp.tr("Lung-RADS report"), blocks, size=(560, 640))] + windows)

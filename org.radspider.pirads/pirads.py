"""PI-RADS structured prostate MRI report: prostate volume (ellipsoid) and PSA density, up to four lesions with their
sector, size and T2W / DWI / DCE scores, the PI-RADS v2.1 assessment category computed per lesion (dominant sequence
by zone), local staging findings and the overall category.

Each lesion has a window of its own: a window holds at most 32 controls, and controls left out of an answer lose
their values. The report is a two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

MAX_LESIONS = 4  # 9 exam controls + 4 x 10 lesion controls stay under the host's 64 controls per instance

SIDES = [rp.tr("Right"), rp.tr("Left"), rp.tr("Midline"), rp.tr("Bilateral")]
LEVELS = [rp.tr("Base"), rp.tr("Midgland"), rp.tr("Apex")]
SECTORS = {  # option English id -> zone the v2.1 assessment rules use
    "Peripheral zone, posterolateral (PZpl)": "PZ",
    "Peripheral zone, posteromedial (PZpm)": "PZ",
    "Peripheral zone, anterior (PZa)": "PZ",
    "Transition zone, anterior (TZa)": "TZ",
    "Transition zone, posterior (TZp)": "TZ",
    "Central zone (CZ)": "CZ",
    "Anterior fibromuscular stroma (AS)": "AS",
}
SECTOR_OPTIONS = [
    rp.tr("Peripheral zone, posterolateral (PZpl)"),
    rp.tr("Peripheral zone, posteromedial (PZpm)"),
    rp.tr("Peripheral zone, anterior (PZa)"),
    rp.tr("Transition zone, anterior (TZa)"),
    rp.tr("Transition zone, posterior (TZp)"),
    rp.tr("Central zone (CZ)"),
    rp.tr("Anterior fibromuscular stroma (AS)"),
]
SCORES = ["1", "2", "3", "4", "5"]
DWI = SCORES + [rp.tr("Inadequate")]
DCE = [rp.tr("Negative"), rp.tr("Positive"), rp.tr("Not performed or inadequate")]
EPE = [rp.tr("Not seen"), rp.tr("Suspected"), rp.tr("Present")]
# Plain text: options are told apart by their English id, and one "PI-RADS {n}" id would make them one option.
MANUAL = [rp.tr("Assign manually")] + ["PI-RADS %d" % n for n in range(1, 6)]
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


def pick(c, name, options):
    """The option whose English id ctx.controls holds for `name`, else the first."""
    return next((o for o in options if str(o) == c.get(name)), options[0])


class Form:
    """Controls built from ctx.controls and the report rows they produce, in the same order."""

    def __init__(self, c):
        self.c, self.rows = c, []

    def choice(self, name, label, options, report=True):
        value = pick(self.c, name, options)
        if report:
            self.rows.append([label, value])
        return rp.Choice(name, label, options, str(value)), value

    def number(self, name, label, hi, step):
        value = min(max(float(self.c.get(name, 0.0)), 0.0), hi)
        return rp.Number(name, label, value, min=0, max=hi, step=step), value


def lesion(f, i):
    """The controls of lesion `i` (they fill `f.rows`) and its category (None: not assigned)."""
    c = f.c
    f.rows.append([rp.tr("Lesion {n}", n=i), ""])
    side = f.choice("side_%d" % i, rp.tr("Side"), SIDES)[0]
    lvl = f.choice("level_%d" % i, rp.tr("Level"), LEVELS)[0]
    sector, where = f.choice("sector_%d" % i, rp.tr("Sector"), SECTOR_OPTIONS)
    size_ctl, size = f.number("size_%d" % i, rp.tr("Largest diameter (mm)"), 100, 1)
    if size > 0:
        f.rows.append([rp.tr("Largest diameter"), "%g mm" % size])
    t2_ctl, t2 = f.choice("t2_%d" % i, rp.tr("T2W score"), SCORES)
    dwi_ctl, dwi = f.choice("dwi_%d" % i, rp.tr("DWI score"), DWI)
    dce_ctl, dce = f.choice("dce_%d" % i, rp.tr("DCE"), DCE)
    zone = SECTORS[str(where)]
    dce_value = {"Negative": False, "Positive": True}.get(str(dce))
    auto = category(zone, int(t2), int(dwi) if str(dwi) in SCORES else None, dce_value)
    blocks = [rp.Row([side, lvl]), sector, size_ctl, rp.Row([t2_ctl, dwi_ctl, dce_ctl])]
    if auto is None:
        manual_ctl, manual = f.choice("manual_%d" % i, rp.tr("Category"), MANUAL, report=False)
        blocks += [
            rp.Label(
                rp.tr(
                    "No PI-RADS v2.1 rule applies (central zone, inadequate DWI) or the anterior stroma lesion is "
                    "scored with the zone it arises from: assign the category."
                ),
                weak=True,
            ),
            manual_ctl,
        ]
        auto = MANUAL.index(manual) or None
    blocks.append(f.choice("epe_%d" % i, rp.tr("Extraprostatic extension"), EPE)[0])
    svi = bool(c.get("svi_%d" % i, False))
    blocks.append(rp.Checkbox("svi_%d" % i, rp.tr("Seminal vesicle invasion"), svi))
    if svi:
        f.rows.append([rp.tr("Seminal vesicle invasion"), rp.tr("Present")])
    f.rows.append([rp.tr("PI-RADS"), CATEGORIES[auto] if auto else rp.tr("Not assigned")])
    blocks.append(rp.Label(CATEGORIES[auto] if auto else rp.tr("Not assigned")))
    return blocks, auto


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    f = Form(c)
    dims = [
        f.number(name, label, 150, 1)
        for name, label in (
            ("ap", rp.tr("Anteroposterior (mm)")),
            ("tv", rp.tr("Transverse (mm)")),
            ("cc", rp.tr("Craniocaudal (mm)")),
        )
    ]
    psa_ctl, psa = f.number("psa", rp.tr("PSA (ng/ml)"), 1000, 0.1)
    ml = volume_ml(*(v for _, v in dims))
    if ml > 0:
        f.rows.append([rp.tr("Prostate volume"), "%.1f ml" % ml])
        if psa > 0:
            f.rows.append([rp.tr("PSA density"), "%.2f ng/ml/ml" % (psa / ml)])
    count = int(min(max(c.get("count", 1), 0), MAX_LESIONS))
    head = [
        rp.Row([ctl for ctl, _ in dims]),
        psa_ctl,
        rp.Number("count", rp.tr("Lesions"), count, min=0, max=MAX_LESIONS, step=1),
    ]

    windows, found = [], []
    for i in range(1, count + 1):
        blocks, cat = lesion(f, i)
        found.append(cat or 0)
        windows.append(
            rp.Window("lesion_%d" % i, rp.tr("Lesion {n}", n=i), blocks, size=(480, 400), reopen=ctx.event == "count")
        )

    staging = []
    for name, label in (("nodes", rp.tr("Suspicious pelvic lymph nodes")), ("bone", rp.tr("Suspicious bone lesions"))):
        on = bool(c.get(name, False))
        staging.append(rp.Checkbox(name, label, on))
        f.rows.append([label, rp.tr("Present") if on else rp.tr("Not seen")])
    top = max(found, default=0)
    f.rows.append(
        [rp.tr("Overall assessment"), CATEGORIES[top] if top else rp.tr("No lesion with an assigned PI-RADS category")]
    )
    comment = str(c.get("comment", "")).strip()
    if comment:
        f.rows.append([rp.tr("Comment"), comment])
    blocks = head + [
        rp.Row(staging),
        rp.TextField("comment", rp.tr("Comment"), comment, max_length=500),
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(f.rows),
        rp.Label(
            rp.tr(
                "PI-RADS v2.1 (Turkbey et al., Eur Urol 2019). The category is computed from the scores the "
                "reader enters; scores of 1-2 need no lesion entry. Not a medical device: check every line "
                "before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("PI-RADS report"), blocks, size=(560, 700))] + windows)

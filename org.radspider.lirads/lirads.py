"""LI-RADS structured liver CT/MRI report: up to five observations in patients at high risk for hepatocellular
carcinoma, each with its segment, size and major features, the LI-RADS v2018 diagnostic category (computed from the
diagnostic table, adjusted by ancillary features) or the category the reader assigns before the table (LR-NC, LR-1,
LR-2, LR-M, LR-TIV), and the management of each category.

Each observation has a window of its own: a window holds at most 32 controls, and controls left out of an answer lose
their values. The report is a two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

MAX_OBSERVATIONS = 5  # 4 exam controls + 5 x 8 observation controls stay under the host's 64 controls per instance

MODALITIES = [rp.tr("CT"), rp.tr("MRI with extracellular contrast"), rp.tr("MRI with hepatobiliary contrast")]
SEGMENTS = ["I", "II", "III", "IVa", "IVb", "V", "VI", "VII", "VIII"]
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


def observation(f, i):
    """The controls of observation `i` (they fill `f.rows`) and its category code."""
    c = f.c
    f.rows.append([rp.tr("Observation {n}", n=i), ""])
    segment = f.choice("segment_%d" % i, rp.tr("Segment"), SEGMENTS)[0]
    size = min(max(float(c.get("size_%d" % i, 0.0)), 0.0), 300.0)
    size_ctl = rp.Number("size_%d" % i, rp.tr("Largest diameter (mm)"), size, min=0, max=300, step=1)
    if size > 0:
        f.rows.append([rp.tr("Largest diameter"), "%g mm" % size])
    path_ctl, path = f.choice("path_%d" % i, rp.tr("Category"), PATHS, report=False)
    blocks = [rp.Row([segment, size_ctl]), path_ctl]
    if path is not TABLE:
        code = str(path).split(":")[0]
    else:
        aphe_ctl, aphe = f.choice("aphe_%d" % i, rp.tr("Arterial phase"), APHE)
        on = {name: bool(c.get("%s_%d" % (name, i), False)) for name, _ in FEATURES}
        boxes = [rp.Checkbox("%s_%d" % (name, i), label, on[name]) for name, label in FEATURES]
        found = [label for name, label in FEATURES if on[name]]
        f.rows += [[rp.tr("Additional major features"), label] for label in found] or [
            [rp.tr("Additional major features"), rp.tr("None")]
        ]
        anc_ctl, anc = f.choice("ancillary_%d" % i, rp.tr("Ancillary features"), ANCILLARY)
        blocks += [aphe_ctl, rp.Section(rp.tr("Additional major features"), boxes), anc_ctl]
        if size <= 0:
            blocks.append(rp.Label(rp.tr("Enter the size: the diagnostic table needs it."), weak=True))
            code = None
        else:
            code = adjust(
                table_category(str(aphe) == str(APHE[1]), size, on["washout"], on["capsule"], on["growth"]), str(anc)
            )
    name = CATEGORIES[code][0] if code else rp.tr("Not assigned")
    f.rows.append([rp.tr("LI-RADS"), name])
    if code:
        f.rows.append([rp.tr("Management"), CATEGORIES[code][1]])
    blocks.append(rp.Label(name))
    return blocks, code


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    f = Form(c)
    risk = bool(c.get("at_risk", True))
    head = [
        f.choice("modality", rp.tr("Exam"), MODALITIES)[0],
        rp.Checkbox(
            "at_risk",
            rp.tr("Patient at high risk for HCC (cirrhosis, chronic hepatitis B, current or prior HCC)"),
            risk,
        ),
    ]
    windows, found = [], []
    if risk:
        count = int(min(max(c.get("count", 1), 0), MAX_OBSERVATIONS))
        head.append(rp.Number("count", rp.tr("Observations"), count, min=0, max=MAX_OBSERVATIONS, step=1))
        for i in range(1, count + 1):
            blocks, code = observation(f, i)
            if code:
                found.append(code)
            windows.append(
                rp.Window(
                    "observation_%d" % i,
                    rp.tr("Observation {n}", n=i),
                    blocks,
                    size=(480, 420),
                    reopen=ctx.event == "count",
                )
            )
        if not count:
            f.rows.append([rp.tr("Observations"), rp.tr("None")])
        top = max(found, key=ORDER.index, default=None)
        f.rows.append([rp.tr("Most worrying observation"), CATEGORIES[top][0] if top else rp.tr("None")])
    else:
        f.rows.append([rp.tr("LI-RADS"), rp.tr("Not applicable: the patient is not in the LI-RADS population")])
    comment = str(c.get("comment", "")).strip()
    if comment:
        f.rows.append([rp.tr("Comment"), comment])
    blocks = head + [
        rp.TextField("comment", rp.tr("Comment"), comment, max_length=500),
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(f.rows),
        rp.Label(
            rp.tr(
                "LI-RADS CT/MRI v2018 diagnostic algorithm. LR-NC, LR-TIV, LR-1, LR-2 and LR-M are the "
                "reader's call before the table; treated observations (LR-TR) are not covered. Not a medical "
                "device: check every line before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("LI-RADS report"), blocks, size=(560, 640))] + windows)

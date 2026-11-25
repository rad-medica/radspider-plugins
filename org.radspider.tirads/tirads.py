"""TI-RADS structured thyroid report: up to four nodules scored with ACR TI-RADS (Tessler et al., JACR 2017), the
cervical lymph node map by level and side (ETA 2013 ultrasound classification), and an optional clinical TNM stage of
differentiated thyroid carcinoma (AJCC 8th edition).

Each nodule has a window of its own: a window holds at most 32 controls, and controls left out of an answer lose
their values. The report is a two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

MAX_NODULES = 4  # 19 main controls + 4 x 11 nodule controls stay under the host's 64 controls per instance

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
FOCI = [  # (control name, label, points): echogenic foci add up; none or large comet-tail artifacts score 0
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
NODE_LEVELS = [  # (control name, label, central: VI and VII give N1a, the lateral levels N1b)
    ("ln_r1", rp.tr("Right level I"), False),
    ("ln_l1", rp.tr("Left level I"), False),
    ("ln_r2", rp.tr("Right level II"), False),
    ("ln_l2", rp.tr("Left level II"), False),
    ("ln_r3", rp.tr("Right level III"), False),
    ("ln_l3", rp.tr("Left level III"), False),
    ("ln_r4", rp.tr("Right level IV"), False),
    ("ln_l4", rp.tr("Left level IV"), False),
    ("ln_r5", rp.tr("Right level V"), False),
    ("ln_l5", rp.tr("Left level V"), False),
    ("ln_6", rp.tr("Level VI (central)"), True),
    ("ln_7", rp.tr("Level VII (upper mediastinum)"), True),
]

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


def n_category(states):
    """cN from {level control name: state English id}: suspicious lateral nodes N1b, else central N1a, else N0."""
    suspicious = [central for name, _, central in NODE_LEVELS if states.get(name) == "Suspicious"]
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

    def number(self, name, label, lo, hi):
        value = min(max(float(self.c.get(name, 0.0)), lo), hi)
        return rp.Number(name, label, value, min=lo, max=hi, step=1), value


def nodule(f, i):
    """The controls of nodule `i` (they fill `f.rows`) and its TR level."""
    c = f.c
    f.rows.append([rp.tr("Nodule {n}", n=i), ""])
    where = f.choice("where_%d" % i, rp.tr("Location"), LOCATIONS)[0]
    sizes = [
        f.number("%s_%d" % (axis, i), label, 0, 150)
        for axis, label in (
            ("ap", rp.tr("Anteroposterior (mm)")),
            ("tv", rp.tr("Transverse (mm)")),
            ("cc", rp.tr("Longitudinal (mm)")),
        )
    ]
    dims = [v for _, v in sizes if v > 0]
    if dims:
        f.rows.append([rp.tr("Size"), " × ".join("%g" % v for v in dims) + " mm"])
    features = []
    ids = []
    for name, label, table in (
        ("comp", rp.tr("Composition"), COMPOSITION),
        ("echo", rp.tr("Echogenicity"), ECHOGENICITY),
        ("shape", rp.tr("Shape"), SHAPE),
        ("margin", rp.tr("Margin"), MARGIN),
    ):
        ctl, value = f.choice("%s_%d" % (name, i), label, [o for o, _ in table])
        features.append(ctl)
        ids.append(str(value))
    foci = [name for name, _, _ in FOCI if c.get("%s_%d" % (name, i), False)]
    boxes = [rp.Checkbox("%s_%d" % (name, i), label, name in foci) for name, label, _ in FOCI]
    for name, label, _ in FOCI:
        if name in foci:
            f.rows.append([rp.tr("Echogenic foci"), label])
    if not foci:
        f.rows.append([rp.tr("Echogenic foci"), NO_FOCI])
    score = points(*ids, foci)
    tr = level(score)
    size = max(dims, default=0.0)
    fna, schedule = advice(tr, size)
    f.rows.append([rp.tr("ACR TI-RADS"), LEVELS[tr][0]])
    f.rows.append([rp.tr("Points"), score])
    if LEVELS[tr][1] is None:
        f.rows.append([rp.tr("Recommendation"), rp.tr("No FNA")])
    elif not dims:
        f.rows.append([rp.tr("Recommendation"), rp.tr("Enter the size to get the recommendation")])
    elif fna:
        f.rows.append([rp.tr("Recommendation"), rp.tr("FNA (from {mm} mm at this level)", mm=LEVELS[tr][1])])
    elif schedule:
        f.rows.append([rp.tr("Recommendation"), schedule])
    else:
        f.rows.append([rp.tr("Recommendation"), rp.tr("No FNA or follow-up for its size")])
    blocks = [
        where,
        rp.Row([ctl for ctl, _ in sizes]),
        rp.Row(features[:2]),
        rp.Row(features[2:]),
        rp.Section(rp.tr("Echogenic foci (all that apply)"), boxes),
        rp.Row([rp.Label(rp.trn(score, "{n} point", "{n} points")), rp.Label(LEVELS[tr][0])]),
    ]
    return blocks, tr, size


@rp.tool("report")
def report(volume, ctx):
    c = ctx.controls
    f = Form(c)
    count = int(min(max(c.get("count", 1), 0), MAX_NODULES))
    head = [rp.Number("count", rp.tr("Nodules"), count, min=0, max=MAX_NODULES, step=1)]

    windows = []
    for i in range(1, count + 1):
        blocks, _, _ = nodule(f, i)
        windows.append(
            rp.Window("nodule_%d" % i, rp.tr("Nodule {n}", n=i), blocks, size=(480, 420), reopen=ctx.event == "count")
        )
    if not count:
        f.rows.append([rp.tr("Thyroid nodules"), rp.tr("None")])

    states = {name: str(pick(c, name, NODE_STATES)) for name, _, _ in NODE_LEVELS}
    levels = [f.choice(name, label, NODE_STATES, report=False)[0] for name, label, _ in NODE_LEVELS]
    abnormal = [(label, pick(c, name, NODE_STATES)) for name, label, _ in NODE_LEVELS if states[name] != "Normal"]
    f.rows += [[label, state] for label, state in abnormal] or [
        [rp.tr("Cervical lymph nodes"), rp.tr("No indeterminate or suspicious lymph nodes in levels I to VII")]
    ]
    neck = rp.Section(
        rp.tr("Cervical lymph nodes by level"),
        [rp.Row(levels[k : k + 2]) for k in range(0, len(levels) - 2, 2)]
        + [
            rp.Row(levels[-2:]),
            rp.Label(
                rp.tr(
                    "Suspicious: microcalcifications, cystic change, peripheral or diffuse increased vascularity, or "
                    "hyperechoic tissue like thyroid. Indeterminate: no hilum and none of these. Normal: hilum present "
                    "(ETA 2013)."
                ),
                weak=True,
            ),
        ],
    )

    staged = pick(c, "staging", STAGING)
    staging = [rp.Choice("staging", rp.tr("TNM staging"), STAGING, str(staged))]
    if str(staged) != "Not staged":
        size_ctl, size = f.number("t_size", rp.tr("Tumour largest diameter (mm)"), 0, 200)
        ext_ctl, ext = f.choice("t_ext", rp.tr("Extension"), EXTENSION, report=False)
        age_ctl, age = f.choice("age", rp.tr("Age at diagnosis"), AGES, report=False)
        m_ctl, m = f.choice("m", rp.tr("Distant metastases"), METASTASES, report=False)
        t = t_category(size, str(ext))
        n = n_category(states)
        m_code = "M1" if str(m).startswith("M1") else "M0"
        group = stage(t, n, str(age) == "55 years or older", m_code == "M1")
        staging += [rp.Row([size_ctl, age_ctl]), ext_ctl, m_ctl]
        f.rows += [
            [rp.tr("Clinical TNM (AJCC 8th edition)"), "c%s c%s c%s" % (t, n, m_code)],
            [rp.tr("Stage (differentiated thyroid carcinoma)"), group],
        ]

    comment = str(c.get("comment", "")).strip()
    if comment:
        f.rows.append([rp.tr("Comment"), comment])
    blocks = head + [
        neck,
        rp.Section(rp.tr("Staging"), staging),
        rp.TextField("comment", rp.tr("Comment"), comment, max_length=500),
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(f.rows),
        rp.Label(
            rp.tr(
                "ACR TI-RADS (Tessler et al., JACR 2017); lymph nodes: ETA 2013; TNM: AJCC 8th "
                "edition, clinical, for differentiated carcinoma only. Not a medical device: "
                "check every line before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("TI-RADS report"), blocks, size=(560, 760))] + windows)

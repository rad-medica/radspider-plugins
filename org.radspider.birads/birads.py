"""BI-RADS structured breast report: exam, breast composition, up to four findings described with the BI-RADS
lexicon (mammography, ultrasound, MRI), the reader's assessment category per finding, the overall assessment, its
management and likelihood of malignancy. BI-RADS has no scoring algorithm: every category is the reader's choice; the
plugin only applies the ACR hierarchy for the overall assessment and the standard wording.

Each finding has a window of its own: a window holds at most 32 controls, and controls left out of an answer lose
their values. The report is a two-column table; *Copy table* puts it on the clipboard as tab-separated lines."""

import radspider_plugin as rp

MAX_FINDINGS = 4  # 7 exam controls + 4 x 14 finding controls stay under the host's 64 controls per instance

MAMMO, US, BOTH, MRI = rp.tr("Mammography"), rp.tr("Ultrasound"), rp.tr("Mammography and ultrasound"), rp.tr("MRI")
MODALITIES = [MAMMO, US, BOTH, MRI]
INDICATIONS = [rp.tr("Screening"), rp.tr("Diagnostic"), rp.tr("Follow-up"), rp.tr("Staging of known cancer")]
SIDES = [rp.tr("Bilateral"), rp.tr("Right"), rp.tr("Left")]
COMPOSITION = [
    rp.tr("a. The breasts are almost entirely fatty"),
    rp.tr("b. There are scattered areas of fibroglandular density"),
    rp.tr("c. The breasts are heterogeneously dense, which may obscure small masses"),
    rp.tr("d. The breasts are extremely dense, which lowers the sensitivity of mammography"),
]
ECHOTEXTURE = [
    rp.tr("Homogeneous background echotexture: fat"),
    rp.tr("Homogeneous background echotexture: fibroglandular"),
    rp.tr("Heterogeneous background echotexture"),
]
FGT = [
    rp.tr("a. Almost entirely fat"),
    rp.tr("b. Scattered fibroglandular tissue"),
    rp.tr("c. Heterogeneous fibroglandular tissue"),
    rp.tr("d. Extreme fibroglandular tissue"),
]
BPE = [rp.tr("Minimal"), rp.tr("Mild"), rp.tr("Moderate"), rp.tr("Marked")]

MASS, CALC, NME = rp.tr("Mass"), rp.tr("Calcifications"), rp.tr("Non-mass enhancement")
FINDING_TYPES = [
    MASS,
    CALC,
    rp.tr("Asymmetry"),
    rp.tr("Focal asymmetry"),
    rp.tr("Global asymmetry"),
    rp.tr("Developing asymmetry"),
    rp.tr("Architectural distortion"),
    rp.tr("Focus"),
    NME,
    rp.tr("Simple cyst"),
    rp.tr("Complicated cyst"),
    rp.tr("Clustered microcysts"),
    rp.tr("Intramammary lymph node"),
    rp.tr("Axillary lymph node"),
    rp.tr("Skin lesion"),
    rp.tr("Solitary dilated duct"),
]
FINDING_SIDES = [rp.tr("Right"), rp.tr("Left")]
# Clock positions stay plain text: options are told apart by their English id, and "{h} o'clock" would be one id.
LOCATIONS = ["%d:00" % h for h in range(1, 13)] + [rp.tr("Retroareolar"), rp.tr("Central"), rp.tr("Axillary tail")]
DEPTHS = [rp.tr("Not stated"), rp.tr("Anterior third"), rp.tr("Middle third"), rp.tr("Posterior third")]

SHAPE = [rp.tr("Oval"), rp.tr("Round"), rp.tr("Irregular")]
MARGIN = {
    "mammo": [
        rp.tr("Circumscribed"),
        rp.tr("Obscured"),
        rp.tr("Microlobulated"),
        rp.tr("Indistinct"),
        rp.tr("Spiculated"),
    ],
    "us": [rp.tr("Circumscribed"), rp.tr("Indistinct"), rp.tr("Angular"), rp.tr("Microlobulated"), rp.tr("Spiculated")],
    "both": [
        rp.tr("Circumscribed"),
        rp.tr("Obscured"),
        rp.tr("Indistinct"),
        rp.tr("Angular"),
        rp.tr("Microlobulated"),
        rp.tr("Spiculated"),
    ],
    "mri": [rp.tr("Circumscribed"), rp.tr("Irregular"), rp.tr("Spiculated")],
}
DENSITY = [rp.tr("Equal density"), rp.tr("High density"), rp.tr("Low density"), rp.tr("Fat-containing")]
ORIENTATION = [rp.tr("Parallel"), rp.tr("Not parallel")]
ECHO = [
    rp.tr("Anechoic"),
    rp.tr("Hyperechoic"),
    rp.tr("Complex cystic and solid"),
    rp.tr("Hypoechoic"),
    rp.tr("Isoechoic"),
    rp.tr("Heterogeneous"),
]
POSTERIOR = [
    rp.tr("No posterior features"),
    rp.tr("Posterior enhancement"),
    rp.tr("Posterior shadowing"),
    rp.tr("Combined posterior pattern"),
]
MASS_ENHANCEMENT = [
    rp.tr("Homogeneous"),
    rp.tr("Heterogeneous"),
    rp.tr("Rim enhancement"),
    rp.tr("Dark internal septations"),
]
MORPHOLOGY = [
    rp.tr("Typically benign: skin"),
    rp.tr("Typically benign: vascular"),
    rp.tr("Typically benign: coarse or popcorn-like"),
    rp.tr("Typically benign: large rod-like"),
    rp.tr("Typically benign: round"),
    rp.tr("Typically benign: rim"),
    rp.tr("Typically benign: dystrophic"),
    rp.tr("Typically benign: milk of calcium"),
    rp.tr("Typically benign: suture"),
    rp.tr("Suspicious: amorphous"),
    rp.tr("Suspicious: coarse heterogeneous"),
    rp.tr("Suspicious: fine pleomorphic"),
    rp.tr("Suspicious: fine linear or fine-linear branching"),
]
DISTRIBUTION = [rp.tr("Grouped"), rp.tr("Diffuse"), rp.tr("Regional"), rp.tr("Linear"), rp.tr("Segmental")]
NME_DISTRIBUTION = [
    rp.tr("Focal"),
    rp.tr("Linear"),
    rp.tr("Segmental"),
    rp.tr("Regional"),
    rp.tr("Multiple regions"),
    rp.tr("Diffuse"),
]
NME_ENHANCEMENT = [rp.tr("Homogeneous"), rp.tr("Heterogeneous"), rp.tr("Clumped"), rp.tr("Clustered ring")]
INITIAL = [rp.tr("Not assessed"), rp.tr("Slow"), rp.tr("Medium"), rp.tr("Fast")]
DELAYED = [rp.tr("Not assessed"), rp.tr("Persistent"), rp.tr("Plateau"), rp.tr("Washout")]

# (option, management, likelihood of malignancy), ACR BI-RADS Atlas 5th edition (2013), assessment categories.
CATEGORIES = {
    "0": (
        rp.tr("BI-RADS 0: incomplete, needs additional imaging evaluation and/or prior examinations for comparison"),
        rp.tr("Recall for additional imaging and/or comparison with prior examination(s)"),
        rp.tr("Not applicable"),
    ),
    "1": (rp.tr("BI-RADS 1: negative"), rp.tr("Routine screening"), rp.tr("Essentially 0%")),
    "2": (rp.tr("BI-RADS 2: benign"), rp.tr("Routine screening"), rp.tr("Essentially 0%")),
    "3": (
        rp.tr("BI-RADS 3: probably benign"),
        rp.tr("Short-interval (6-month) follow-up or continued surveillance"),
        rp.tr("More than 0% but 2% or less"),
    ),
    "4": (rp.tr("BI-RADS 4: suspicious"), rp.tr("Tissue diagnosis"), rp.tr("More than 2% but less than 95%")),
    "4A": (rp.tr("BI-RADS 4A: low suspicion for malignancy"), rp.tr("Tissue diagnosis"), rp.tr("More than 2% to 10%")),
    "4B": (
        rp.tr("BI-RADS 4B: moderate suspicion for malignancy"),
        rp.tr("Tissue diagnosis"),
        rp.tr("More than 10% to 50%"),
    ),
    "4C": (
        rp.tr("BI-RADS 4C: high suspicion for malignancy"),
        rp.tr("Tissue diagnosis"),
        rp.tr("More than 50% to less than 95%"),
    ),
    "5": (rp.tr("BI-RADS 5: highly suggestive of malignancy"), rp.tr("Tissue diagnosis"), rp.tr("95% or more")),
    "6": (
        rp.tr("BI-RADS 6: known biopsy-proven malignancy"),
        rp.tr("Surgical excision when clinically appropriate"),
        rp.tr("Not applicable"),
    ),
}
# The ACR order for the overall assessment, least to most worrying: 1, 2, 3, 6, 0, 4, 5 (4A < 4B < 4C).
HIERARCHY = ["1", "2", "3", "6", "0", "4A", "4", "4B", "4C", "5"]
HIGHEST = rp.tr("Highest of the findings")


def codes(modality):
    """The categories offered: BI-RADS subdivides 4 into 4A-4C for mammography and ultrasound, not for MRI."""
    return [c for c in CATEGORIES if (c == "4") == (modality == "mri") or not c.startswith("4")]


def overall(categories):
    """The overall assessment of the findings' categories (ACR hierarchy); "1" without findings."""
    return max(categories, key=HIERARCHY.index, default="1")


def pick(c, name, options):
    """The option whose English id ctx.controls holds for `name`, else the first."""
    return next((o for o in options if str(o) == c.get(name)), options[0])


def kind(modality):
    return {str(MAMMO): "mammo", str(US): "us", str(BOTH): "both", str(MRI): "mri"}[str(modality)]


class Form:
    """Controls built from ctx.controls and the report rows they produce, in the same order."""

    def __init__(self, c):
        self.c, self.rows = c, []

    def choice(self, name, label, options, report=None):
        value = pick(self.c, name, options)
        if report is not False:
            self.rows.append([report or label, value])
        return rp.Choice(name, label, options, str(value)), value

    def number(self, name, label, unit, lo, hi, step):
        value = min(max(float(self.c.get(name, 0.0)), lo), hi)
        if value > 0:
            self.rows.append([label, "%g %s" % (round(value, 1), unit)])
        return rp.Number(name, label, value, min=lo, max=hi, step=step), value

    def text(self, name, label):
        value = str(self.c.get(name, "")).strip()
        if value:
            self.rows.append([label, value])
        return rp.TextField(name, label, value, max_length=500)


def finding(f, i, mod):
    """The controls of finding `i` (they fill `f.rows`) and its category code."""
    blocks = []
    ctl, ftype = f.choice("type_%d" % i, rp.tr("Finding"), FINDING_TYPES, rp.tr("Finding {n}", n=i))
    blocks.append(ctl)
    blocks.append(
        rp.Row(
            [
                f.choice("side_%d" % i, rp.tr("Breast"), FINDING_SIDES)[0],
                f.choice("where_%d" % i, rp.tr("Location"), LOCATIONS)[0],
            ]
        )
    )
    blocks.append(
        rp.Row(
            [
                f.choice("depth_%d" % i, rp.tr("Depth"), DEPTHS)[0],
                f.number("nipple_%d" % i, rp.tr("Distance from the nipple"), "cm", 0, 30, 0.5)[0],
                f.number("size_%d" % i, rp.tr("Largest diameter"), "mm", 0, 300, 1)[0],
            ]
        )
    )
    mammo, us, mri = mod in ("mammo", "both"), mod in ("us", "both"), mod == "mri"
    described = []
    if str(ftype) == str(MASS):
        described += [
            f.choice("shape_%d" % i, rp.tr("Shape"), SHAPE)[0],
            f.choice("margin_%d" % i, rp.tr("Margin"), MARGIN[mod])[0],
        ]
        if mammo:
            described.append(f.choice("density_%d" % i, rp.tr("Density"), DENSITY)[0])
        if us:
            described += [
                f.choice("orient_%d" % i, rp.tr("Orientation"), ORIENTATION)[0],
                f.choice("echo_%d" % i, rp.tr("Echo pattern"), ECHO)[0],
                f.choice("post_%d" % i, rp.tr("Posterior features"), POSTERIOR)[0],
            ]
        if mri:
            described.append(f.choice("inner_%d" % i, rp.tr("Internal enhancement"), MASS_ENHANCEMENT)[0])
    elif str(ftype) == str(CALC):
        described += [
            f.choice("morph_%d" % i, rp.tr("Morphology"), MORPHOLOGY)[0],
            f.choice("dist_%d" % i, rp.tr("Distribution"), DISTRIBUTION)[0],
        ]
    elif str(ftype) == str(NME):
        described += [
            f.choice("nmedist_%d" % i, rp.tr("Distribution"), NME_DISTRIBUTION)[0],
            f.choice("nmeinner_%d" % i, rp.tr("Internal enhancement"), NME_ENHANCEMENT)[0],
        ]
    if mri and str(ftype) in (str(MASS), str(NME), "Focus"):
        described += [
            f.choice("initial_%d" % i, rp.tr("Kinetics: initial phase"), INITIAL)[0],
            f.choice("delayed_%d" % i, rp.tr("Kinetics: delayed phase"), DELAYED)[0],
        ]
    if described:
        blocks.append(
            rp.Section(rp.tr("Descriptors"), [rp.Row(described[k : k + 3]) for k in range(0, len(described), 3)])
        )
    blocks.append(f.text("notes_%d" % i, rp.tr("Associated features and notes")))
    options = [CATEGORIES[k][0] for k in codes(mod)]
    ctl, cat = f.choice("cat_%d" % i, rp.tr("Assessment"), options, rp.tr("BI-RADS"))
    blocks.append(ctl)
    return blocks, next(k for k in CATEGORIES if CATEGORIES[k][0] is cat)


@rp.tool("report")
def report(volume, ctx):
    f = Form(ctx.controls)
    ctl_mod, modality = f.choice("modality", rp.tr("Exam"), MODALITIES)
    mod = kind(modality)
    head = [
        rp.Row(
            [
                ctl_mod,
                f.choice("indication", rp.tr("Indication"), INDICATIONS)[0],
                f.choice("side", rp.tr("Breasts"), SIDES)[0],
            ]
        )
    ]
    if mod in ("mammo", "both"):
        head.append(f.choice("composition", rp.tr("Breast composition"), COMPOSITION)[0])
    if mod in ("us", "both"):
        head.append(f.choice("echotexture", rp.tr("Tissue composition (ultrasound)"), ECHOTEXTURE)[0])
    if mod == "mri":
        head.append(
            rp.Row(
                [
                    f.choice("fgt", rp.tr("Fibroglandular tissue"), FGT)[0],
                    f.choice("bpe", rp.tr("Background parenchymal enhancement"), BPE)[0],
                ]
            )
        )
    count = int(min(max(ctx.controls.get("count", 0), 0), MAX_FINDINGS))
    head.append(rp.Number("count", rp.tr("Findings"), count, min=0, max=MAX_FINDINGS, step=1))

    windows, found = [], []
    for i in range(1, count + 1):
        blocks, code = finding(f, i, mod)
        found.append(code)
        windows.append(
            rp.Window("finding_%d" % i, rp.tr("Finding {n}", n=i), blocks, size=(460, 420), reopen=ctx.event == "count")
        )

    auto = overall(found)
    options = [HIGHEST] + [CATEGORIES[k][0] for k in codes(mod)]
    final = pick(ctx.controls, "overall", options)
    code = auto if final is HIGHEST else next(k for k in CATEGORIES if CATEGORIES[k][0] is final)
    if code not in codes(mod):  # a category of another modality left from before the exam changed
        code = auto
    name, management, likelihood = CATEGORIES[code]
    head.append(rp.Choice("overall", rp.tr("Overall assessment"), options, str(final)))
    f.rows += [
        [rp.tr("Overall assessment"), name],
        [rp.tr("Management"), management],
        [rp.tr("Likelihood of malignancy"), likelihood],
    ]
    head.append(f.text("comment", rp.tr("Comment")))

    blocks = head + [
        rp.Separator(),
        rp.Label(rp.tr("Report")),
        rp.Table(f.rows),
        rp.Label(
            rp.tr(
                "Categories are the reader's choice; the overall assessment follows the ACR hierarchy "
                "(1, 2, 3, 6, 0, 4, 5). Lexicon and wording: ACR BI-RADS Atlas, 5th edition. Not a medical "
                "device: check every line before signing."
            ),
            weak=True,
        ),
    ]
    return rp.Result(windows=[rp.Window("main", rp.tr("BI-RADS report"), blocks, size=(560, 720))] + windows)

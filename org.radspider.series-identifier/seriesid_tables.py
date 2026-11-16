"""Data tables of org.radspider.series-identifier: tags, keywords, codes, thresholds, explanations.

Pure data, no radspider_plugin import. Every result id that `seriesid_rules.identify` returns is a key of EXPLAIN.
Ids with `{name}` placeholders are templates: their arguments are data (numbers, codes, tag values), never words
that would need translating.
"""

import re

# The 32 tags of the manifest (spec §1), tag -> DICOM keyword-style name used in evidence and messages.
TAGS = {
    "0008,0008": "Image Type",
    "0008,0070": "Manufacturer",
    "0008,103E": "Series Description",
    "0018,1030": "Protocol Name",
    "0018,0015": "Body Part Examined",
    "0018,0050": "Slice Thickness",
    "0018,0010": "Contrast/Bolus Agent",
    "0018,5101": "View Position",
    "0020,0060": "Laterality",
    "0020,0062": "Image Laterality",
    "0020,0020": "Patient Orientation",
    "0018,1510": "Positioner Primary Angle",
    "0018,1511": "Positioner Secondary Angle",
    "0018,1210": "Convolution Kernel",
    "0054,1000": "Series Type",
    "0054,1001": "Units",
    "0018,0020": "Scanning Sequence",
    "0018,0021": "Sequence Variant",
    "0018,0024": "Sequence Name",
    "0018,0023": "MR Acquisition Type",
    "0018,0080": "Repetition Time",
    "0018,0081": "Echo Time",
    "0018,0082": "Inversion Time",
    "0018,0083": "Number of Averages",
    "0018,0084": "Imaging Frequency",
    "0018,0091": "Echo Train Length",
    "0018,0095": "Pixel Bandwidth",
    "0018,1314": "Flip Angle",
    "0018,1316": "SAR",
    "0018,1318": "dB/dt",
    "0018,9087": "Diffusion b-value",
    "0018,9089": "Diffusion Gradient Orientation",
}

ITEMS = ("series", "plane", "projection", "region", "laterality", "contrast", "model")

# Modality codes handled by the projection-radiography rules (DICOM Modality codes; section not fetched).
XR_MODALITIES = {
    "CR": "Radiograph",
    "DX": "Radiograph",
    "RF": "Fluoroscopy image",
    "PX": "Panoramic dental radiograph",
    "IO": "Intra-oral dental radiograph",
}

# --- Plane ---------------------------------------------------------------------------------------------------------

PLANE_IDS = {"axial": "Axial", "coronal": "Coronal", "sagittal": "Sagittal"}
OBLIQUE_IDS = {
    "axial": "Oblique, closest to axial ({deg}°)",
    "coronal": "Oblique, closest to coronal ({deg}°)",
    "sagittal": "Oblique, closest to sagittal ({deg}°)",
}

# --- CT ------------------------------------------------------------------------------------------------------------

# Contrast phase keywords searched (whole words, upper case, "_" read as a space) in Series Description and Protocol
# Name. HEURISTIC: no standard governs series naming; these are common English and Spanish site/vendor names.
# Order matters: the first match wins ("PORTAL VENOUS" must hit portal before venous; native first so that
# "NON CONTRAST" is never read as contrast).
CT_NATIVE = "Non-contrast CT"
CT_PHASE_WORDS = (
    (r"NATIVE?|NATIVA|NON ?-?CONTRAST|NONCON|UNENHANCED|PRE ?-?CONTRAST|PRECONTRAST|SIN CONTRASTE|SIN CONT|"
     r"S/C|SIMPLE|PLAIN", CT_NATIVE),
    (r"CTA|ANGIO\w*|ANGIOTC|ANGIO-?TC", "Contrast-enhanced CT, angiographic phase (CTA)"),
    (r"PORTAL|PORTO ?-?VENOUS|PORTOVENOSA|PV", "Contrast-enhanced CT, portal venous phase"),
    (r"(LATE |EARLY )?ARTERIAL|ARTERIAL|ARTERIELLE?|ART", "Contrast-enhanced CT, arterial phase"),
    (r"NEPHRO\w*|NEFRO\w*", "Contrast-enhanced CT, nephrographic phase"),
    (r"EXCRET\w*|UROGRA\w*|PYELO\w*|PIELO\w*", "Contrast-enhanced CT, excretory phase"),
    (r"DELAYED|DELAY|TARDIA|TARDIO|EQUILIBRIUM|LATE", "Contrast-enhanced CT, delayed phase"),
    (r"VENOUS|VENOSA|VENOSO", "Contrast-enhanced CT, venous phase"),
)
CT_PHASE_UNSTATED = "Contrast-enhanced CT, phase not stated"

# Derived reconstructions: searched in Image Type and the description, only when Image Type value 1 is DERIVED
# (DICOM Image Type value 1; section not fetched). HEURISTIC keyword list.
CT_DERIVED_WORDS = (
    (r"MIN ?-?IP", "CT minimum intensity projection (MinIP)"),
    (r"MIP", "CT maximum intensity projection (MIP)"),
    (r"VRT?|VOLUME RENDER\w*", "CT volume rendering (VRT)"),
    (r"MPR|REFORMAT\w*|MPR\w*", "CT multiplanar reformat (MPR)"),
)
CT_LOCALIZER = "CT localizer (scout)"
# HEURISTIC. "DE" is only read in Image Type values: in descriptions it is the Spanish "of" ("TC DE TORAX").
CT_DUAL_ENERGY_IMAGE_TYPE = r"DE|DUAL|DUAL ?-?ENERGY|SPECTRAL|MONOE\w*|VMI"
CT_DUAL_ENERGY_WORDS = r"DUAL ?-?ENERGY|SPECTRAL|MONOENERGETIC|MONOE\w*|VMI"
CT_DUAL_ENERGY = "Dual-energy (spectral) reconstruction"
CT_KEV = r"(\d{2,3}) ?KEV"
CT_MONO = "Virtual monoenergetic image, {kev} keV"

# Kernel families. Words first (any manufacturer: GE names its algorithms with plain words such as STANDARD, SOFT,
# DETAIL, BONE, BONEPLUS, LUNG, CHEST, EDGE), then the manufacturer's code pattern (full match, upper case).
# HEURISTIC: built from the vendors' public naming conventions, not checked against a fetched vendor document.
# Siemens: letter = body (B, Br, Bf, Bv, I = iterative body, Qr = quantitative) or head (H, Hr, Hc, J = iterative
# head), Bl = lung; the number is sharpness. The 50 cut between smooth and sharp is a heuristic. Sharp body kernels
# serve both bone and lung, so they are "other". Philips letter kernels and Canon/Toshiba FCxx numbers are NOT
# mapped: no source was at hand, so they come out as "not in the tables" rather than guessed.
KERNEL_WORDS = (
    (r"BONE\w*|EDGE|OSSEOUS", "bone"),
    (r"LUNG|CHEST", "lung"),
    (r"BRAIN|HEAD|NEURO", "brain"),
    (r"SOFT|STANDARD|STND|STD|DETAIL|ABDOMEN|BODY", "soft"),
)
CT_KERNELS = {
    "SIEMENS": (
        (r"BL\d{2}[A-Z]?\d?", "lung"),
        (r"(H|HR|HC|HN|J)[0-4]\d[A-Z]?\d?", "brain"),
        (r"(H|HR|J)[5-9]\d[A-Z]?\d?", "bone"),
        (r"(B|BR|BF|BV|I|QR)[0-4]\d[A-Z]?\d?", "soft"),
        (r"(B|BR|BF|I|QR)[5-9]\d[A-Z]?\d?", "other"),
    ),
}
# Manufacturer (0008,0070) text -> CT_KERNELS key.
MANUFACTURERS = ((r"SIEMENS", "SIEMENS"), (r"GE|GE MEDICAL SYSTEMS|GE HEALTHCARE", "GE"),
                 (r"PHILIPS", "PHILIPS"), (r"CANON|TOSHIBA", "CANON"))
KERNEL_IDS = {
    "bone": "Kernel: bone",
    "lung": "Kernel: lung",
    "soft": "Kernel: soft tissue",
    "brain": "Kernel: brain",
    "other": "Kernel: sharp body, bone or lung",
}
KERNEL_UNKNOWN = "Kernel not in the tables ({kernel})"

# --- Contrast (CT, MR, XA) -----------------------------------------------------------------------------------------

CONTRAST_RECORDED = "Contrast agent recorded ({agent})"
CONTRAST_DESCRIPTION = "Contrast suggested by the description"
# HEURISTIC: post-contrast words in descriptions (GD/GAD = gadolinium, +C / C+ = with contrast, KM = Kontrastmittel).
POST_CONTRAST_WORDS = r"POST|POSTGAD|\+C|C\+|GD|GAD\w*|KM|CONTRAST|CONTRASTE|CON CONTRASTE|CE|ENHANCED"

# --- MR ------------------------------------------------------------------------------------------------------------

# MR timing thresholds (ms). Source for the scheme: short TR + short TE = T1-weighted, long TR + short TE = proton
# density, long TR + long TE = T2-weighted, with "the exact reference ranges ... not generally specified"
# (https://mriquestions.com/image-contrast-trte.html). The numbers below are therefore HEURISTIC cut-offs; the
# spec's own example (TR < 800 ms and TE < 30 ms -> T1-like) sets the first two.
TR_SHORT_MAX = 800.0
TE_SHORT_MAX = 30.0
TR_LONG_MIN = 2000.0
TE_LONG_MIN = 80.0
# Inversion recovery: the TI that nulls a tissue is TI = ln(2) * T1 of that tissue
# (https://en.wikipedia.org/wiki/Fluid-attenuated_inversion_recovery). With approximate textbook T1 values (not
# fetched: fat about 250 ms, CSF about 4000 ms at 1.5-3 T) that gives about 170 ms (STIR) and about 2800 ms (FLAIR).
# The cut-offs below sit well clear of both and are HEURISTIC; anything between is an IR-prepared T1 sequence
# (MPRAGE-like, T1-FLAIR).
STIR_TI_MAX = 300.0
FLAIR_TI_MIN = 1500.0
# Gradient echo: a TE of 15 ms or more is read as T2*-weighted, shorter as T1-weighted. HEURISTIC.
GRE_T2STAR_TE_MIN = 15.0
# A diffusion tensor has 6 independent elements, so a tensor (DTI) acquisition needs at least 6 directions; a clinical
# trace acquisition uses 3 orthogonal ones.
DTI_MIN_DIRECTIONS = 6
TRACE_DIRECTIONS = 3

# Keyword ids. Searched as whole words, upper case, in Image Type (where noted), Series Description, Protocol Name and
# Sequence Name. HEURISTIC lists of common vendor sequence and series names.
MR_WORDS = {
    "eadc": r"EADC|EXP|EXPADC",
    "adc": r"ADC",
    "fa": r"FA",  # Image Type only
    "diffusion": r"DWI|DIFFUSION|DTI|DIFF|EP2D DIFF|TRACEW|DW",
    "perfusion": r"PERFUSION|PERF|DSC|DCE|ASL|PCASL|PASL",
    "tof": r"TOF|TIME OF FLIGHT|FL3D TOF|INFLOW",
    "pc": r"PC|PCA|PHASE ?-?CONTRAST|QFLOW|FLOW ?-?QUANT\w*|VENC",  # not bare FLOW: "FLOW COMP" is not PC
    "mra": r"MRA|ANGIO\w*|CE ?-?MRA",
    "swi": r"SWI|SWAN|SWIP|VENBOLD|SUSCEPT\w*",
    "ssfp": r"TRUFI|TRUE ?-?FISP|FIESTA|B-?FFE|BSSFP|SSFP|BALANCED",
    "flair": r"FLAIR|DARK ?-?FLUID",
    "stir": r"STIR|TIRM",
    "t1ir": r"MPRAGE|MP-?RAGE|BRAVO|IR ?-?FSPGR|3D ?-?TFE|MP2RAGE",
    "t2star": r"T2\*|T2STAR|GRE|HEMO|MEDIC|MERGE",
    "t1": r"T1\w*",
    "t2": r"T2\w*",
    "pd": r"PD\w*|DP",
    "fatsat": r"FS|FATSAT|FAT ?-?SAT\w*|SPAIR|SPIR|SPECIAL|DIXON|FAT ?-?SUPP\w*",
}
MR = {
    "t1": "T1-weighted",
    "t1_post": "T1-weighted, post-contrast",
    "t1_gre": "T1-weighted (gradient echo)",
    "t1_gre_post": "T1-weighted (gradient echo), post-contrast",
    "t1_ir": "T1-weighted, inversion recovery prepared",
    "t1_ir_post": "T1-weighted, inversion recovery prepared, post-contrast",
    "t2": "T2-weighted",
    "pd": "Proton density-weighted",
    "flair": "T2 FLAIR",
    "stir": "STIR (fat-suppressing inversion recovery)",
    "t2star": "T2*-weighted (gradient echo)",
    "swi": "Susceptibility-weighted (SWI)",
    "ssfp": "Balanced steady-state free precession (bSSFP)",
    "dwi": "Diffusion-weighted",
    "trace": "Diffusion-weighted (trace)",
    "dti": "Diffusion, multiple directions (DTI)",
    "b0": "Diffusion, b = 0 image",
    "adc": "ADC map",
    "eadc": "Exponential ADC map (eADC)",
    "fa": "Fractional anisotropy map (FA)",
    "perfusion": "Perfusion",
    "tof": "MR angiography, time of flight (TOF)",
    "pc": "MR angiography, phase contrast",
    "ce_mra": "MR angiography, contrast-enhanced",
    "mra": "MR angiography",
    "2d": "2D acquisition",
    "3d": "3D acquisition",
    "fatsat": "Fat suppressed",
}

# --- PET -----------------------------------------------------------------------------------------------------------

# Attenuation correction words in Image Type / description. HEURISTIC (Corrected Image (0028,0051), which carries
# ATTN, is not among the 32 tags). NAC words are tried first.
PET_NAC_WORDS = r"NAC|NO ?-?AC|NON ?-?AC|NOAC|UNCORR\w*|NOT CORRECTED|NO ATTN|NONATTN"
PET_AC_WORDS = r"AC|CTAC|MAC|ATTN|ATTENUATION CORRECTED|CORR|CORRECTED|QCFX"
PET_AC = "PET, attenuation corrected"
PET_NAC = "PET, not attenuation corrected"
PET_AC_UNSTATED = "not determined: attenuation correction not stated"
# Units (0054,1001) defined terms, DICOM PS3.3 C.8.9.1.1.3. Read for attenuation correction as a HEURISTIC:
# quantitative units are normally only produced after attenuation correction; raw counts usually are not.
PET_UNITS_AC = {"BQML", "GML", "CM2ML", "MGMINML", "UMOLMINML", "MLMING", "MLG", "UMOLML", "MLMINML", "MLML"}
PET_UNITS_NAC = {"CNTS", "CPS", "PROPCNTS", "PROPCPS"}
PET_UNITS = {
    "BQML": "Values in Bq/mL (activity concentration)",
    "GML": "Values in g/mL (SUV)",
    "CNTS": "Values in counts",
}
PET_UNITS_OTHER = "Values in {units}"
# Series Type (0054,1000) value 1, DICOM PS3.3 C.8.9.1.1.4.
PET_SERIES_TYPES = {
    "STATIC": "Static acquisition",
    "DYNAMIC": "Dynamic acquisition",
    "GATED": "Gated acquisition",
    "WHOLE BODY": "Whole-body acquisition",
}
PET_MIP = "Maximum intensity projection (MIP)"

# --- NM ------------------------------------------------------------------------------------------------------------

# Image Type (0008,0008) value 3 of NM images, DICOM PS3.3 C.8.4.8.1.1 (Table C.8-8).
NM_KINDS = {
    "STATIC": "NM static",
    "WHOLE BODY": "NM whole body",
    "DYNAMIC": "NM dynamic",
    "GATED": "NM gated",
    "TOMO": "NM tomography projections (SPECT)",
    "GATED TOMO": "NM gated tomography projections (gated SPECT)",
    "RECON TOMO": "NM reconstructed tomography (SPECT)",
    "RECON GATED TOMO": "NM reconstructed gated tomography (gated SPECT)",
}
NM_KIND_UNKNOWN = "NM acquisition type not in the tables ({kind})"
# HEURISTIC: planar NM view words in the description. "POST" followed by VOID / STRESS / ... is time, not a view.
NM_VIEW_WORDS = ((r"ANT|ANTERIOR", "Anterior view"),
                 (r"POSTERIOR|POST(?! ?(VOID|STRESS|REST|INJ\w*|THERAPY|TX|MICT\w*))", "Posterior view"),
                 (r"LAT|LATERAL|LLAT|RLAT", "Lateral view"))
NM_VIEW_UNKNOWN = "not determined: no view in Patient Orientation or the description"

# --- Projection radiography ----------------------------------------------------------------------------------------

# View Position (0018,5101) defined terms, DICOM PS3.3 C.8.1.1 (CR Series Module): AP, PA, LL, RL, RLD, LLD, RLO,
# LLO. LAT, LATERAL, OBL, OBLIQUE are NOT defined terms but appear in practice (HEURISTIC additions).
XR_VIEWS = {
    "AP": "AP",
    "PA": "PA",
    "LL": "Left lateral",
    "RL": "Right lateral",
    "RLD": "Right lateral decubitus",
    "LLD": "Left lateral decubitus",
    "RLO": "Right lateral oblique",
    "LLO": "Left lateral oblique",
    "LAT": "Lateral",
    "LATERAL": "Lateral",
    "OBL": "Oblique",
    "OBLIQUE": "Oblique",
}
VIEW_UNKNOWN = "View Position not in the tables ({code})"
# Patient Orientation (0020,0020): direction of the rows, then of the columns, principal letter first; letters
# A P R L H F (DICOM PS3.3 C.7.6.1.1.1).
ORIENTATION_FRONTAL = "frontal (from Patient Orientation)"
ORIENTATION_LATERAL = "lateral (from Patient Orientation)"
ORIENTATION_AXIAL = "axial (from Patient Orientation)"
LATERALITY = {"L": "Left side", "R": "Right side", "B": "Both sides"}

# --- Mammography ---------------------------------------------------------------------------------------------------

# Views of DICOM PS3.16 CID 4014 "View for Mammography", keyed by their ACR MQCM 1999 abbreviation, which is what
# View Position (0018,5101) holds in practice (the MG IOD itself codes the view in View Code Sequence, PS3.3
# C.8.11.7; reading the abbreviation from View Position is a HEURISTIC).
MG_VIEWS = {
    "CC": "CC",
    "MLO": "MLO",
    "ML": "ML",
    "LM": "LM",
    "LMO": "LMO",
    "FB": "FB (from below)",
    "SIO": "SIO",
    "ISO": "ISO",
    "XCCL": "Exaggerated CC (laterally)",
    "XCCM": "Exaggerated CC (medially)",
}
MG_SIDES = {"L": "Left", "R": "Right"}
# Image Laterality (0020,0062) enumerated values R, L, B (PS3.3 C.8.11.7).
MG_LATERALITY = {"L": "Left breast", "R": "Right breast", "B": "Both breasts"}
MG_SERIES = "Mammogram"
# HEURISTIC: vendor product names (Hologic C-View, GE V-Preview, Siemens Insight 2D) and generic words.
MG_TOMO_WORDS = r"TOMO\w*|DBT"
MG_SYNTHETIC_WORDS = r"SYNTH\w*|C-?VIEW|S-?VIEW|V-?PREVIEW|INSIGHT 2D|2D SYNTH\w*"
MG_TOMO = "Breast tomosynthesis"
MG_SYNTHETIC = "Synthetic 2D mammogram"


def mg_view_id(code, side):
    """Result id of a mammography view, e.g. ("MLO", "L") -> "Left MLO"."""
    name = MG_VIEWS[code]
    if side not in MG_SIDES:
        return name
    head, _, rest = name.partition(" ")
    if not head.isupper():
        name = head.lower() + (" " + rest if rest else "")
    return f"{MG_SIDES[side]} {name}"


# --- XA ------------------------------------------------------------------------------------------------------------

# Positioner Primary Angle (0018,1510): RAO -> LAO, +90 at the patient's left (LAO), -90 at the right (RAO);
# Positioner Secondary Angle (0018,1511): CAU -> CRA, +90 cranial (DICOM PS3.3 C.8.7.5.1.2). Angles round to whole
# degrees; a rounded 0 is "frontal" (primary) or no tilt (secondary).
XA_VIEWS = {
    ("LAO", "cranial"): "LAO {primary}°, cranial {secondary}°",
    ("LAO", "caudal"): "LAO {primary}°, caudal {secondary}°",
    ("LAO", ""): "LAO {primary}°",
    ("RAO", "cranial"): "RAO {primary}°, cranial {secondary}°",
    ("RAO", "caudal"): "RAO {primary}°, caudal {secondary}°",
    ("RAO", ""): "RAO {primary}°",
    ("", "cranial"): "Frontal (0°), cranial {secondary}°",
    ("", "caudal"): "Frontal (0°), caudal {secondary}°",
    ("", ""): "Frontal (0°)",
}
XA_SERIES = "X-ray angiography run"

# --- US ------------------------------------------------------------------------------------------------------------

US_COLOUR = "Ultrasound, colour (Doppler or colour map)"
US_GREY = "Ultrasound, greyscale"
US_NO_VIEW = "not determined: ultrasound views are not in the header"

# --- Region --------------------------------------------------------------------------------------------------------

# Body Part Examined (0018,0015) defined terms, DICOM PS3.16 Annex L (Tables L-1, L-2).
REGIONS = {
    "CHEST": "Chest",
    "ABDOMEN": "Abdomen",
    "PELVIS": "Pelvis",
    "ABDOMENPELVIS": "Abdomen and pelvis",
    "CHESTABDOMEN": "Chest and abdomen",
    "HEAD": "Head",
    "BRAIN": "Brain",
    "SKULL": "Skull",
    "NECK": "Neck",
    "CSPINE": "Cervical spine",
    "TSPINE": "Thoracic spine",
    "LSPINE": "Lumbar spine",
    "SPINE": "Spine",
    "WHOLEBODY": "Whole body",
    "SHOULDER": "Shoulder",
    "ELBOW": "Elbow",
    "WRIST": "Wrist",
    "HAND": "Hand",
    "HIP": "Hip",
    "KNEE": "Knee",
    "ANKLE": "Ankle",
    "FOOT": "Foot",
    "BREAST": "Breast",
    "HEART": "Heart",
    "EXTREMITY": "Extremity",
    "ORBIT": "Orbit",
    "JAW": "Jaw",
    "TMJ": "Temporomandibular joint",
}
REGION_OTHER = "Body part as recorded ({part})"

# --- Modality and not-determined -----------------------------------------------------------------------------------

MODALITY_INFERRED = "Modality inferred from the tags: {modality}"
NO_RULES = "No rules for modality {modality}"

ND_MODALITY = "not determined: Modality missing"
ND_GEOMETRY = "not determined: no Image Orientation"
ND_CONTRAST = "not determined: Contrast/Bolus Agent missing"
ND_KERNEL = "not determined: Convolution Kernel missing"
ND_TR_TE = "not determined: Repetition Time and Echo Time missing"
ND_TR_TE_RANGE = "not determined: TR and TE between the T1, PD and T2 ranges"
ND_UNITS = "not determined: Units missing"
ND_IMAGE_TYPE = "not determined: Image Type missing"
ND_XR_VIEW = "not determined: ViewPosition and Patient Orientation missing"
ND_VIEW = "not determined: View Position missing"
ND_LATERALITY = "not determined: Image Laterality missing"
ND_PRIMARY = "not determined: Positioner Primary Angle missing"
ND_SECONDARY = "not determined: Positioner Secondary Angle missing"
ND_BODY_PART = "not determined: Body Part Examined missing"
ND_LOCALIZER = "not determined: localizer is neither frontal nor lateral"

LOCALIZER_VIEWS = {"coronal": "frontal", "sagittal": "lateral"}

# --- Explanations (spec §5): what it is and what it is typically used for. No findings, no advice. ----------------

_ND = "The tool does not guess when the header does not say."

EXPLAIN = {
    # Planes
    "Axial": "Axial slices are horizontal cuts through the body, viewed as if from the feet. Most CT and MR "
             "series are acquired or shown in this plane.",
    "Coronal": "Coronal slices are vertical cuts from front to back, so the image faces you like a person standing "
               "in front of you.",
    "Sagittal": "Sagittal slices are vertical cuts from left to right, showing the body in side view. They are often "
                "used for the spine and the midline of the brain.",
    "Oblique, closest to axial ({deg}°)": "The slices are tilted away from the standard planes; the nearest one is "
                                          "axial, at the angle shown. Tilted slices are used to follow a structure "
                                          "or come from gantry tilt.",
    "Oblique, closest to coronal ({deg}°)": "The slices are tilted away from the standard planes; the nearest one "
                                            "is coronal, at the angle shown. Tilted slices are used to follow a "
                                            "structure such as a joint or a vessel.",
    "Oblique, closest to sagittal ({deg}°)": "The slices are tilted away from the standard planes; the nearest one "
                                             "is sagittal, at the angle shown. Tilted slices are used to follow a "
                                             "structure such as a joint or a vessel.",
    # CT
    CT_LOCALIZER: "A localizer (scout or topogram) is a quick projection image taken before the CT scan. It is "
                  "used to plan where the slices will be taken.",
    "frontal": "The localizer was taken from the front, like a frontal radiograph.",
    "lateral": "The localizer was taken from the side, like a lateral radiograph.",
    ND_LOCALIZER: "The localizer orientation is neither front-on nor side-on within 10 degrees. " + _ND,
    CT_NATIVE: "A CT acquired without intravenous contrast. It shows tissue density without the effect of contrast and "
               "is often the reference for later contrast phases.",
    "Contrast-enhanced CT, angiographic phase (CTA)": "A CT timed for contrast in the arteries (CT angiography). It "
                                                      "is used to show blood vessels.",
    "Contrast-enhanced CT, arterial phase": "A CT taken shortly after contrast injection, while contrast is mainly "
                                            "in the arteries. It shows structures that take up contrast early.",
    "Contrast-enhanced CT, portal venous phase": "A CT taken about a minute after contrast injection, when contrast "
                                                 "fills the portal vein and liver. It is the standard phase for "
                                                 "abdominal CT.",
    "Contrast-enhanced CT, venous phase": "A CT taken after contrast has reached the veins. It is used to show "
                                          "veins and organs in their enhanced state.",
    "Contrast-enhanced CT, nephrographic phase": "A CT taken when contrast fills the kidney tissue evenly, about "
                                                 "100 seconds after injection. It is used to examine the kidneys.",
    "Contrast-enhanced CT, excretory phase": "A CT taken several minutes after contrast, when the kidneys excrete it "
                                             "into the urinary tract. It is used to outline the urinary tract.",
    "Contrast-enhanced CT, delayed phase": "A CT taken several minutes after contrast injection. It shows how "
                                           "contrast washes in or out of tissues over time.",
    CT_PHASE_UNSTATED: "A contrast agent is recorded in the header, but the description does not name the phase.",
    "CT maximum intensity projection (MIP)": "A MIP shows, along each line of sight, the brightest voxel of a slab "
                                             "of slices. It is often used to show vessels or small nodules.",
    "CT minimum intensity projection (MinIP)": "A MinIP shows, along each line of sight, the darkest voxel of a slab "
                                               "of slices. It is often used to show the airways and lung.",
    "CT volume rendering (VRT)": "A volume rendering is a 3D picture computed from the slices. It is used for "
                                 "overview and planning.",
    "CT multiplanar reformat (MPR)": "A reformat recomputes the slices in another plane from the original volume. "
                                     "It lets the same scan be read in axial, coronal or sagittal views.",
    CT_DUAL_ENERGY: "The image comes from a scan at two X-ray energies (dual-energy or spectral CT). Such scans can "
                    "be turned into images of different energies or materials.",
    CT_MONO: "A virtual monoenergetic image simulates a scan at a single X-ray energy, shown in keV. Low energies "
             "increase contrast; high energies reduce metal and beam-hardening artefacts.",
    "Kernel: bone": "The reconstruction kernel is sharp, made for bone detail. Edges are crisp and noise is higher.",
    "Kernel: lung": "The reconstruction kernel is sharp, made for lung detail. Edges are crisp and noise is higher.",
    "Kernel: soft tissue": "The reconstruction kernel is smooth, made for soft tissue. Noise is low and fine edges "
                           "are softer.",
    "Kernel: brain": "The reconstruction kernel is a smooth head kernel, made for brain tissue contrast.",
    "Kernel: sharp body, bone or lung": "The reconstruction kernel is a sharp body kernel. The name alone does not "
                                        "say whether it was meant for bone or for lung.",
    KERNEL_UNKNOWN: "The reconstruction kernel shown is not in the tool's tables, so its family is not named.",
    # Contrast
    CONTRAST_RECORDED: "The header records a contrast agent for this series, by the name shown.",
    CONTRAST_DESCRIPTION: "The header records no contrast agent, but the series description uses a word for "
                          "contrast. Descriptions are typed by people and can be wrong.",
    # MR
    MR["t1"]: "T1-weighted images show fat bright and fluid dark. They are used to show anatomy.",
    MR["t1_post"]: "T1-weighted images taken after a gadolinium contrast injection. Tissues that take up contrast "
                   "appear brighter than before.",
    MR["t1_gre"]: "T1-weighted images from a fast gradient-echo sequence, often acquired in 3D or in one breath-hold.",
    MR["t1_gre_post"]: "T1-weighted gradient-echo images taken after a gadolinium contrast injection, often in 3D "
                       "or in one breath-hold.",
    MR["t1_ir"]: "T1-weighted images with an inversion pulse that increases T1 contrast (for example MPRAGE). They "
                 "are often 3D and used for detailed anatomy.",
    MR["t1_ir_post"]: "T1-weighted inversion-prepared images (for example MPRAGE) taken after a gadolinium contrast "
                      "injection.",
    MR["t2"]: "T2-weighted images show fluid bright. They are a basic sequence in most MR examinations.",
    MR["pd"]: "Proton density-weighted images show the amount of water and fat in tissue, with little T1 or T2 "
              "contrast. They are common in joint imaging.",
    MR["flair"]: "FLAIR is a T2-weighted image in which the signal of free fluid such as cerebrospinal fluid is "
                 "nulled. It is widely used in brain imaging.",
    MR["stir"]: "STIR is an inversion recovery sequence that nulls the signal of fat. Fluid stays bright, so it is "
                "used where fat would hide it.",
    MR["t2star"]: "T2*-weighted gradient-echo images are sensitive to magnetic disturbances such as iron, blood "
                  "products and calcium.",
    MR["swi"]: "Susceptibility-weighted imaging is a gradient-echo technique that strongly shows magnetic "
               "differences, such as those of veins, blood products and calcium.",
    MR["ssfp"]: "Balanced steady-state free precession is a fast sequence where fluid is bright. It is used for "
                "the heart, fetal imaging and fluid-filled structures.",
    MR["dwi"]: "Diffusion-weighted images show how freely water molecules move in tissue.",
    MR["trace"]: "Trace diffusion-weighted images combine three diffusion directions into one image of how freely "
                 "water moves.",
    MR["dti"]: "Diffusion images acquired in many directions (diffusion tensor imaging). They are used to compute "
               "maps such as fractional anisotropy and to trace white matter tracts.",
    MR["b0"]: "The b = 0 image of a diffusion series has no diffusion weighting and looks like a T2-weighted image. "
              "It is the reference for the diffusion maps.",
    MR["adc"]: "The apparent diffusion coefficient (ADC) map is computed from diffusion images and shows water "
               "mobility as a number per pixel.",
    MR["eadc"]: "The exponential ADC map is computed from diffusion images. It removes the T2 contribution from the "
                "diffusion-weighted image.",
    MR["fa"]: "The fractional anisotropy map is computed from diffusion tensor data and shows how directional water "
              "movement is. It is used to study white matter.",
    MR["perfusion"]: "Perfusion imaging measures blood flow through tissue, with injected contrast (DSC, DCE) or "
                     "with magnetically labelled blood (ASL).",
    MR["tof"]: "Time-of-flight MR angiography shows flowing blood bright without contrast injection. It is "
               "commonly used for the brain arteries.",
    MR["pc"]: "Phase-contrast MR shows flowing blood and can measure its speed and direction without contrast.",
    MR["ce_mra"]: "Contrast-enhanced MR angiography shows vessels filled with injected gadolinium contrast.",
    MR["mra"]: "MR angiography shows blood vessels. The technique is not stated in the header.",
    MR["2d"]: "The images were acquired slice by slice (2D acquisition).",
    MR["3d"]: "The images were acquired as one volume (3D acquisition), which allows thin slices and reformats in "
              "any plane.",
    MR["fatsat"]: "The series description indicates fat suppression, which makes fat dark so that other tissues "
                  "stand out.",
    # PET
    PET_AC: "The PET image is corrected for attenuation, the absorption of radiation by the body. Corrected images "
            "are the ones used for quantitative values such as SUV.",
    PET_NAC: "The PET image is not corrected for attenuation. It is often kept to check for artefacts of the "
             "correction.",
    PET_AC_UNSTATED: "Neither the description, the Image Type nor the Units say whether attenuation correction was "
                     "applied. " + _ND,
    PET_UNITS["BQML"]: "Pixel values are activity concentration in becquerels per millilitre, from which SUV can be "
                       "computed.",
    PET_UNITS["GML"]: "Pixel values are in grams per millilitre, the unit used for standardized uptake values "
                      "(SUV).",
    PET_UNITS["CNTS"]: "Pixel values are detected counts, not calibrated to activity.",
    PET_UNITS_OTHER: "Pixel values are in the unit shown, as recorded in the Units field.",
    PET_SERIES_TYPES["STATIC"]: "A static acquisition records one image of the tracer distribution over the "
                                "acquisition time.",
    PET_SERIES_TYPES["DYNAMIC"]: "A dynamic acquisition records a sequence of time frames to follow how the tracer "
                                 "moves over time.",
    PET_SERIES_TYPES["GATED"]: "A gated acquisition sorts data by heartbeat or breathing phase to reduce motion.",
    PET_SERIES_TYPES["WHOLE BODY"]: "A whole-body acquisition covers a long part of the body in several bed "
                                    "positions joined together.",
    PET_MIP: "A maximum intensity projection shows the brightest value along each line of sight. In PET it gives "
             "a quick overview of the whole tracer distribution.",
    # NM
    NM_KINDS["STATIC"]: "A static nuclear medicine image is a single planar picture of the tracer distribution.",
    NM_KINDS["WHOLE BODY"]: "A whole-body nuclear medicine image is a planar scan of the whole body, typically front "
                            "and back. It is common for bone scans.",
    NM_KINDS["DYNAMIC"]: "A dynamic nuclear medicine study is a sequence of planar images over time to follow "
                         "tracer flow or uptake.",
    NM_KINDS["GATED"]: "A gated nuclear medicine study sorts images by heartbeat phase, as used for heart function.",
    NM_KINDS["TOMO"]: "These are the raw projections of a SPECT acquisition, taken while the camera rotates. They "
                      "are reconstructed into slices.",
    NM_KINDS["GATED TOMO"]: "These are the raw projections of a gated SPECT acquisition, sorted by heartbeat phase.",
    NM_KINDS["RECON TOMO"]: "These are slices reconstructed from a SPECT acquisition, showing the tracer "
                            "distribution in 3D.",
    NM_KINDS["RECON GATED TOMO"]: "These are slices reconstructed from a gated SPECT acquisition, typically of the "
                                  "heart, one volume per heartbeat phase.",
    NM_KIND_UNKNOWN: "The nuclear medicine acquisition type shown is not in the tool's tables.",
    "Anterior view": "A planar nuclear medicine view taken from the front of the patient.",
    "Posterior view": "A planar nuclear medicine view taken from the back of the patient.",
    "Lateral view": "A planar nuclear medicine view taken from the side of the patient.",
    NM_VIEW_UNKNOWN: "Neither Patient Orientation nor the series description names the view. " + _ND,
    # Radiography
    XR_MODALITIES["CR"]: "A projection radiograph: an X-ray image of a body part, flattened onto one plane.",
    XR_MODALITIES["RF"]: "An image from fluoroscopy, live X-ray imaging used to follow movement or guide "
                         "procedures.",
    XR_MODALITIES["PX"]: "A panoramic dental radiograph shows the whole of both jaws and the teeth in one image.",
    XR_MODALITIES["IO"]: "An intra-oral dental radiograph is taken with the detector inside the mouth, showing a "
                         "few teeth in detail.",
    "AP": "Anteroposterior view: the X-rays pass from the front of the body to the back.",
    "PA": "Posteroanterior view: the X-rays pass from the back of the body to the front. It is the standard view "
          "for an upright chest radiograph.",
    "Left lateral": "Lateral view with the patient's left side against the detector.",
    "Right lateral": "Lateral view with the patient's right side against the detector.",
    "Right lateral decubitus": "View taken with the patient lying on the right side and a horizontal X-ray beam.",
    "Left lateral decubitus": "View taken with the patient lying on the left side and a horizontal X-ray beam.",
    "Right lateral oblique": "Oblique view with the patient turned so the right side is nearer the detector.",
    "Left lateral oblique": "Oblique view with the patient turned so the left side is nearer the detector.",
    "Lateral": "Lateral view: a side view of the body part. The side nearer the detector is not stated.",
    "Oblique": "Oblique view: the body part is turned at an angle between frontal and lateral.",
    VIEW_UNKNOWN: "The View Position code shown is not in the tool's tables.",
    ORIENTATION_FRONTAL: "No view is recorded, but the image directions in Patient Orientation run left-right and "
                         "head-feet, as in a frontal (AP or PA) view. Whether it is AP or PA is not known.",
    ORIENTATION_LATERAL: "No view is recorded, but the image directions in Patient Orientation run front-back and "
                         "head-feet, as in a lateral view.",
    ORIENTATION_AXIAL: "No view is recorded, but the image directions in Patient Orientation run left-right and "
                       "front-back, as in an axial view.",
    LATERALITY["L"]: "The header records the left side.",
    LATERALITY["R"]: "The header records the right side.",
    LATERALITY["B"]: "The header records both sides.",
    # Mammography
    MG_SERIES: "A mammogram is a low-dose X-ray image of the breast.",
    MG_TOMO: "Breast tomosynthesis takes several low-dose images over an arc and builds thin slices of the breast. "
             "It reduces the overlap of tissue.",
    MG_SYNTHETIC: "A synthetic 2D mammogram is computed from tomosynthesis data instead of being taken as a "
                  "separate exposure.",
    MG_LATERALITY["L"]: "The image is of the left breast.",
    MG_LATERALITY["R"]: "The image is of the right breast.",
    MG_LATERALITY["B"]: "The image includes both breasts.",
    # XA
    XA_SERIES: "An X-ray angiography run is a series of X-ray images taken while contrast flows through vessels. "
               "The C-arm angles give the viewing direction.",
    # US
    US_COLOUR: "An ultrasound image with colour, usually colour Doppler showing blood flow or a colour map. Colour "
               "alone does not tell which mode was used.",
    US_GREY: "A greyscale ultrasound image, showing tissue echoes.",
    US_NO_VIEW: "Ultrasound probe position and view are not stored in standard header fields, so the tool cannot "
                "name them.",
    # Modality
    MODALITY_INFERRED: "The host did not report the modality, so it was inferred from which tags are present. "
                       "Treat it with caution.",
    NO_RULES: "The tool has no identification rules for this modality.",
    # Not determined
    ND_MODALITY: "The modality is not reported and could not be inferred from the tags. " + _ND,
    ND_GEOMETRY: "The image has no orientation in the header, so the plane cannot be computed. " + _ND,
    ND_CONTRAST: "No contrast agent is recorded and the description names no phase. This does not mean no contrast "
                 "was given. " + _ND,
    ND_KERNEL: "The reconstruction kernel is not recorded. " + _ND,
    ND_TR_TE: "Repetition time and echo time are not recorded and the description names no weighting. " + _ND,
    ND_TR_TE_RANGE: "The repetition and echo times fall between the usual T1, proton density and T2 ranges, and "
                    "the description names no weighting. " + _ND,
    ND_UNITS: "The pixel Units are not recorded and the description does not say whether attenuation correction "
              "was applied. " + _ND,
    ND_IMAGE_TYPE: "The Image Type that names the nuclear medicine acquisition type is not recorded. " + _ND,
    ND_XR_VIEW: "Neither View Position nor Patient Orientation is recorded, so the projection is unknown. " + _ND,
    ND_VIEW: "View Position is not recorded, so the mammographic view is unknown. " + _ND,
    ND_LATERALITY: "Image Laterality is not recorded, so the side is unknown. " + _ND,
    ND_PRIMARY: "The C-arm primary angle is not recorded, so the viewing direction is unknown. " + _ND,
    ND_SECONDARY: "The C-arm secondary angle is not recorded, so the cranial or caudal tilt is unknown. " + _ND,
    ND_BODY_PART: "Body Part Examined is not recorded. " + _ND,
}

_XA_SIDE = {
    "LAO": "rotated toward the patient's left (left anterior oblique)",
    "RAO": "rotated toward the patient's right (right anterior oblique)",
    "": "straight above the patient (frontal)",
}
_XA_TILT = {"cranial": " and tilted toward the head (cranial)", "caudal": " and tilted toward the feet (caudal)",
            "": ""}
for (_side, _tilt), _rid in XA_VIEWS.items():
    EXPLAIN[_rid] = (f"The image detector is {_XA_SIDE[_side]}{_XA_TILT[_tilt]}, by the angles shown. "
                     "Angiography uses these angles to see vessels without overlap.")

_MG_TEXT = {
    "CC": "Cranio-caudal view: the breast is compressed from above and imaged from top to bottom.",
    "MLO": "Medio-lateral oblique view: the breast is imaged at an angle from the middle outward. It shows the most "
           "breast tissue, up into the armpit.",
    "ML": "Medio-lateral view: a straight side view of the breast, taken from the middle outward.",
    "LM": "Latero-medial view: a straight side view of the breast, taken from the outside inward.",
    "LMO": "Latero-medial oblique view: an angled view taken from the outside inward.",
    "FB": "Caudo-cranial view (from below): the breast is imaged from bottom to top.",
    "SIO": "Superolateral to inferomedial oblique view: an angled view from the upper outer side.",
    "ISO": "Inferomedial to superolateral oblique view: an angled view from the lower inner side.",
    "XCCL": "Exaggerated cranio-caudal view, turned to include the outer part of the breast.",
    "XCCM": "Exaggerated cranio-caudal view, turned to include the inner part of the breast.",
}
for _code, _para in _MG_TEXT.items():
    EXPLAIN[mg_view_id(_code, "")] = _para + " Screening uses mainly CC and MLO."
    for _s, _word in MG_SIDES.items():
        EXPLAIN[mg_view_id(_code, _s)] = f"{_para} This image is of the {_word.lower()} breast."

for _name in REGIONS.values():
    EXPLAIN[_name] = f"The body part recorded in the header is: {_name.lower()}."
EXPLAIN[REGION_OTHER] = "The body part is shown as recorded in the header; it is not in the tool's table."


def word_re(pattern):
    """Compile `pattern` (an alternation) to match whole words only."""
    return re.compile(rf"(?<![A-Z0-9])(?:{pattern})(?![A-Z0-9])")


def all_result_ids():
    """Every result id the data tables can produce (literal ids in the rules are covered by the tests)."""
    ids = set(PLANE_IDS.values()) | set(OBLIQUE_IDS.values()) | set(LOCALIZER_VIEWS.values())
    ids |= {rid for _, rid in CT_PHASE_WORDS} | {rid for _, rid in CT_DERIVED_WORDS}
    ids |= set(KERNEL_IDS.values()) | set(MR.values()) | set(PET_UNITS.values()) | set(PET_SERIES_TYPES.values())
    ids |= set(NM_KINDS.values()) | {rid for _, rid in NM_VIEW_WORDS} | set(XR_VIEWS.values())
    ids |= set(XR_MODALITIES.values()) | set(LATERALITY.values()) | set(MG_LATERALITY.values())
    ids |= {mg_view_id(c, s) for c in MG_VIEWS for s in ("", *MG_SIDES)} | set(XA_VIEWS.values())
    ids |= set(REGIONS.values())
    ids |= {CT_LOCALIZER, CT_PHASE_UNSTATED, CT_DUAL_ENERGY, CT_MONO, KERNEL_UNKNOWN, CONTRAST_RECORDED,
            CONTRAST_DESCRIPTION, PET_AC, PET_NAC, PET_AC_UNSTATED, PET_UNITS_OTHER, PET_MIP, NM_KIND_UNKNOWN,
            NM_VIEW_UNKNOWN, VIEW_UNKNOWN, ORIENTATION_FRONTAL, ORIENTATION_LATERAL, ORIENTATION_AXIAL, MG_SERIES,
            MG_TOMO, MG_SYNTHETIC, XA_SERIES, US_COLOUR, US_GREY, US_NO_VIEW, REGION_OTHER, MODALITY_INFERRED,
            NO_RULES, ND_MODALITY, ND_GEOMETRY, ND_CONTRAST, ND_KERNEL, ND_TR_TE, ND_TR_TE_RANGE, ND_UNITS,
            ND_IMAGE_TYPE, ND_XR_VIEW, ND_VIEW, ND_LATERALITY, ND_PRIMARY, ND_SECONDARY, ND_BODY_PART,
            ND_LOCALIZER}
    return ids

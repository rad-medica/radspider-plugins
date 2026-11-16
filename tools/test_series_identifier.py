"""Tests of org.radspider.series-identifier/seriesid_rules.py (pure Python, loaded by path)."""

import importlib.util
import math
import re
import sys
import unittest
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "org.radspider.series-identifier"
_PATH = _DIR / "seriesid_rules.py"
# seriesid_rules imports its sibling seriesid_tables, as it does inside radspider (plugin folder on sys.path).
sys.path.insert(0, str(_DIR))
_SPEC = importlib.util.spec_from_file_location("seriesid_rules", _PATH)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


class RulesCoreTests(unittest.TestCase):
    def test_plane_classification(self):
        self.assertEqual(R.plane((1, 0, 0), (0, 1, 0))[0], "axial")
        self.assertEqual(R.plane((1, 0, 0), (0, 0, -1))[0], "coronal")
        self.assertEqual(R.plane((0, 1, 0), (0, 0, -1))[0], "sagittal")
        self.assertEqual(R.plane((1, 0, 1e-7), (0, 1, 0))[0], "axial")
        name, deg, near = R.plane((1, 0, 0), (0, 0.7071068, -0.7071068))
        self.assertEqual((name, near), ("oblique", "axial"))
        self.assertAlmostEqual(deg, 45.0, places=3)
        self.assertEqual(R.plane(None, None)[0], "unknown")

    def test_plane_threshold_and_degenerate(self):
        def tilted(deg):
            a = math.radians(deg)
            return (1, 0, 0), (0, math.cos(a), math.sin(a))

        self.assertEqual(R.plane(*tilted(9.9))[0], "axial")
        self.assertEqual(R.plane(*tilted(10.0))[0], "axial")
        self.assertEqual(R.plane(*tilted(10.5))[0], "oblique")
        name, deg, near = R.plane((0, 0, 0), (0, 1, 0))
        self.assertEqual((name, near), ("unknown", ""))
        self.assertTrue(math.isnan(deg))
        self.assertEqual(R.plane((1, 0, 0), (1, 0, 0))[0], "unknown")
        self.assertEqual(R.plane((1, 0), (0, 1))[0], "unknown")
        self.assertEqual(R.plane((1, 0, 0), (0, 1, math.nan))[0], "unknown")

    def test_value_helpers(self):
        self.assertEqual(R.text(" mlo "), "MLO")
        self.assertEqual(R.text(12.0), "12")
        self.assertIsNone(R.text(""))
        self.assertIsNone(R.text(None))
        self.assertEqual(R.text(["a", " b "]), "A\\B")
        self.assertIsNone(R.text(["", None]))
        self.assertEqual(R.numbers([0.5, 0.5]), [0.5, 0.5])
        self.assertIsNone(R.number("x"))
        self.assertEqual(R.number(" 2.5 "), 2.5)
        self.assertEqual(R.number([3]), 3.0)
        self.assertIsNone(R.number(None))
        self.assertIsNone(R.number(math.nan))
        self.assertEqual(R.numbers("1\\2.5"), [1.0, 2.5])
        self.assertIsNone(R.numbers([1, "x"]))
        self.assertIsNone(R.numbers([]))

    def test_finding_is_frozen(self):
        f = R.Finding("plane", "axial", "x", ("a",))
        with self.assertRaises(Exception):
            f.item = "series"


AXIAL = ((1, 0, 0), (0, 1, 0))
CORONAL = ((1, 0, 0), (0, 0, -1))
SAGITTAL = ((0, 1, 0), (0, 0, -1))
NONE = (None, None)
_TILT = math.radians(70)

# name -> (tags, series, (row, col), color). Every identify() input of these tests; explain_complete walks all of it.
CASES = {
    "ct_portal": ({"0018,0010": "OMNIPAQUE", "0008,103e": "ABD PORTAL 3mm", "0018,1210": "B30f",
                   "0008,0070": "SIEMENS"}, {"modality": "CT"}, AXIAL, False),
    "ct_localizer": ({"0008,0008": "ORIGINAL\\PRIMARY\\LOCALIZER", "0008,0070": "SIEMENS"}, {"modality": "CT"},
                     SAGITTAL, False),
    "ct_localizer_frontal": ({"0008,0008": "ORIGINAL\\PRIMARY\\LOCALIZER"}, {"modality": "CT"}, CORONAL, False),
    "ct_native": ({"0008,103E": "TORAX SIN CONTRASTE", "0018,1210": "LUNG", "0008,0070": "GE MEDICAL SYSTEMS"},
                  {"modality": "CT"}, AXIAL, False),
    "ct_agent_only": ({"0018,0010": "IOMERON", "0018,1210": "BONE", "0008,0070": "GE MEDICAL SYSTEMS"},
                      {"modality": "CT"}, AXIAL, False),
    "ct_mip": ({"0008,0008": "DERIVED\\SECONDARY\\MIP", "0008,103E": "CTA MIP COR"}, {"modality": "CT"}, CORONAL,
               False),
    "ct_mono": ({"0008,0008": "DERIVED\\PRIMARY\\AXIAL\\DE", "0008,103E": "Mono+ 50 keV",
                 "0018,1210": "Qr40", "0008,0070": "SIEMENS"}, {"modality": "CT"}, AXIAL, False),
    "ct_oblique": ({}, {"modality": "CT"}, ((1, 0, 0), (0, math.cos(_TILT), -math.sin(_TILT))), False),
    "mr_flair": ({"0018,0080": 9000.0, "0018,0081": 120.0, "0018,0082": 2500.0, "0018,0020": "SE\\IR",
                  "0018,0023": "2D"}, {"modality": "MR"}, AXIAL, False),
    "mr_t1_post": ({"0018,0080": 500.0, "0018,0081": 10.0, "0018,0010": "GADOVIST"}, {"modality": "MR"}, AXIAL,
                   False),
    "mr_t2": ({"0018,0080": 4000.0, "0018,0081": 100.0, "0018,0020": "SE"}, {"modality": "MR"}, SAGITTAL, False),
    "mr_pd": ({"0018,0080": 3000.0, "0018,0081": 20.0, "0018,0020": "SE", "0008,103E": "PD FS COR"},
              {"modality": "MR"}, CORONAL, False),
    "mr_stir": ({"0018,0080": 5000.0, "0018,0081": 60.0, "0018,0082": 150.0, "0018,0020": "SE\\IR"},
                {"modality": "MR"}, CORONAL, False),
    "mr_mprage": ({"0018,0080": 2300.0, "0018,0081": 3.0, "0018,0082": 900.0, "0018,0020": "GR\\IR",
                   "0018,0023": "3D", "0018,1314": 9.0}, {"modality": "MR"}, SAGITTAL, False),
    "mr_t2star": ({"0018,0080": 600.0, "0018,0081": 20.0, "0018,0020": "GR", "0018,1314": 20.0},
                  {"modality": "MR"}, AXIAL, False),
    "mr_dwi_series": ({"0008,0008": "ORIGINAL\\PRIMARY\\DIFFUSION\\NONE"},
                      {"modality": "MR", "b_values": [0, 1000], "gradient_directions": 3}, AXIAL, False),
    "mr_dti": ({"0008,0008": "ORIGINAL\\PRIMARY\\DIFFUSION\\NONE", "0018,9087": 1000.0},
               {"modality": "MR", "b_values": [0, 1000], "gradient_directions": 30}, AXIAL, False),
    "mr_b0": ({"0008,0008": "ORIGINAL\\PRIMARY\\DIFFUSION\\NONE", "0018,9087": 0.0},
              {"modality": "MR", "b_values": [0, 1000], "gradient_directions": 3}, AXIAL, False),
    "mr_adc": ({"0008,0008": "DERIVED\\PRIMARY\\DIFFUSION\\ADC"}, {"modality": "MR"}, AXIAL, False),
    "mr_tof": ({"0008,103E": "TOF 3D multi-slab", "0018,0020": "GR", "0018,0080": 22.0, "0018,0081": 3.5},
               {"modality": "MR"}, AXIAL, False),
    "pet_ac": ({"0054,1001": "BQML", "0008,0008": "ORIGINAL\\PRIMARY", "0008,103E": "PET AC",
                "0054,1000": "WHOLE BODY\\IMAGE"}, {"modality": "PT"}, AXIAL, False),
    "pet_counts": ({"0054,1001": "CNTS", "0008,0008": "ORIGINAL\\PRIMARY"}, {"modality": "PT"}, AXIAL, False),
    "pet_nac_keyword": ({"0054,1001": "BQML", "0008,103E": "PET NAC"}, {"modality": "PT"}, AXIAL, False),
    "cxr_pa": ({"0018,5101": "PA", "0018,0015": "CHEST"}, {"modality": "CR"}, NONE, False),
    "xr_patient_orientation_only": ({"0018,5101": None, "0020,0020": "L\\F"}, {"modality": "DX"}, NONE, False),
    "xr_lateral_orientation": ({"0020,0020": "P\\F"}, {"modality": "DX"}, NONE, False),
    "xr_nothing": ({}, {"modality": "DX"}, NONE, False),
    "mg_lmlo": ({"0018,5101": "MLO", "0020,0062": "L"}, {"modality": "MG"}, NONE, False),
    "mg_xccl": ({"0018,5101": "XCCL"}, {"modality": "MG"}, NONE, False),
    "mg_tomo": ({"0018,5101": "CC", "0020,0062": "R", "0008,0008": "ORIGINAL\\PRIMARY\\TOMOSYNTHESIS"},
                {"modality": "MG"}, NONE, False),
    "xa_lao_cranial": ({"0018,1510": 30.0, "0018,1511": 20.0}, {"modality": "XA"}, NONE, False),
    "xa_rao_caudal": ({"0018,1510": -15.0, "0018,1511": -10.0}, {"modality": "XA"}, NONE, False),
    "xa_frontal": ({"0018,1510": 0.2, "0018,1511": 0.0}, {"modality": "XA"}, NONE, False),
    "us_colour": ({"0018,0015": "ABDOMEN"}, {"modality": "US"}, NONE, True),
    "us_grey": ({}, {"modality": "US"}, NONE, False),
    "nm_wholebody": ({"0008,0008": "ORIGINAL\\PRIMARY\\WHOLE BODY\\EMISSION"}, {"modality": "NM"}, NONE, False),
    "nm_spect": ({"0008,0008": "ORIGINAL\\PRIMARY\\RECON TOMO\\EMISSION"}, {"modality": "NM"}, AXIAL, False),
    "other_modality": ({}, {"modality": "SR"}, NONE, False),
    # Fix round 1: negations, Protocol Name, ADC description, T1 FLAIR, MG AT/CV vs XR LAT.
    "mr_no_contrast": ({"0018,0080": 500.0, "0018,0081": 10.0, "0008,103E": "T1 NO CONTRAST"}, {"modality": "MR"},
                       AXIAL, False),
    "mr_without_contrast": ({"0018,0080": 500.0, "0018,0081": 10.0, "0008,103E": "T1 WITHOUT CONTRAST"},
                            {"modality": "MR"}, AXIAL, False),
    "mr_pre_gad": ({"0018,0080": 500.0, "0018,0081": 10.0, "0008,103E": "T1 PRE GAD"}, {"modality": "MR"}, AXIAL,
                   False),
    "mr_sin_gadolinio": ({"0018,0080": 500.0, "0018,0081": 10.0, "0008,103E": "T1 SIN GADOLINIO"},
                         {"modality": "MR"}, AXIAL, False),
    "mr_post_op": ({"0018,0080": 500.0, "0018,0081": 10.0, "0008,103E": "T1 POST OP"}, {"modality": "MR"}, AXIAL,
                   False),
    "mr_post_gad": ({"0018,0080": 500.0, "0018,0081": 10.0, "0008,103E": "AX T1 POST GAD"}, {"modality": "MR"},
                    AXIAL, False),
    "mr_protocol_gad": ({"0018,0080": 500.0, "0018,0081": 10.0, "0008,103E": "AX T1",
                         "0018,1030": "BRAIN W WO GAD"}, {"modality": "MR"}, AXIAL, False),
    "mr_protocol_only": ({"0018,1030": "AX FLAIR"}, {"modality": "MR"}, AXIAL, False),
    "mr_dwi_adc_description": ({"0008,0008": "ORIGINAL\\PRIMARY\\DIFFUSION\\NONE", "0018,9087": 1000.0,
                                "0008,103E": "DWI ADC"},
                               {"modality": "MR", "b_values": [0, 1000], "gradient_directions": 3}, AXIAL, False),
    "mr_adc_description_only": ({"0008,103E": "ADC"}, {"modality": "MR"}, AXIAL, False),
    "mr_exp_word": ({"0018,0080": 4000.0, "0018,0081": 100.0, "0008,103E": "T2 EXP 2"}, {"modality": "MR"}, AXIAL,
                    False),
    "mr_t1_flair": ({"0018,0080": 2000.0, "0018,0081": 10.0, "0008,103E": "AX T1 FLAIR"}, {"modality": "MR"},
                    AXIAL, False),
    "ct_protocol_cta": ({"0008,103E": "ABDOMEN 3.0 B30F", "0018,1030": "CTA AORTA"}, {"modality": "CT"}, AXIAL,
                        False),
    "ct_arterial_protocol_cta": ({"0008,103E": "ARTERIAL", "0018,1030": "CTA LIVER"}, {"modality": "CT"}, AXIAL,
                                 False),
    "ct_protocol_only": ({"0018,1030": "CTA AORTA"}, {"modality": "CT"}, AXIAL, False),
    "ct_no_contrast": ({"0008,103E": "ABD NO CONTRAST"}, {"modality": "CT"}, AXIAL, False),
    "ct_without_contrast": ({"0008,103E": "CHEST WITHOUT CONTRAST"}, {"modality": "CT"}, AXIAL, False),
    "ct_w_o": ({"0008,103E": "HEAD W/O"}, {"modality": "CT"}, AXIAL, False),
    "ct_wo_contrast": ({"0008,103E": "ABD WO CONTRAST"}, {"modality": "CT"}, AXIAL, False),
    "ct_sin_contraste_iv": ({"0008,103E": "TORAX SIN CONTRASTE IV"}, {"modality": "CT"}, AXIAL, False),
    "inferred_lat": ({"0018,5101": "LAT"}, None, NONE, False),
    "mg_lat": ({"0018,5101": "LAT", "0020,0062": "L"}, {"modality": "MG"}, NONE, False),
    "mg_at": ({"0018,5101": "AT", "0020,0062": "R"}, {"modality": "MG"}, NONE, False),
    "mg_cv": ({"0018,5101": "CV"}, {"modality": "MG"}, NONE, False),
    "mg_prefixed": ({"0018,5101": "LCC"}, {"modality": "MG"}, NONE, False),
    "ct_spanish_de": ({"0008,103E": "TC DE TORAX SIN CONTRASTE"}, {"modality": "CT"}, AXIAL, False),
    "nm_post_void": ({"0008,0008": "ORIGINAL\\PRIMARY\\STATIC\\EMISSION", "0008,103E": "PELVIS POST VOID"},
                     {"modality": "NM"}, NONE, False),
    "nm_posterior": ({"0008,0008": "ORIGINAL\\PRIMARY\\STATIC\\EMISSION", "0008,103E": "THYROID POST"},
                     {"modality": "NM"}, NONE, False),
    "mr_flow_comp": ({"0018,0080": 4000.0, "0018,0081": 100.0, "0018,0020": "SE", "0008,103E": "T2 FLOW COMP"},
                     {"modality": "MR"}, AXIAL, False),
    "inferred_mr": ({"0018,0080": 500.0, "0018,0081": 10.0}, None, AXIAL, False),
    "inferred_dx": ({"0018,5101": "AP"}, {"modality": None}, NONE, False),
    "inferred_mg": ({"0018,5101": "cc", "0020,0062": "R"}, {"modality": ""}, NONE, False),
    "inferred_none": ({}, None, NONE, False),
    "odd_mg": ({"0018,5101": b"mlo \x00", "0020,0062": ["l"], "0008,103E": 12.0}, {"modality": "MG"}, NONE, False),
    "odd_ct": ({"0008,0008": ["ORIGINAL", "PRIMARY", "AXIAL"], "0008,103E": 3.0, "0018,1210": ["B30f"],
                "0008,0070": "SIEMENS\x00", "0018,0010": math.nan}, {"modality": "ct"}, AXIAL, False),
    "odd_xa": ({"0018,1510": "30", "0018,1511": [20.0]}, {"modality": "XA"}, NONE, False),
    "odd_xr": ({"0018,5101": math.inf, "0020,0020": True, "0018,0015": {"x": 1}}, {"modality": "DX"}, NONE, False),
    "odd_mr": ({"0018,0080": "4000", "0018,0081": [100.0, 200.0], "0018,0020": b"SE", "0008,0008": 7},
               {"modality": "MR", "b_values": "junk", "gradient_directions": "x"}, AXIAL, False),
}

ALL_MODALITIES = ("CT", "MR", "PT", "NM", "CR", "DX", "RF", "PX", "IO", "MG", "US", "XA", "SR")
_ALL_TAGS = ("0008,0008", "0008,0070", "0008,103E", "0018,1030", "0018,0015", "0018,0050", "0018,0010",
             "0018,5101", "0020,0060", "0020,0062", "0020,0020", "0018,1510", "0018,1511", "0018,1210",
             "0054,1000", "0054,1001", "0018,0020", "0018,0021", "0018,0024", "0018,0023", "0018,0080",
             "0018,0081", "0018,0082", "0018,0083", "0018,0084", "0018,0091", "0018,0095", "0018,1314",
             "0018,1316", "0018,1318", "0018,9087", "0018,9089")
for _m in ALL_MODALITIES:
    CASES[f"missing_{_m}"] = ({}, {"modality": _m}, NONE, False)
    CASES[f"none_{_m}"] = (dict.fromkeys(_ALL_TAGS), {"modality": _m}, NONE, False)


def run(name):
    tags, series, (row, col), color = CASES[name]
    return R.identify(tags, series, row, col, color)


def texts(findings, item):
    return [f.english for f in findings if f.item == item]


class IdentifyTests(unittest.TestCase):
    def assertHas(self, name, item, expected):
        got = texts(run(name), item)
        self.assertIn(expected, got, f"{name}: {item} = {got}")

    def test_tag_list_is_the_manifest_32(self):
        self.assertEqual(len(set(_ALL_TAGS)), 32)
        self.assertEqual(set(R.TAGS), set(_ALL_TAGS))

    def test_ct_portal(self):
        self.assertHas("ct_portal", "series", "Contrast-enhanced CT, portal venous phase")
        self.assertHas("ct_portal", "series", "Kernel: soft tissue")
        self.assertHas("ct_portal", "plane", "Axial")
        self.assertHas("ct_portal", "contrast", "Contrast agent recorded ({agent})".format(agent="OMNIPAQUE"))
        self.assertEqual(R.kernel_family("SIEMENS", "B30f")[0], "soft")

    def test_ct_kernels(self):
        self.assertEqual(R.kernel_family("SIEMENS", "B70f")[0], "other")
        self.assertEqual(R.kernel_family("SIEMENS", "Bl57")[0], "lung")
        self.assertEqual(R.kernel_family("SIEMENS", "H30s")[0], "brain")
        self.assertEqual(R.kernel_family("SIEMENS", "H70h")[0], "bone")
        self.assertEqual(R.kernel_family("GE MEDICAL SYSTEMS", "BONEPLUS")[0], "bone")
        self.assertEqual(R.kernel_family("GE MEDICAL SYSTEMS", "STANDARD")[0], "soft")
        self.assertEqual(R.kernel_family(None, "LUNG")[0], "lung")
        self.assertIsNone(R.kernel_family("ACME", "K9")[0])
        self.assertIsNone(R.kernel_family("SIEMENS", None)[0])
        self.assertHas("ct_native", "series", "Kernel: lung")
        self.assertHas("ct_agent_only", "series", "Kernel: bone")
        self.assertHas("ct_mono", "series", "Kernel: soft tissue")

    def test_ct_localizer(self):
        self.assertHas("ct_localizer", "series", "CT localizer (scout)")
        self.assertHas("ct_localizer", "projection", "Lateral localizer")
        self.assertHas("ct_localizer_frontal", "projection", "Frontal localizer")
        self.assertEqual(texts(run("ct_localizer"), "plane"), [])

    def test_ct_contrast_and_reconstructions(self):
        self.assertHas("ct_native", "series", "Non-contrast CT")
        self.assertHas("ct_agent_only", "series", "Contrast-enhanced CT, phase not stated")
        self.assertHas("ct_mip", "series", "CT maximum intensity projection (MIP)")
        self.assertHas("ct_mip", "series", "Contrast-enhanced CT, angiographic phase (CTA)")
        self.assertHas("ct_mono", "series", "Virtual monoenergetic image, 50 keV")
        self.assertHas("ct_mono", "series", "Dual-energy (spectral) reconstruction")
        self.assertHas("ct_oblique", "plane", "Oblique, closest to coronal (20°)")
        self.assertHas("missing_CT", "series", "not determined: Contrast/Bolus Agent missing")
        self.assertHas("missing_CT", "series", "not determined: Convolution Kernel missing")

    def test_mr(self):
        self.assertHas("mr_flair", "series", "T2 FLAIR")
        self.assertHas("mr_flair", "series", "2D acquisition")
        self.assertHas("mr_t1_post", "series", "T1-weighted, post-contrast")
        self.assertHas("mr_t2", "series", "T2-weighted")
        self.assertHas("mr_t2", "plane", "Sagittal")
        self.assertHas("mr_pd", "series", "Proton density-weighted")
        self.assertHas("mr_pd", "series", "Fat suppressed")
        self.assertHas("mr_stir", "series", "STIR (fat-suppressing inversion recovery)")
        self.assertHas("mr_mprage", "series", "T1-weighted, inversion recovery prepared")
        self.assertHas("mr_mprage", "series", "3D acquisition")
        self.assertHas("mr_t2star", "series", "T2*-weighted (gradient echo)")
        self.assertHas("mr_dwi_series", "series", "Diffusion-weighted (trace)")
        self.assertHas("mr_dti", "series", "Diffusion, multiple directions (DTI)")
        self.assertHas("mr_b0", "series", "Diffusion, b = 0 image")
        self.assertHas("mr_adc", "series", "ADC map")
        self.assertHas("mr_tof", "series", "MR angiography, time of flight (TOF)")
        self.assertHas("missing_MR", "series", "not determined: Repetition Time and Echo Time missing")

    def test_pet(self):
        self.assertHas("pet_ac", "series", "PET, attenuation corrected")
        self.assertHas("pet_ac", "series", "Values in Bq/mL (activity concentration)")
        self.assertHas("pet_ac", "series", "Whole-body acquisition")
        self.assertHas("pet_counts", "series", "PET, not attenuation corrected")
        self.assertHas("pet_nac_keyword", "series", "PET, not attenuation corrected")
        self.assertHas("missing_PT", "series", "not determined: Units missing")

    def test_radiography(self):
        self.assertHas("cxr_pa", "series", "Radiograph")
        self.assertHas("cxr_pa", "projection", "PA")
        self.assertHas("cxr_pa", "region", "Chest")
        self.assertHas("xr_patient_orientation_only", "projection", "frontal (from Patient Orientation)")
        self.assertHas("xr_lateral_orientation", "projection", "lateral (from Patient Orientation)")
        self.assertHas("xr_nothing", "projection", "not determined: ViewPosition and Patient Orientation missing")
        self.assertHas("xr_nothing", "region", "not determined: Body Part Examined missing")

    def test_mammography(self):
        self.assertHas("mg_lmlo", "projection", "Left MLO")
        self.assertHas("mg_lmlo", "laterality", "Left breast")
        self.assertHas("mg_xccl", "projection", "Exaggerated CC (laterally)")
        self.assertHas("mg_xccl", "laterality", "not determined: Image Laterality missing")
        self.assertHas("mg_tomo", "projection", "Right CC")
        self.assertHas("mg_tomo", "series", "Breast tomosynthesis")
        self.assertHas("missing_MG", "projection", "not determined: View Position missing")

    def test_angiography(self):
        self.assertHas("xa_lao_cranial", "projection", "LAO 30°, cranial 20°")
        self.assertHas("xa_rao_caudal", "projection", "RAO 15°, caudal 10°")
        self.assertHas("xa_frontal", "projection", "Frontal (0°)")
        self.assertHas("missing_XA", "projection", "not determined: Positioner Primary Angle missing")

    def test_ultrasound(self):
        self.assertHas("us_colour", "series", "Ultrasound, colour (Doppler or colour map)")
        self.assertHas("us_colour", "projection", "not determined: ultrasound views are not in the header")
        self.assertHas("us_colour", "region", "Abdomen")
        self.assertHas("us_grey", "series", "Ultrasound, greyscale")

    def test_nuclear_medicine(self):
        self.assertHas("nm_wholebody", "series", "NM whole body")
        self.assertHas("nm_spect", "series", "NM reconstructed tomography (SPECT)")
        self.assertHas("nm_spect", "plane", "Axial")
        self.assertHas("missing_NM", "series", "not determined: Image Type missing")

    def test_other_modality(self):
        self.assertHas("other_modality", "series", "No rules for modality SR")

    def test_keyword_false_positives(self):
        self.assertNotIn("Dual-energy (spectral) reconstruction", texts(run("ct_spanish_de"), "series"))
        self.assertHas("ct_spanish_de", "series", "Non-contrast CT")
        self.assertNotIn("Posterior view", texts(run("nm_post_void"), "projection"))
        self.assertHas("nm_posterior", "projection", "Posterior view")
        self.assertHas("mr_flow_comp", "series", "T2-weighted")
        self.assertNotIn("Contrast-enhanced CT, arterial phase", texts(run("ct_portal"), "series"))

    def test_fix_round_1(self):
        for name in ("mr_no_contrast", "mr_without_contrast", "mr_pre_gad", "mr_sin_gadolinio", "mr_post_op",
                     "mr_protocol_gad"):
            self.assertHas(name, "series", "T1-weighted")
            self.assertHas(name, "contrast", "not determined: Contrast/Bolus Agent missing")
        self.assertHas("mr_post_gad", "series", "T1-weighted, post-contrast")
        self.assertHas("mr_post_gad", "contrast", "Contrast suggested by the description")
        self.assertHas("mr_protocol_only", "series", "T2 FLAIR")
        f = next(f for f in run("mr_protocol_only") if f.item == "series")
        self.assertIn("(0018,1030)", f.evidence)
        self.assertHas("mr_dwi_adc_description", "series", "Diffusion-weighted (trace)")
        self.assertHas("mr_adc_description_only", "series", "ADC map")
        self.assertHas("mr_exp_word", "series", "T2-weighted")
        self.assertHas("mr_t1_flair", "series", "T1-weighted, inversion recovery prepared")
        self.assertHas("ct_protocol_cta", "series", "not determined: Contrast/Bolus Agent missing")
        self.assertHas("ct_arterial_protocol_cta", "series", "Contrast-enhanced CT, arterial phase")
        self.assertHas("ct_protocol_only", "series", "Contrast-enhanced CT, angiographic phase (CTA)")
        for name in ("ct_no_contrast", "ct_without_contrast", "ct_w_o", "ct_wo_contrast", "ct_sin_contraste_iv",
                     "ct_spanish_de"):
            self.assertHas(name, "series", "Non-contrast CT")
        self.assertHas("inferred_lat", "series", "Modality inferred from the tags: DX")
        self.assertHas("inferred_lat", "projection", "Lateral")
        self.assertHas("mg_lat", "projection", "Lateral")
        self.assertHas("mg_lat", "laterality", "Left breast")
        self.assertHas("mg_at", "projection", "Right AT (axillary tail)")
        self.assertHas("mg_cv", "projection", "CV (cleavage view)")
        self.assertHas("mg_prefixed", "projection", "Left CC")
        sided = next(f for f in run("mg_lmlo") if f.item == "projection")
        self.assertEqual(sided.explain, ("MLO", "Left breast"))
        region = next(f for f in run("cxr_pa") if f.item == "region")
        self.assertEqual(region.explain, ("Body part examined",))

    def test_tables_are_module_constants(self):
        for name in ("CT_KERNELS", "CT_PHASE_WORDS", "MR_WORDS", "XR_VIEWS", "MG_VIEWS", "NM_KINDS"):
            self.assertTrue(getattr(R, name), name)

    def test_all_tags_missing(self):
        for m in ALL_MODALITIES:
            for name in (f"missing_{m}", f"none_{m}"):
                fs = run(name)
                self.assertTrue(fs, name)
                for f in fs:
                    self.assertNotIn("None", f.english, name)
                if m != "SR":
                    self.assertTrue(any(f.english.startswith("not determined: ") for f in fs), name)
            self.assertEqual(run(f"missing_{m}"), run(f"none_{m}"))
        for name in ("missing_CT", "missing_MR", "missing_PT"):
            self.assertIn("not determined: no Image Orientation", texts(run(name), "plane"))

    def test_odd_value_types(self):
        self.assertEqual(R.text(b"MLO\x00"), "MLO")
        self.assertEqual(R.text("CC\x00 "), "CC")
        self.assertEqual(R.text(b"\xe9"), "\xc9")
        self.assertIsNone(R.text(math.nan))
        self.assertIsNone(R.text(math.inf))
        self.assertIsNone(R.text(True))
        self.assertIsNone(R.text({"a": 1}))
        self.assertIsNone(R.text("\x00\x00"))
        self.assertEqual(R.text(12.0), "12")
        self.assertIsNone(R.numbers(b"12"))
        self.assertIsNone(R.numbers({"a": 1}))
        self.assertIsNone(R.numbers(True))
        self.assertIsNone(R.number(b"12"))
        self.assertHas("odd_mg", "projection", "Left MLO")
        self.assertHas("odd_ct", "series", "Kernel: soft tissue")
        self.assertHas("odd_ct", "series", "not determined: Contrast/Bolus Agent missing")
        self.assertHas("odd_xa", "projection", "LAO 30°, cranial 20°")
        self.assertHas("odd_xr", "projection", "not determined: ViewPosition and Patient Orientation missing")
        self.assertHas("odd_xr", "region", "not determined: Body Part Examined missing")
        self.assertHas("odd_mr", "series", "T2-weighted")

    def test_modality_inferred(self):
        self.assertHas("inferred_mr", "series", "Modality inferred from the tags: MR")
        self.assertHas("inferred_mr", "series", "T1-weighted")
        self.assertHas("inferred_dx", "series", "Modality inferred from the tags: DX")
        self.assertHas("inferred_dx", "projection", "AP")
        self.assertHas("inferred_mg", "series", "Modality inferred from the tags: MG")
        self.assertHas("inferred_mg", "projection", "Right CC")
        self.assertHas("inferred_none", "series", "not determined: Modality missing")
        self.assertNotIn("Modality inferred from the tags: CT", texts(run("ct_portal"), "series"))

    def test_evidence_names_tags(self):
        f = next(f for f in run("mr_flair") if f.english == "T2 FLAIR")
        self.assertIn("2500", f.evidence)
        f = next(f for f in run("cxr_pa") if f.item == "projection")
        self.assertIn("(0018,5101)", f.evidence)

    def test_explain_complete(self):
        placeholder = re.compile(r"\{(\w+)\}")
        for name in CASES:
            for f in run(name):
                self.assertIn(f.item, R.ITEMS, name)
                self.assertIn(f.result, R.all_result_ids(), f"{name}: result {f.result!r}")
                self.assertTrue(f.explain, f"{name}: {f.result!r} has no explanation")
                self.assertEqual(f.explain, R.explain_for(f.result), name)
                for e in f.explain:
                    self.assertIn(e, R.EXPLAIN, f"{name}: explain {e!r}")
                self.assertEqual(set(placeholder.findall(f.result)), {k for k, _ in f.args}, name)
                self.assertNotIn("{", f.english, name)

    def test_tables_explained(self):
        self.assertEqual(set(R.EXPLAIN), R.all_explain_ids())
        ids = R.all_result_ids() | set(R.EXPLAIN)
        folded = {}
        for i in ids:
            self.assertNotIn(i.casefold(), folded, f"{i!r} vs {folded.get(i.casefold())!r} differ only by case")
            folded[i.casefold()] = i
        for key, para in R.EXPLAIN.items():
            self.assertTrue(para and para.strip() == para, key)
            sentences = [s for s in re.split(r"(?<=[.!?])\s+", para) if s]
            self.assertLessEqual(len(sentences), 3, key)
            self.assertTrue(para.endswith("."), key)


if __name__ == "__main__":
    unittest.main()

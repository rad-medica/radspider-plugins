"""Tests of org.radspider.series-identifier/seriesid_rules.py and seriesid_model.py (loaded by path).

The model test runs only when onnxruntime and numpy import and RADSPIDER_SERIES_ID_MODEL names the verified file;
everything else needs neither (no network: urlopen is patched).
"""

import hashlib
import http.client
import importlib.util
import io
import math
import os
import re
import sys
import tempfile
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

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
    # Final review fix wave: vendor-shaped headers (as the scanners write them).
    "ct_agent_none": ({"0008,0008": "ORIGINAL\\PRIMARY\\AXIAL", "0008,0070": "SIEMENS", "0008,103E": "Head 5.0 H31s",
                       "0018,1210": "H31s", "0018,0010": "NONE", "0018,0015": "HEAD", "0018,0050": 5.0},
                      {"modality": "CT"}, AXIAL, False),
    "mr_agent_no": ({"0008,0008": "ORIGINAL\\PRIMARY\\M_SE\\M\\SE", "0008,0070": "Philips Medical Systems",
                     "0008,103E": "T1W_SE SAG", "0018,0020": "SE", "0018,0021": "SK", "0018,0024": "SE",
                     "0018,0023": "2D", "0018,0080": 550.0, "0018,0081": 12.0, "0018,1314": 90.0, "0018,0010": "No"},
                    {"modality": "MR"}, SAGITTAL, False),
    "xa_agent_dash": ({"0008,0070": "Siemens", "0008,103E": "Coro LCA", "0018,1510": -30.0, "0018,1511": 20.0,
                       "0018,0010": "-"}, {"modality": "XA"}, NONE, False),
    "mr_lge_psir_siemens": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\NORM\\DIS2D", "0008,0070": "SIEMENS",
                             "0008,103E": "tfl_LGE_PSIR_SAX", "0018,0020": "GR\\IR", "0018,0021": "SK\\SP\\MP\\OSP",
                             "0018,0024": "*tfl2d1_12", "0018,0023": "2D", "0018,0080": 700.0, "0018,0081": 3.2,
                             "0018,0082": 280.0, "0018,1314": 25.0, "0018,0010": "Gadovist"},
                            {"modality": "MR"}, AXIAL, False),
    "mr_lge_psir_philips": ({"0008,0008": "ORIGINAL\\PRIMARY\\M_IR\\M\\IR", "0008,0070": "Philips Medical Systems",
                             "0008,103E": "LGE_PSIR_SA", "0018,0020": "GR\\IR", "0018,0021": "SK\\MP",
                             "0018,0024": "T1TFE", "0018,0023": "2D", "0018,0080": 6.1, "0018,0081": 3.0,
                             "0018,0082": 300.0, "0018,1314": 25.0, "0018,0010": "DOTAREM"},
                            {"modality": "MR"}, AXIAL, False),
    "mr_lge_no_agent": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\NORM\\DIS2D", "0008,0070": "SIEMENS",
                         "0008,103E": "tfl_LGE_SAX", "0018,0020": "GR\\IR", "0018,0021": "SK\\SP\\MP\\OSP",
                         "0018,0024": "*tfl2d1_12", "0018,0080": 700.0, "0018,0081": 3.2, "0018,0082": 280.0,
                         "0018,1314": 25.0}, {"modality": "MR"}, AXIAL, False),
    # Scanning Sequence missing (removed by an anonymiser or a converter): the words decide.
    "mr_lge_no_sequence": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\NORM\\DIS2D", "0008,0070": "SIEMENS",
                            "0008,103E": "tfl_LGE_PSIR_SAX", "0018,0021": "SK\\SP\\MP\\OSP",
                            "0018,0023": "2D", "0018,0080": 700.0, "0018,0081": 3.2, "0018,0082": 280.0,
                            "0018,1314": 25.0, "0018,0010": "Gadovist"}, {"modality": "MR"}, AXIAL, False),
    "mr_short_ti_no_sequence": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\NORM\\DIS2D", "0008,0070": "SIEMENS",
                                 "0008,103E": "COR T2 FS", "0018,0021": "SK\\SP\\MP\\OSP", "0018,0023": "2D",
                                 "0018,0080": 5000.0, "0018,0081": 60.0, "0018,0082": 160.0, "0018,1314": 150.0},
                                {"modality": "MR"}, CORONAL, False),
    "mr_gre_t1_description": ({"0008,0008": "ORIGINAL\\PRIMARY\\OTHER", "0008,0070": "GE MEDICAL SYSTEMS",
                               "0008,103E": "AX T1 FL2D", "0018,0020": "GR", "0018,0021": "SK", "0018,0024": "fgre",
                               "0018,0023": "2D", "0018,0080": 180.0, "0018,0081": 4.2, "0018,1314": 70.0},
                              {"modality": "MR"}, AXIAL, False),
    "mr_tirm_siemens": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\NORM\\DIS2D", "0008,0070": "SIEMENS",
                         "0008,103E": "t2_tirm_cor", "0018,0020": "SE\\IR", "0018,0021": "SK\\SP\\MP\\OSP",
                         "0018,0024": "*tir2d1_13", "0018,0080": 5000.0, "0018,0081": 60.0, "0018,0082": 150.0,
                         "0018,1314": 150.0}, {"modality": "MR"}, CORONAL, False),
    "mr_stir_agent_stamped": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\NORM\\DIS2D", "0008,0070": "SIEMENS",
                               "0008,103E": "t2_tirm_cor", "0018,0020": "SE\\IR", "0018,0021": "SK\\SP\\MP\\OSP",
                               "0018,0024": "*tir2d1_13", "0018,0080": 5000.0, "0018,0081": 60.0,
                               "0018,0082": 150.0, "0018,1314": 150.0, "0018,0010": "Gadovist"},
                              {"modality": "MR"}, CORONAL, False),
    "mr_cine_siemens": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\RETRO\\DIS2D", "0008,0070": "SIEMENS",
                         "0008,103E": "cine_sax", "0018,0020": "GR", "0018,0021": "SK\\SS",
                         "0018,0024": "*tfi2d1_12", "0018,0023": "2D", "0018,0080": 40.0, "0018,0081": 1.4,
                         "0018,1314": 60.0}, {"modality": "MR"}, AXIAL, False),
    "mr_cine_philips": ({"0008,0008": "ORIGINAL\\PRIMARY\\M_FFE\\M\\FFE", "0008,0070": "Philips Medical Systems",
                         "0008,103E": "sBTFE_SA", "0018,0020": "GR", "0018,0021": "SS", "0018,0023": "2D",
                         "0018,0080": 3.0, "0018,0081": 1.5, "0018,1314": 60.0}, {"modality": "MR"}, AXIAL, False),
    "mr_survey_philips": ({"0008,0008": "ORIGINAL\\PRIMARY\\M_FFE\\M\\FFE", "0008,0070": "Philips Medical Systems",
                           "0008,103E": "Survey", "0018,0020": "GR", "0018,0021": "SS", "0018,0023": "2D",
                           "0018,0080": 4.5, "0018,0081": 2.2, "0018,1314": 50.0}, {"modality": "MR"}, AXIAL, False),
    "mr_vibe_siemens": ({"0008,0008": "ORIGINAL\\PRIMARY\\M\\NORM\\DIS2D", "0008,0070": "SIEMENS",
                         "0008,103E": "t1_vibe_fs_tra", "0018,0020": "GR", "0018,0021": "SK\\SP\\OSP",
                         "0018,0024": "*fl3d1", "0018,0023": "3D", "0018,0080": 4.2, "0018,0081": 1.9,
                         "0018,1314": 9.0}, {"modality": "MR"}, AXIAL, False),
    "mr_lava_ge": ({"0008,0008": "ORIGINAL\\PRIMARY\\OTHER", "0008,0070": "GE MEDICAL SYSTEMS",
                    "0008,103E": "AX LAVA", "0018,0020": "GR", "0018,0021": "SS\\SK", "0018,0024": "efgre3d",
                    "0018,0023": "3D", "0018,0080": 4.0, "0018,0081": 1.8, "0018,1314": 12.0},
                   {"modality": "MR"}, AXIAL, False),
    "mr_adc_ge": ({"0008,0008": "DERIVED\\PRIMARY\\OTHER", "0008,0070": "GE MEDICAL SYSTEMS",
                   "0008,103E": "Apparent Diffusion Coefficient (mm2/s)", "0018,0020": "EP", "0018,0021": "NONE",
                   "0018,0024": "epi2", "0018,0080": 6000.0, "0018,0081": 80.0}, {"modality": "MR"}, AXIAL, False),
    "mr_adc_philips": ({"0008,0008": "DERIVED\\PRIMARY\\DIFFUSION", "0008,0070": "Philips Medical Systems",
                        "0008,103E": "dADC", "0018,0020": "SE", "0018,0021": "SK", "0018,0080": 3000.0,
                        "0018,0081": 80.0, "0018,9087": 0.0}, {"modality": "MR"}, AXIAL, False),
    "mr_dixon_opp": ({"0008,0008": "DERIVED\\PRIMARY\\DIXON\\OPP_PHASE", "0008,0070": "SIEMENS",
                      "0008,103E": "t1_vibe_dixon_tra_opp", "0018,0020": "GR", "0018,0021": "SK\\SP\\OSP",
                      "0018,0024": "*fl3d2", "0018,0023": "3D", "0018,0080": 4.0, "0018,0081": 1.2,
                      "0018,1314": 9.0}, {"modality": "MR"}, AXIAL, False),
    "mr_dixon_fat": ({"0008,0008": "DERIVED\\PRIMARY\\DIXON\\FAT", "0008,0070": "SIEMENS",
                      "0008,103E": "t1_vibe_dixon_tra_F", "0018,0020": "GR", "0018,0021": "SK\\SP\\OSP",
                      "0018,0024": "*fl3d2", "0018,0023": "3D", "0018,0080": 4.0, "0018,0081": 2.4,
                      "0018,1314": 9.0}, {"modality": "MR"}, AXIAL, False),
    "mr_dixon_water": ({"0008,0008": "DERIVED\\PRIMARY\\DIXON\\WATER", "0008,0070": "SIEMENS",
                        "0008,103E": "t1_vibe_dixon_tra_W", "0018,0020": "GR", "0018,0021": "SK\\SP\\OSP",
                        "0018,0024": "*fl3d2", "0018,0023": "3D", "0018,0080": 4.0, "0018,0081": 2.4,
                        "0018,1314": 9.0}, {"modality": "MR"}, AXIAL, False),
    "mr_dixon_water_image_type": ({"0008,0008": "DERIVED\\PRIMARY\\DIXON\\WATER", "0008,0070": "SIEMENS",
                                   "0008,103E": "t1_vibe_dixon_tra", "0018,0020": "GR",
                                   "0018,0021": "SK\\SP\\OSP", "0018,0080": 4.0, "0018,0081": 2.4,
                                   "0018,1314": 9.0}, {"modality": "MR"}, AXIAL, False),
    # Philips Image Type W\W and the Siemens DET_AB token below are not checked against a real header.
    "mr_mdixon_water": ({"0008,0008": "ORIGINAL\\PRIMARY\\W\\W\\DERIVED", "0008,0070": "Philips Medical Systems",
                         "0008,103E": "mDIXON_W", "0018,0020": "GR", "0018,0021": "SK\\SP", "0018,0080": 5.5,
                         "0018,0081": 1.8, "0018,1314": 10.0}, {"modality": "MR"}, AXIAL, False),
    "pet_nac_spanish": ({"0008,0008": "ORIGINAL\\PRIMARY", "0008,0070": "SIEMENS",
                         "0008,103E": "PET SIN CORRECCION", "0054,1001": "BQML", "0054,1000": "WHOLE BODY\\IMAGE"},
                        {"modality": "PT"}, AXIAL, False),
    "pet_no_corregido": ({"0008,0008": "ORIGINAL\\PRIMARY", "0008,0070": "SIEMENS",
                          "0008,103E": "PET NO CORREGIDO", "0054,1001": "BQML", "0054,1000": "WHOLE BODY\\IMAGE"},
                         {"modality": "PT"}, AXIAL, False),
    "pet_corregido": ({"0008,0008": "ORIGINAL\\PRIMARY", "0008,0070": "SIEMENS", "0008,103E": "PET CORREGIDO",
                       "0054,1001": "BQML", "0054,1000": "WHOLE BODY\\IMAGE"}, {"modality": "PT"}, AXIAL, False),
    "pet_wb_bqml": ({"0008,0008": "ORIGINAL\\PRIMARY", "0008,0070": "SIEMENS", "0008,103E": "PET WB",
                     "0054,1001": "BQML", "0054,1000": "WHOLE BODY\\IMAGE"}, {"modality": "PT"}, AXIAL, False),
    "ct_cardiac_la_pv": ({"0008,0008": "ORIGINAL\\PRIMARY\\AXIAL", "0008,0070": "SIEMENS",
                          "0008,103E": "LA/PV 0.75 Bv36", "0018,1210": "Bv36", "0018,0010": "Omnipaque",
                          "0018,0015": "HEART"}, {"modality": "CT"}, AXIAL, False),
    "ct_dual_source": ({"0008,0008": "ORIGINAL\\PRIMARY\\AXIAL\\CT_SOM7 SPI DUAL", "0008,0070": "SIEMENS",
                        "0008,103E": "Thorax 1.0 Br40", "0018,1210": "Br40f", "0018,0015": "CHEST"},
                       {"modality": "CT"}, AXIAL, False),
    "ct_dual_energy_det": ({"0008,0008": "ORIGINAL\\PRIMARY\\AXIAL\\CT_SOM5 SPI\\DET_AB", "0008,0070": "SIEMENS",
                            "0008,103E": "Abdomen 1.5 Qr40", "0018,1210": "Qr40", "0018,0015": "ABDOMEN"},
                           {"modality": "CT"}, AXIAL, False),
    "nm_wb_ant_post": ({"0008,0008": "ORIGINAL\\PRIMARY\\WHOLE BODY\\EMISSION", "0008,0070": "GE MEDICAL SYSTEMS",
                        "0008,103E": "WB ANT/POST"}, {"modality": "NM"}, NONE, False),
    "nm_3hr_post": ({"0008,0008": "ORIGINAL\\PRIMARY\\STATIC\\EMISSION", "0008,0070": "SIEMENS",
                     "0008,103E": "THYROID 3HR POST"}, {"modality": "NM"}, NONE, False),
    "nm_24h_post_ant": ({"0008,0008": "ORIGINAL\\PRIMARY\\STATIC\\EMISSION", "0008,0070": "SIEMENS",
                         "0008,103E": "WB 24 H POST ANT"}, {"modality": "NM"}, NONE, False),
    "nm_24hr_posterior": ({"0008,0008": "ORIGINAL\\PRIMARY\\STATIC\\EMISSION", "0008,0070": "SIEMENS",
                           "0008,103E": "WB 24HR POSTERIOR"}, {"modality": "NM"}, NONE, False),
    "mg_generated_2d": ({"0008,0008": "DERIVED\\PRIMARY\\TOMO_2D\\NONE", "0008,0070": "HOLOGIC, Inc.",
                         "0008,103E": "L MLO", "0018,5101": "MLO", "0020,0062": "L"}, {"modality": "MG"}, NONE, False),
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

    def test_final_review_fixes(self):
        # 1. A "no agent" value is no agent.
        self.assertHas("ct_agent_none", "series", "not determined: Contrast/Bolus Agent missing")
        self.assertEqual(texts(run("ct_agent_none"), "contrast"), [])
        self.assertHas("mr_agent_no", "series", "T1-weighted")
        self.assertHas("mr_agent_no", "contrast", "not determined: Contrast/Bolus Agent missing")
        f = next(f for f in run("mr_agent_no") if f.item == "contrast")
        self.assertIn("= NO (a no-agent value, read as missing)", f.evidence)
        self.assertEqual(texts(run("xa_agent_dash"), "contrast"), [])
        # 2. Short TI: STIR only on a spin-echo IR without an agent.
        for name in ("mr_lge_psir_siemens", "mr_lge_psir_philips"):
            self.assertHas(name, "series", "T1-weighted, inversion recovery prepared, post-contrast")
        self.assertHas("mr_lge_no_agent", "series", "T1-weighted, inversion recovery prepared")
        self.assertHas("mr_tirm_siemens", "series", "STIR (fat-suppressing inversion recovery)")
        self.assertHas("mr_stir_agent_stamped", "series", "STIR (fat-suppressing inversion recovery)")
        self.assertHas("mr_stir_agent_stamped", "contrast", "Contrast agent recorded (GADOVIST)")
        self.assertHas("mr_lge_no_sequence", "series", "T1-weighted, inversion recovery prepared, post-contrast")
        self.assertHas("mr_short_ti_no_sequence", "series", "STIR (fat-suppressing inversion recovery)")
        # 3. A T1 word in the description keeps an unspoiled-looking short-TE gradient echo T1, and says so.
        f = next(f for f in run("mr_gre_t1_description") if f.item == "series")
        self.assertEqual(f.english, "T1-weighted (gradient echo)")
        self.assertIn("no spoiling in the tags; T1 word in Series Description (0008,103E) = AX T1 FL2D", f.evidence)
        # 3. bSSFP by name; T1 gradient echo only when spoiled; else not determined.
        for name in ("mr_cine_siemens", "mr_cine_philips"):
            self.assertHas(name, "series", "Balanced steady-state free precession (bSSFP)")
        self.assertHas("mr_survey_philips", "series", "Gradient echo, weighting not determined")
        self.assertEqual(R.mr_kind(run("mr_survey_philips")), "")
        self.assertHas("mr_vibe_siemens", "series", "T1-weighted (gradient echo)")
        self.assertHas("mr_vibe_siemens", "series", "Fat suppressed")
        self.assertHas("mr_lava_ge", "series", "T1-weighted (gradient echo)")
        f = next(f for f in run("mr_vibe_siemens") if f.english == "T1-weighted (gradient echo)")
        self.assertIn("(0018,0021) = SK\\SP\\OSP", f.evidence)
        # 4. ADC maps named by the description.
        self.assertHas("mr_adc_ge", "series", "ADC map")
        self.assertHas("mr_adc_philips", "series", "ADC map")
        self.assertHas("mr_dwi_adc_description", "series", "Diffusion-weighted (trace)")
        # 6. BQML says nothing about attenuation correction; Spanish words do.
        self.assertHas("pet_nac_spanish", "series", "PET, not attenuation corrected")
        self.assertHas("pet_no_corregido", "series", "PET, not attenuation corrected")
        self.assertHas("pet_corregido", "series", "PET, attenuation corrected")
        self.assertHas("pet_wb_bqml", "series", "not determined: attenuation correction not stated")
        self.assertHas("pet_wb_bqml", "series", "Values in Bq/mL (activity concentration)")
        # 7. "PV" is not portal venous.
        self.assertHas("ct_cardiac_la_pv", "series", "Contrast-enhanced CT, phase not stated")
        # 8. Only the Dixon water image is fat suppressed.
        for name in ("mr_dixon_opp", "mr_dixon_fat"):
            self.assertHas(name, "series", "T1-weighted (gradient echo)")
            self.assertNotIn("Fat suppressed", texts(run(name), "series"), name)
        for name in ("mr_dixon_water", "mr_dixon_water_image_type", "mr_mdixon_water"):
            self.assertHas(name, "series", "Fat suppressed")
        f = next(f for f in run("mr_dixon_water_image_type") if f.english == "Fat suppressed")
        self.assertIn("(0008,0008)", f.evidence)
        water = R.T.word_re(R.T.MR_DIXON_WATER_WORDS)
        for desc in ("DIXON W/O", "DIXON W CONTRAST", "DIXON W GAD", "DIXON W/WO"):
            self.assertIsNone(water.search(desc), desc)
        self.assertIsNotNone(water.search("MDIXON W"))
        # 9. NM: both views, and time after injection.
        self.assertHas("nm_wb_ant_post", "projection",
                       "not determined: the description names both anterior and posterior views")
        self.assertHas("nm_3hr_post", "projection", "not determined: no view in Patient Orientation or the description")
        self.assertHas("nm_24h_post_ant", "projection", "Anterior view")
        self.assertHas("nm_24hr_posterior", "projection", "Posterior view")
        # 10. Dual source is not dual energy.
        self.assertNotIn("Dual-energy (spectral) reconstruction", texts(run("ct_dual_source"), "series"))
        self.assertHas("ct_dual_energy_det", "series", "Dual-energy (spectral) reconstruction")
        # 11. Hologic generated 2D.
        self.assertHas("mg_generated_2d", "series", "Synthetic 2D mammogram")
        self.assertHas("mg_generated_2d", "projection", "Left MLO")

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


# --- dcm-classifier features and model --------------------------------------------------------------------------

_MODEL_SPEC = importlib.util.spec_from_file_location("seriesid_model", _DIR / "seriesid_model.py")
M = importlib.util.module_from_spec(_MODEL_SPEC)
_MODEL_SPEC.loader.exec_module(M)

T1 = {
    "0018,0081": 10.0, "0018,0080": 500.0, "0018,1314": 90.0, "0018,0095": 200.0, "0018,0050": 5.0,
    "0018,0020": "SE", "0018,0021": "SP", "0008,0008": "ORIGINAL\\PRIMARY\\M\\ND", "0008,0070": "SIEMENS",
}
T1_VECTOR = [
    0, 10.0, -12345, 90.0, 0, 0, 0, 0, 0, 0, 1, 0, -12345, -12345, 1, -12345, 200.0, 500.0, -12345,
    0, 0, 1, 0, 1, -12345, 0, 0, 0,
]


def feats(tags, geometry=True, spacing=True, **extra):
    vec, why = R.features({**tags, **extra}, geometry, spacing)
    return (dict(zip(R.FEATURES, vec)) if vec is not None else None), why


class FeatureTests(unittest.TestCase):
    def test_feature_order(self):
        self.assertEqual(len(R.FEATURES), 28)
        self.assertEqual(R.FEATURES, (
            "Diffusionb-valueBool", "EchoTime", "EchoTrainLength", "FlipAngle", "HasDiffusionGradientOrientation",
            "ImageType_ADC", "ImageType_DERIVED", "ImageType_DIFFUSION", "ImageType_EADC", "ImageType_FA",
            "ImageType_ORIGINAL", "ImageType_TRACEW", "ImagingFrequency", "InversionTime", "Manufacturer_siemens",
            "NumberOfAverages", "PixelBandwidth", "RepetitionTime", "SAR", "ScanningSequence_GR",
            "ScanningSequence_IR", "ScanningSequence_SE", "SequenceVariant_MP", "SequenceVariant_SP", "dBdt",
            "has_b0", "has_pos_b0", "likely_diffusion",
        ))

    def test_features_t1(self):
        vec, why = R.features(T1, True, True)
        self.assertIsNone(why)
        self.assertEqual(vec, T1_VECTOR)
        f, _ = feats(T1)
        for name, want in (("ImageType_ORIGINAL", 1), ("Manufacturer_siemens", 1), ("ScanningSequence_SE", 1),
                           ("SequenceVariant_SP", 1), ("InversionTime", -12345), ("has_b0", 0),
                           ("likely_diffusion", 0)):
            self.assertEqual(f[name], want, name)

    def test_missing_scanning_sequence_quirk(self):
        f, _ = feats(T1, **{"0018,0020": None})
        self.assertEqual((f["ScanningSequence_SE"], f["ScanningSequence_GR"], f["ScanningSequence_IR"]), (1, 0, 0))
        # Present but empty is not "missing" for the reference: no default, no SE.
        f, _ = feats(T1, **{"0018,0020": ""})
        self.assertEqual(f["ScanningSequence_SE"], 0)
        f, _ = feats(T1, **{"0018,0020": "GR\\IR"})
        self.assertEqual((f["ScanningSequence_SE"], f["ScanningSequence_GR"], f["ScanningSequence_IR"]), (0, 1, 1))

    def test_bvalue_rules(self):
        f, _ = feats(T1, **{"0018,9087": 1004.0})
        self.assertEqual((f["Diffusionb-valueBool"], f["has_pos_b0"], f["has_b0"], f["likely_diffusion"]),
                         (1, 1, 0, 1))
        self.assertEqual(R.bvalue({"0018,9087": 1004.0}), 1000)
        self.assertEqual(R.bvalue({"0018,9087": 1005.0}), 1000)  # round half to even: round(100.5) == 100
        # > 5000 is tested before rounding: 5004 is missing although it would round to 5000.
        self.assertEqual(R.bvalue({"0018,9087": 5004.0}), -12345)
        self.assertEqual(R.bvalue({"0018,9087": 5000.0}), 5000)
        f, _ = feats(T1, **{"0018,9087": 0.0})
        self.assertEqual((f["Diffusionb-valueBool"], f["has_b0"], f["has_pos_b0"], f["likely_diffusion"]),
                         (1, 1, 0, 0))
        f, _ = feats(T1, **{"0018,9087": 6000.0})
        self.assertEqual((f["Diffusionb-valueBool"], f["has_b0"], f["has_pos_b0"]), (0, 0, 0))
        self.assertEqual(R.bvalue({"0018,9087": [0.0, 1000.0]}), -12345)
        f, _ = feats(T1, **{"0018,9089": [0, 0.6, 0.8]})
        self.assertEqual((f["HasDiffusionGradientOrientation"], f["likely_diffusion"]), (1, 1))
        f, _ = feats(T1, **{"0018,9089": [0, 0.6, 0.9]})
        self.assertEqual(f["HasDiffusionGradientOrientation"], 0)
        f, _ = feats(T1, **{"0018,9089": [0.6, 0.8]})
        self.assertEqual(f["HasDiffusionGradientOrientation"], 0)

    def test_adc_eadc(self):
        f, _ = feats(T1, **{"0008,0008": "DERIVED\\PRIMARY\\EADC"})
        self.assertEqual((f["ImageType_EADC"], f["ImageType_ADC"], f["ImageType_DERIVED"]), (1, 0, 1))
        f, _ = feats(T1, **{"0008,0008": "DERIVED\\PRIMARY\\ADC"})
        self.assertEqual((f["ImageType_ADC"], f["ImageType_EADC"], f["likely_diffusion"]), (1, 0, 1))

    def test_substring_quirks(self):
        # "fa" is a substring test: FAT sets ImageType_FA and with it likely_diffusion.
        f, _ = feats(T1, **{"0008,0008": "ORIGINAL\\PRIMARY\\FAT"})
        self.assertEqual((f["ImageType_FA"], f["likely_diffusion"]), (1, 1))
        f, _ = feats(T1, **{"0008,0008": None, "0008,0070": None, "0018,0021": None})
        self.assertEqual((f["ImageType_ORIGINAL"], f["Manufacturer_siemens"], f["SequenceVariant_SP"]), (0, 0, 0))
        f, _ = feats(T1, **{"0008,0070": "Siemens Healthineers", "0018,0021": "SK\\MP\\OSP"})
        self.assertEqual((f["Manufacturer_siemens"], f["SequenceVariant_MP"], f["SequenceVariant_SP"]), (1, 1, 1))

    def test_numeric_fields(self):
        f, why = feats(T1, **{"0018,0081": None, "0018,0080": None})
        self.assertIsNone(why)  # the reference keeps going without TE/TR (ADC images)
        self.assertEqual((f["EchoTime"], f["RepetitionTime"]), (-12345, -12345))
        f, _ = feats(T1, **{"0018,1316": [1.0, 2.0], "0018,0082": [2500.0], "0018,0084": "63.6"})
        self.assertEqual((f["SAR"], f["InversionTime"], f["ImagingFrequency"]), (-12345, 2500.0, 63.6))

    def test_required_missing(self):
        self.assertEqual(R.features({**T1, "0018,0095": None}, True, True), (None, "PixelBandwidth missing"))
        self.assertEqual(R.features(T1, False, True), (None, "Image Orientation missing"))
        self.assertEqual(R.features(T1, True, False), (None, "Pixel Spacing missing"))
        self.assertEqual(R.features({**T1, "0018,1314": None}, True, True), (None, "FlipAngle missing"))
        self.assertEqual(R.features({**T1, "0018,0050": None}, True, True), (None, "SliceThickness missing"))
        self.assertEqual(R.features({**T1, "0018,0095": [200.0, 300.0]}, True, True)[1],
                         "PixelBandwidth not a number")
        self.assertEqual(R.features({**T1, "0018,0081": "x"}, True, True)[1], "EchoTime not a number")
        # Reference order (dicom_config.py required_DICOM_fields): orientation is reported first.
        self.assertEqual(R.features({}, False, False), (None, "Image Orientation missing"))

    def test_series_update(self):
        self.assertEqual(R.series_class("t2w", {"b_values": [0, 1000], "gradient_directions": 6}), "dwig")
        self.assertEqual(R.series_class("t2w", {"b_values": [0, 1000], "gradient_directions": 1}), "tracew")
        self.assertEqual(R.series_class("b0", {"b_values": [0, 1000], "gradient_directions": None}), "tracew")
        self.assertEqual(R.series_class("adc", {"b_values": [0, 1000], "gradient_directions": 6}), "adc")
        self.assertEqual(R.series_class("LOW_PROBABILITY_t2w", {"b_values": [1000]}), "tracew")
        self.assertEqual(R.series_class("t2w", {"b_values": [0], "gradient_directions": 6}), "t2w")
        self.assertEqual(R.series_class("t1w", None), "t1w")
        # The reference tests the volume b-value as get_bvalue returns it: rounded to 10, MISSING above 5000.
        self.assertEqual(R.series_class("t2w", {"b_values": [0, 3], "gradient_directions": 6}), "t2w")
        self.assertEqual(R.series_class("t2w", {"b_values": [0, 6000], "gradient_directions": 6}), "t2w")
        self.assertEqual(R.series_class("t2w", {"b_values": [0, 5], "gradient_directions": 6}), "t2w")  # 0.5 -> 0
        self.assertEqual(R.series_class("t2w", {"b_values": [0, 6], "gradient_directions": 6}), "dwig")


class FakeResponse(io.BytesIO):
    headers = {"Content-Length": "16"}


class CountingResponse(FakeResponse):
    """Remembers how many body bytes were read (the response is closed when the download stops)."""

    def __init__(self, body, headers):
        super().__init__(body)
        self.headers, self.consumed = headers, 0

    def read(self, n=-1):
        chunk = super().read(n)
        self.consumed += len(chunk)
        return chunk


class TruncatedResponse(FakeResponse):
    def read(self, n=-1):
        raise http.client.IncompleteRead(b"partial", 100)


class ModelTests(unittest.TestCase):
    def setUp(self):
        M.reset()

    def tearDown(self):
        M.reset()

    def test_truncated_download_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=TruncatedResponse(b"")):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            with self.assertRaises(M.Unavailable) as cm:
                M.model_path(None)
            self.assertIn("RADSPIDER_SERIES_ID_MODEL", str(cm.exception))
            self.assertEqual(os.listdir(d), [])

    def test_interrupt_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(FakeResponse, "read", side_effect=KeyboardInterrupt), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=FakeResponse(b"x")):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            with self.assertRaises(KeyboardInterrupt):
                M.model_path(None)
            self.assertEqual(os.listdir(d), [])

    def test_failure_cached(self):
        # Fake numpy/onnxruntime so this runs on a python without them: the failure comes from the download.
        fakes = {"numpy": types.ModuleType("numpy"), "onnxruntime": types.ModuleType("onnxruntime")}
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.dict(sys.modules, fakes), \
                mock.patch.object(M.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")) as op:
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            with self.assertRaises(M.Unavailable) as first:
                M.predict(T1_VECTOR)
            with self.assertRaises(M.Unavailable) as second:
                M.predict(T1_VECTOR)
            self.assertEqual(op.call_count, 1)
            self.assertIs(second.exception, first.exception)
            M.reset()
            with self.assertRaises(M.Unavailable):
                M.predict(T1_VECTOR)
            self.assertEqual(op.call_count, 2)

    def test_classes(self):
        self.assertEqual(M.CLASSES, ("t1w", "gret2star", "t2w", "flair", "b0", "tracew", "adc", "fa", "eadc", "dwig"))
        self.assertEqual(M.LOW_PROBABILITY, 0.4)
        self.assertTrue(issubclass(M.Unavailable, ValueError))

    def test_too_large_announced_aborts(self):
        big = CountingResponse(b"x" * 64, {"Content-Length": str(M.MAX_BYTES + 1)})
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=big):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            with self.assertRaises(M.Unavailable) as cm:
                M.model_path(None)
            self.assertIn("more than", str(cm.exception))
            self.assertEqual(big.consumed, 0)  # stopped before reading the body
            self.assertEqual(os.listdir(d), [])

    def test_too_large_unannounced_aborts(self):
        big = CountingResponse(b"x" * (M.MAX_BYTES + 4 * (1 << 16)), {})
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=big):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            with self.assertRaises(M.Unavailable) as cm:
                M.model_path(None)
            self.assertIn("exceeds", str(cm.exception))
            self.assertLessEqual(big.consumed, M.MAX_BYTES + (1 << 16))  # stopped at the cap, not at the end
            self.assertEqual(os.listdir(d), [])

    def test_download_uses_its_own_temporary_file(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=FakeResponse(b"not the model..")):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            other = os.path.join(d, M.FILE + ".part")  # a concurrent run's file is not touched
            with open(other, "wb") as fh:
                fh.write(b"other run")
            seen = []
            with self.assertRaises(M.Unavailable):
                M.model_path(lambda _: seen.append(sorted(os.listdir(d))))
            (during,) = {tuple(x) for x in seen}
            mine = [n for n in during if n != M.FILE + ".part"]
            self.assertEqual(len(mine), 1)
            self.assertTrue(mine[0].startswith(M.FILE + ".") and mine[0].endswith(".part"), mine)
            self.assertEqual(os.listdir(d), [M.FILE + ".part"])

    def test_download_success_stores_only_the_model(self):
        body = b"a verified body"
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M, "SHA256", hashlib.sha256(body).hexdigest()), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=FakeResponse(body)):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            path = M.model_path(None)
            self.assertEqual(path, os.path.join(d, M.FILE))
            self.assertEqual(os.listdir(d), [M.FILE])
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), body)

    def test_replace_failure_uses_a_verified_file_stored_meanwhile(self):
        body = b"a verified body"
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M, "SHA256", hashlib.sha256(body).hexdigest()), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=FakeResponse(body)):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            target = os.path.join(d, M.FILE)

            def replace(src, dst):  # another run stored the same file first; ours cannot replace it
                with open(target, "wb") as fh:
                    fh.write(body)
                raise PermissionError("in use")

            with mock.patch.object(M.os, "replace", side_effect=replace):
                self.assertEqual(M.model_path(None), target)
            self.assertEqual(os.listdir(d), [M.FILE])
            with mock.patch.object(M.os, "replace", side_effect=PermissionError("in use")):
                os.remove(target)
                with self.assertRaises(M.Unavailable):
                    M.model_path(None)
            self.assertEqual(os.listdir(d), [])

    def test_hash_mismatch_deletes(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M.urllib.request, "urlopen", return_value=FakeResponse(b"not the model..")) as op:
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            stale = os.path.join(d, "ova_rf_classifier.onnx")
            with open(stale, "wb") as fh:
                fh.write(b"0123456789")
            seen = []
            with self.assertRaises(M.Unavailable) as cm:
                M.model_path(seen.append)
            self.assertEqual(op.call_args.kwargs.get("timeout"), 60)
            self.assertIn(M.SHA256, str(cm.exception))
            self.assertIn(hashlib.sha256(b"not the model..").hexdigest(), str(cm.exception))
            self.assertIn("RADSPIDER_SERIES_ID_MODEL", str(cm.exception))
            self.assertEqual(os.listdir(d), [])
            self.assertTrue(seen)

    def test_offline(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_DIR": d}), \
                mock.patch.object(M.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")):
            os.environ.pop("RADSPIDER_SERIES_ID_MODEL", None)
            with self.assertRaises(M.Unavailable) as cm:
                M.model_path(None)
            self.assertIn("RADSPIDER_SERIES_ID_MODEL", str(cm.exception))
            self.assertEqual(os.listdir(d), [])

    def test_env_file_checked_not_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "model.onnx")
            with open(bad, "wb") as fh:
                fh.write(b"0123456789")
            with mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_MODEL": bad}):
                with self.assertRaises(M.Unavailable):
                    M.model_path(None)
            self.assertTrue(os.path.isfile(bad))
            with mock.patch.dict(os.environ, {"RADSPIDER_SERIES_ID_MODEL": os.path.join(d, "absent.onnx")}):
                with self.assertRaises(M.Unavailable):
                    M.model_path(None)

    @unittest.skipUnless(importlib.util.find_spec("onnxruntime") and importlib.util.find_spec("numpy")
                         and os.path.isfile(os.environ.get("RADSPIDER_SERIES_ID_MODEL", "")),
                         "needs onnxruntime, numpy and RADSPIDER_SERIES_ID_MODEL pointing to the model")
    def test_predict(self):
        pairs = M.predict(T1_VECTOR)
        self.assertEqual(len(pairs), 10)
        self.assertEqual({c for c, _ in pairs}, set(M.CLASSES))
        self.assertAlmostEqual(sum(p for _, p in pairs), 1.0, delta=1e-5)
        self.assertEqual([p for _, p in pairs], sorted((p for _, p in pairs), reverse=True))
        self.assertEqual(pairs[0][0], "t1w")
        self.assertAlmostEqual(pairs[0][1], 0.9129343, places=6)  # as before the session options
        options = M.load().get_session_options()
        self.assertEqual((options.intra_op_num_threads, options.inter_op_num_threads), (1, 1))
        self.assertEqual(options.get_session_config_entry("session.intra_op.allow_spinning"), "0")
        with self.assertRaises(ValueError):
            M.predict(T1_VECTOR[:-1])


# --- Plugin shell: manifest, translations, the rp layer ------------------------------------------------------------

_LANG = _DIR / "lang"


def _toml(path):
    import tomllib  # tools need Python >= 3.11 (validate_plugins.py)

    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _placeholders(s):
    return set(re.findall(r"\{(\w+)\}", s))


class ShellTests(unittest.TestCase):
    def test_manifest_tags_are_the_32(self):
        tool = _toml(_DIR / "plugin.toml")["tool"][0]
        self.assertEqual(len(tool["tags"]), 32)
        self.assertEqual(list(tool["tags"]), list(R.TAGS))

    def test_template_and_spanish_catalog_are_complete(self):
        """The template lists every id the plugin can show: the generator's literal ids plus the table ids that
        tools/series_identifier_template.py appends. es.toml has exactly those keys, each with a Spanish text that
        keeps the placeholders. (The ids actually shown at run time are checked by LayerTests.)"""
        template = _toml(_LANG / "template.toml")["strings"]
        needed = R.all_result_ids() | R.all_explain_ids() | set(R.EXPLAIN.values())
        self.assertEqual(sorted(needed - set(template)), [])
        self.assertEqual(set(template.values()), {""})
        es = _toml(_LANG / "es.toml")
        self.assertTrue(es["language"]["name"])
        strings = es["strings"]
        self.assertEqual(list(strings), list(template))
        for key, value in strings.items():
            self.assertIsInstance(value, str, key)
            self.assertTrue(value.strip(), key)
            self.assertEqual(_placeholders(key), _placeholders(value), key)

    def test_literal_ids_are_in_the_template(self):
        """lang/template.toml is current: every literal rp.tr id of seriesid.py is in it (and so, by the test above,
        in es.toml). Regenerate with `python -m radspider_plugin template org.radspider.series-identifier`."""
        import ast

        tree = ast.parse((_DIR / "seriesid.py").read_text(encoding="utf-8"))
        ids = {node.args[0].value for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "tr"
               and isinstance(node.func.value, ast.Name) and node.func.value.id == "rp"
               and node.args and isinstance(node.args[0], ast.Constant)}
        self.assertGreater(len(ids), 20)
        self.assertEqual(sorted(ids - set(_toml(_LANG / "template.toml")["strings"])), [])

    def test_verdict_tables(self):
        self.assertEqual(set(R.FEATURE_TAGS), set(R.FEATURES))
        self.assertTrue({t for t in R.FEATURE_TAGS.values() if t} <= set(R.TAGS))
        self.assertTrue(set(R.MODEL_AGREES) <= R.MR_KINDS)
        self.assertTrue(set().union(*R.MODEL_AGREES.values()) <= set(M.CLASSES))
        self.assertTrue(R.DIFFUSION_ACQUIRED <= R.MR_KINDS)

    def test_model_verdict(self):
        t1, dwi, pd = "T1-weighted", "Diffusion-weighted", "Proton density-weighted"
        low = M.LOW_PROBABILITY
        self.assertEqual(R.model_verdict(t1, None, "t1w", 0.9, low), "agrees")
        self.assertEqual(R.model_verdict(t1, None, "t2w", 0.9, low), "differs")
        self.assertEqual(R.model_verdict(t1, None, "t1w", 0.39, low), "low")
        self.assertEqual(R.model_verdict(pd, None, "t2w", 0.9, low), "no_class")  # the model has no PD class
        self.assertEqual(R.model_verdict(pd, None, "t2w", 0.1, low), "no_class")  # wins over a low probability
        self.assertEqual(R.model_verdict("MR angiography", None, "t1w", 0.9, low), "no_class")
        self.assertEqual(R.model_verdict("", None, "t2w", 0.9, low), "")  # the rules could not tell
        self.assertEqual(R.model_verdict(dwi, None, "tracew", 0.9, low), "unreliable")
        self.assertEqual(R.model_verdict(dwi, None, "tracew", 0.1, low), "unreliable")
        self.assertEqual(R.model_verdict(dwi, 1000.0, "dwig", 0.9, low), "agrees")
        self.assertEqual(R.model_verdict("ADC map", None, "adc", 0.9, low), "agrees")  # maps: Image Type decides

    def test_mr_kind_and_is_mr(self):
        self.assertEqual(R.mr_kind(R.identify({"0018,0080": 500.0, "0018,0081": 10.0}, {"modality": "MR"}, *AXIAL,
                                              False)), "T1-weighted")
        self.assertIsNone(R.mr_kind(R.identify({}, {"modality": "CT"}, *AXIAL, False)))
        self.assertEqual(R.mr_kind(R.identify({}, {"modality": "MR"}, None, None, False)), "")
        self.assertTrue(R.is_mr([], {"modality": "mr"}))
        self.assertFalse(R.is_mr([], {"modality": "CT"}))
        self.assertTrue(R.is_mr(R.identify({"0018,0080": 500.0}, None, None, None, False), None))


class _Text(str):
    """Stands in for rp.Text: the English rendering, and the id it came from."""

    def __new__(cls, id, args):
        obj = super().__new__(cls, id.format(**args))
        obj.id, obj.args = id, args
        return obj


class _Block:
    def __init__(self, kind, *args, **kwargs):
        self.kind, self.args, self.kwargs = kind, args, kwargs


def _fake_rp():
    rp = types.ModuleType("radspider_plugin")
    rp.ids, rp.tools = [], {}

    def tr(id, **args):
        for k, v in args.items():  # the SDK refuses a text argument over 1000 characters
            if isinstance(v, str) and len(v) > 1000:
                raise ValueError("text %r: arg %s is longer than 1000 characters" % (id, k))
        rp.ids.append(id)
        return _Text(id, args)

    def tool(name):
        def wrap(fn):
            rp.tools[name] = fn
            return fn
        return wrap

    rp.tr, rp.tool = tr, tool
    for kind in ("Label", "Table", "Row", "Section", "Button", "Window", "Result"):
        setattr(rp, kind, lambda *a, _k=kind, **kw: _Block(_k, *a, **kw))
    return rp


class _Volume:
    """What the host gives an image tool, as far as seriesid.py reads it."""

    def __init__(self, tags, row, col, spacing_source="pixel", rgb=None):
        self.tags = {k.lower(): v for k, v in tags.items()}  # the host keys tags in lower case
        self._rgb = rgb
        self.slice_rows = None if row is None else [row]
        self.slice_cols = None if col is None else [col]
        self.spacing_source = spacing_source

    def tag_source(self, tag):
        if tag.upper() not in R.TAGS:
            raise KeyError(tag)
        return "top" if self.tags.get(tag.lower()) is not None else None

    def rgb(self):
        if isinstance(self._rgb, BaseException):
            raise self._rgb
        return self._rgb


class _Series:
    def __init__(self, d):
        self.modality = d.get("modality")
        self.images = self.frames = self.phases = 1
        self.phase_axis = None
        b = d.get("b_values")
        self.b_values = tuple(b) if isinstance(b, (list, tuple)) else ()
        g = d.get("gradient_directions")
        self.gradient_directions = g if isinstance(g, int) else None
        self.image_types = ()


class _Ctx:
    def __init__(self, series):
        self.series = None if series is None else _Series(series)
        self.image = self.event = None
        self.progressed = []

    def progress(self, fraction, message=""):
        self.progressed.append((fraction, message))


_MR_T1 = {"0008,0008": "ORIGINAL\\PRIMARY\\M\\ND", "0008,0070": "SIEMENS", "0018,0080": 500.0, "0018,0081": 10.0,
          "0018,1314": 90.0, "0018,0095": 200.0, "0018,0050": 5.0, "0018,0020": "SE"}
_MR_DWI = {"0008,0008": "ORIGINAL\\PRIMARY\\DIFFUSION\\NONE", "0018,0080": 5000.0, "0018,0081": 90.0,
           "0018,1314": 90.0, "0018,0095": 1500.0, "0018,0050": 5.0}


class LayerTests(unittest.TestCase):
    """seriesid.py against a stand-in SDK: the window's shape, the model row, and that every id shown is in es.toml."""

    @classmethod
    def setUpClass(cls):
        cls.rp = _fake_rp()
        with mock.patch.dict(sys.modules, {"radspider_plugin": cls.rp, "seriesid_rules": R, "seriesid_model": M}):
            spec = importlib.util.spec_from_file_location("seriesid", _DIR / "seriesid.py")
            cls.S = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.S)
        cls.strings = _toml(_LANG / "es.toml")["strings"]
        cls.template = _toml(_LANG / "template.toml")["strings"]

    def setUp(self):
        self.rp.ids.clear()

    def call(self, tags, series, row, col, predict=None, download=False, rgb=None):
        ctx = _Ctx(series) if series is not None else _Ctx(None)
        predict = predict or mock.Mock(side_effect=M.Unavailable("offline"))
        with mock.patch.object(M, "predict", predict), \
                mock.patch.object(self.S, "_will_download", return_value=download):
            result = self.rp.tools["identify"](_Volume(tags, row, col, rgb=rgb), ctx)
        (window,) = result.kwargs["windows"]
        self.assertEqual(window.args[:2], ("main", None))
        return window.args[2], ctx

    @staticmethod
    def model_cell(blocks):
        cells = [r[1] for r in blocks[1].args[0] if r[0] == "Model (MR)"]
        return cells[0] if cells else None

    def test_every_case_renders_and_is_translated(self):
        for name, (tags, series, (row, col), _) in CASES.items():
            with self.subTest(name):
                blocks, _ = self.call(tags, series, row, col)
                kinds = [b.kind for b in blocks]
                self.assertEqual(kinds[:3], ["Row", "Table", "Section"])
                self.assertEqual(kinds[-2:], ["Section", "Label"])
                self.assertEqual(kinds.count("Section"), 3 if self.model_cell(blocks) is not None else 2)
        self.assertEqual(sorted(set(self.rp.ids) - set(self.template)), [])

    def test_model_row(self):
        mr = {"modality": "MR"}
        top = mock.Mock(return_value=[("t1w", 0.91), ("t2w", 0.05), ("flair", 0.04)])
        self.assertEqual(self.model_cell(self.call(_MR_T1, mr, *AXIAL, top)[0]), "t1w 0.91 · agrees")
        top = mock.Mock(return_value=[("t2w", 0.81), ("t1w", 0.1)])
        self.assertEqual(self.model_cell(self.call(_MR_T1, mr, *AXIAL, top)[0]), "t2w 0.81 · differs from the rules")
        top = mock.Mock(return_value=[("flair", 0.35), ("t1w", 0.3), ("t2w", 0.2)])
        self.assertEqual(self.model_cell(self.call(_MR_T1, mr, *AXIAL, top)[0]), "flair 0.35 · low probability")
        self.assertEqual(self.model_cell(self.call(_MR_T1, mr, *AXIAL)[0]), "model not run: offline")
        boom = mock.Mock(side_effect=RuntimeError("boom"))
        self.assertEqual(self.model_cell(self.call(_MR_T1, mr, *AXIAL, boom)[0]), "model not run: RuntimeError: boom")
        self.assertIsNone(self.model_cell(self.call(_MR_T1, {"modality": "CT"}, *AXIAL)[0]))

    def test_model_refusal_and_unreliable_b(self):
        mr = {"modality": "MR"}
        no_flip = {k: v for k, v in _MR_T1.items() if k != "0018,1314"}
        blocks, _ = self.call(no_flip, mr, *AXIAL, mock.Mock(return_value=[("t1w", 0.9)]))
        self.assertEqual(self.model_cell(blocks), "model not run: FlipAngle missing")
        blocks, _ = self.call(_MR_T1, mr, None, None, mock.Mock(return_value=[("t1w", 0.9)]))
        self.assertEqual(self.model_cell(blocks), "model not run: Image Orientation missing")
        blocks, _ = self.call(_MR_DWI, mr, *AXIAL, mock.Mock(return_value=[("tracew", 0.8)]))
        self.assertEqual(self.model_cell(blocks), "tracew · unreliable: no standard b-value")
        detail = [b for b in blocks if b.kind == "Section" and b.args[0] == "Model detail"][0].args[1]
        self.assertNotIn("Probability", [str(c) for b in detail if b.kind == "Table" for c in b.args[0][0]])
        self.assertTrue(any(b.kind == "Label" and b.kwargs.get("weak") for b in detail))
        dwi_b = dict(_MR_DWI, **{"0018,9087": 1000.0})
        blocks, _ = self.call(dwi_b, dict(mr, b_values=[0.0, 1000.0]), *AXIAL,
                              mock.Mock(return_value=[("t2w", 0.7)]))
        self.assertEqual(self.model_cell(blocks), "tracew 0.70 · agrees")  # the series step rewrote t2w

    def test_no_model_class(self):
        pd = dict(_MR_T1, **{"0018,0080": 3000.0, "0018,0081": 15.0})
        blocks, _ = self.call(pd, {"modality": "MR"}, *AXIAL, mock.Mock(return_value=[("t2w", 0.3)]))
        self.assertEqual(self.model_cell(blocks), "t2w 0.30 · no model class for this series type")

    def test_long_tag_text_is_cut(self):
        agent = "A" * 1024  # a tag value may be 1024 characters; the SDK takes 1000
        blocks, _ = self.call({"0018,0010": agent}, {"modality": "CT"}, *AXIAL)
        cells = [r[1] for r in blocks[1].args[0] if r[0] == "Contrast"]
        self.assertEqual(cells, ["Contrast agent recorded (%s)" % ("A" * 1000)])

    def us_series(self, rgb):
        tags = {"0008,0008": "ORIGINAL\\PRIMARY\\ABDOMINAL", "0008,0070": "GE Healthcare", "0018,0015": "ABDOMEN",
                "0008,103E": "Abdomen"}
        blocks, _ = self.call(tags, {"modality": "US"}, None, None, rgb=rgb)
        return [(r[1], r[2]) for r in blocks[1].args[0] if r[0] == "Series"][0]

    def test_ultrasound_colour_is_measured(self):
        rows, cols = 768, 1024
        grey = bytes(v for i in range(rows * cols) for v in ((i * 7) % 256,) * 3)  # grey stored as RGB
        result, evidence = self.us_series(grey)
        self.assertEqual(result, "Ultrasound, greyscale")
        self.assertIn("pixels grey", evidence)
        doppler = bytearray(grey)
        for p in range(0, rows * cols, 50):  # 2 % of pixels red: a colour Doppler box
            doppler[3 * p:3 * p + 3] = b"\xc8\x20\x20"
        result, evidence = self.us_series(bytes(doppler))
        self.assertEqual(result, "Ultrasound, colour (Doppler or colour map)")
        self.assertIn("2.00 % of pixels", evidence)
        sparse = bytearray(grey)
        sparse[0:3] = b"\xff\x00\x00"  # one coloured pixel (a cursor): below 0.1 %
        self.assertEqual(self.us_series(bytes(sparse))[0], "Ultrasound, greyscale")
        result, evidence = self.us_series(ValueError("colour file holds 3 bytes, expected 9"))
        self.assertEqual(result, "Ultrasound, greyscale")
        self.assertIn("colour data unreadable", evidence)
        self.assertEqual(self.us_series(None), ("Ultrasound, greyscale", "image is greyscale"))

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "needs numpy")
    def test_ultrasound_colour_numpy(self):
        import numpy as np

        grey = np.repeat(np.arange(768 * 1024, dtype=np.uint32).reshape(768, 1024, 1) % 256, 3, axis=2)
        grey = grey.astype(np.uint8)
        self.assertEqual(self.us_series(grey)[0], "Ultrasound, greyscale")
        colour = grey.copy()
        colour[100:200, 100:300] = (40, 60, 220)  # a colour box with values below the grey ones: no wraparound
        self.assertEqual(self.us_series(colour)[0], "Ultrasound, colour (Doppler or colour map)")

    def test_progress_only_around_a_download(self):
        def predict(vector, progress):
            if progress:
                progress(0.5)
            return [("t1w", 0.9)]

        for download in (False, True):
            _, ctx = self.call(_MR_T1, {"modality": "MR"}, *AXIAL, predict, download)
            if download:
                self.assertEqual([round(f, 2) for f, _ in ctx.progressed], [0.2, 0.55])
                self.assertEqual(ctx.progressed[0][1], "Downloading the MR model (305 KB)…")
            else:
                self.assertEqual(ctx.progressed, [])


if __name__ == "__main__":
    unittest.main()

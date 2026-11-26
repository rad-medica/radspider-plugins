"""Tests of the five structured report plugins (birads, pirads, lirads, lungrads, tirads).

The scoring rules are pure functions, tested against their tables with a stand-in for the host's SDK. With a radspider
checkout beside this repository, every form is also built with the real SDK at its largest (all findings open) and
checked against the host's window limits; without it those tests are skipped. Catalogs: lang/es.toml has exactly the
ids of lang/template.toml, with the same placeholders."""

import importlib.util
import json
import re
import sys
import tempfile
import tomllib
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SDK = ROOT.parent / "radspider" / "assets" / "python"
PLUGINS = {"birads": "birads", "pirads": "pirads", "lirads": "lirads", "lungrads": "lungrads", "tirads": "tirads"}


def _stand_in():
    """radspider_plugin reduced to what the modules call at import time: rp.tr / rp.trn give the English text."""
    rp = types.ModuleType("radspider_plugin")
    rp.tr = lambda id, **a: id.format(**a) if a else id
    rp.trn = lambda n, one, other, **a: (one if n == 1 else other).format(n=n, **a)
    rp.tool = lambda name: lambda f: f
    return rp


def _load(name, rp):
    with mock.patch.dict(sys.modules, {"radspider_plugin": rp}):
        spec = importlib.util.spec_from_file_location("report_" + name, ROOT / ("org.radspider." + name) / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _real_sdk():
    if not (SDK / "radspider_plugin.py").is_file():
        return None
    spec = importlib.util.spec_from_file_location("radspider_plugin", SDK / "radspider_plugin.py")
    rp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rp)
    rp._MARKING = True
    return rp


R = {name: _load(name, _stand_in()) for name in PLUGINS}


class TiRadsTests(unittest.TestCase):
    T = R["tirads"]

    def test_points_and_levels(self):
        p = self.T.points
        # Solid 2 + very hypoechoic 3 + taller-than-wide 3 + punctate 3 = 11 (TR5)
        self.assertEqual(p("Solid or almost completely solid", "Very hypoechoic", "Taller-than-wide", "Smooth",
                           ["punctate"]), 11)
        # Echogenic foci add up: macro 1 + rim 2 + punctate 3
        self.assertEqual(p("Mixed cystic and solid", "Anechoic", "Wider-than-tall", "Smooth",
                           ["macro", "rim", "punctate"]), 7)
        # Spongiform and cystic: 0 whatever else is set
        for comp in ("Spongiform", "Cystic or almost completely cystic"):
            self.assertEqual(p(comp, "Very hypoechoic", "Taller-than-wide", "Extra-thyroidal extension",
                               ["punctate"]), 0)
        self.assertEqual([self.T.level(s) for s in range(0, 9)], [1, 2, 2, 3, 4, 4, 4, 5, 5])

    def test_fna_and_follow_up_thresholds(self):
        a = self.T.advice
        self.assertEqual(a(2, 40), (False, None))
        self.assertEqual(a(3, 25)[0], True)
        self.assertEqual(a(3, 24)[1], "Follow-up ultrasound at 1, 3 and 5 years")
        self.assertEqual(a(3, 14), (False, None))
        self.assertEqual(a(4, 15)[0], True)
        self.assertEqual(a(4, 10)[1], "Follow-up ultrasound at 1, 2, 3 and 5 years")
        self.assertEqual(a(5, 10)[0], True)
        self.assertEqual(a(5, 5)[1], "Follow-up ultrasound every year for up to 5 years")
        self.assertEqual(a(5, 4), (False, None))

    def test_tnm(self):
        t = self.T.t_category
        inside = "Confined to the thyroid"
        self.assertEqual([t(s, inside) for s in (0, 10, 11, 20, 21, 40, 41)],
                         ["TX", "T1a", "T1b", "T1b", "T2", "T2", "T3a"])
        self.assertEqual(t(5, "Gross extension into strap muscles"), "T3b")
        self.assertEqual(self.T.n_category([True]), "N1a")
        self.assertEqual(self.T.n_category([True, False]), "N1b")
        self.assertEqual(self.T.n_category([]), "N0")
        s = self.T.stage
        self.assertEqual([s("T4b", "N1b", False, False), s("T1a", "N0", False, True)], ["I", "II"])
        self.assertEqual([s("T1b", "N0", True, False), s("T2", "N1a", True, False), s("T3b", "N0", True, False),
                          s("T4a", "N0", True, False), s("T4b", "N0", True, False), s("T1a", "N0", True, True)],
                         ["I", "II", "II", "III", "IVA", "IVB"])

    def test_locate(self):
        loc = self.T.locate
        self.assertEqual(loc(195, 100), ("nodule", 0))  # right lobe, upper third
        self.assertEqual(loc(265, 190), ("nodule", 6))  # left lobe, lower third
        self.assertEqual(loc(230, 170), ("nodule", 3))  # isthmus
        self.assertEqual(loc(90, 150)[1][0], "r3")
        self.assertEqual(loc(230, 280)[1][0], "c7")
        self.assertEqual(loc(150, 290), (None, None))

    def test_sketch_edit_flow(self):
        """Editing a control writes it into the selected mark; labels, tones and cN follow the marks."""
        captured = {}
        rp = _stand_in()
        stub = types.SimpleNamespace
        for kind in ("Choice", "Number", "Checkbox", "TextField", "Label", "Row", "Section", "Separator", "Button"):
            setattr(rp, kind, lambda *a, **k: stub())
        rp.Sketch = lambda *a, value=None, **k: captured.setdefault("value", value)
        rp.Table = lambda rows, csv=True: captured.setdefault("rows", [[str(c) for c in r] for r in rows])
        rp.Window = lambda *a, **k: stub()
        rp.Result = lambda windows: windows
        module = _load("tirads", rp)
        marks = [{"id": 1, "x": 195, "y": 140, "r": 8, "data": {}}, {"id": 2, "x": 90, "y": 150, "r": 6, "data": {}}]
        edit = {"comp": "Solid or almost completely solid", "echo": "Very hypoechoic", "shape": "Taller-than-wide",
                "margin": "Smooth", "punctate": True, "macro": False, "rim": False, "ap": 12.0, "tv": 9.0, "cc": 14.0}
        controls = {k + "_1": v for k, v in edit.items()}
        # the user edited nodule 1, then selected node 2 before that run started: the edit must stay on nodule 1
        controls.update(neck={"marks": marks, "selected": 2},
                        staging="Differentiated thyroid carcinoma (AJCC 8th edition)")
        module.report(None, stub(controls=controls, event="neck"))
        nodule, node = captured["value"]["marks"]
        self.assertEqual(nodule["data"]["punctate"], "1")
        self.assertEqual((nodule["label"], nodule["tone"]), ("N1 TR5", "error"))
        self.assertEqual((node["label"], node["form"], node["tone"]), ("L1", "square", "ok"))  # hilum by default
        self.assertIn(["Recommendation", "FNA (from 10 mm at this level)"], captured["rows"])
        node["data"] = {"micro": "1"}
        captured.clear()
        controls = {"neck": {"marks": [nodule, node], "selected": None}, "staging": controls["staging"]}
        module.report(None, stub(controls=controls, event="neck"))
        self.assertEqual(captured["value"]["marks"][1]["label"], "L1 S")
        self.assertIn("cTX cN1b cM0", [r[1] for r in captured["rows"]])


class PiRadsTests(unittest.TestCase):
    P = R["pirads"]

    def test_peripheral_zone(self):
        c = self.P.category
        self.assertEqual([c("PZ", 5, d, False) for d in range(1, 6)], [1, 2, 3, 4, 5])
        self.assertEqual(c("PZ", 1, 3, True), 4)
        self.assertEqual(c("PZ", 1, 3, None), 3)  # biparametric: no upgrade

    def test_transition_zone(self):
        c = self.P.category
        self.assertEqual([c("TZ", 1, d, True) for d in range(1, 6)], [1] * 5)
        self.assertEqual([c("TZ", 2, d, None) for d in range(1, 6)], [2, 2, 2, 3, 3])
        self.assertEqual([c("TZ", 3, d, None) for d in range(1, 6)], [3, 3, 3, 3, 4])
        self.assertEqual([c("TZ", t, 1, None) for t in (4, 5)], [4, 5])

    def test_no_rule(self):
        self.assertIsNone(self.P.category("CZ", 4, 4, True))
        self.assertIsNone(self.P.category("AS", 4, 4, True))
        self.assertIsNone(self.P.category("PZ", 4, None, True))
        self.assertAlmostEqual(self.P.volume_ml(40, 50, 45), 46.8)

    def test_locate(self):
        loc = self.P.locate
        self.assertEqual(loc(70, 80), (0, 0, "AS"))  # base, anterior stroma, right
        self.assertEqual(loc(70, 105), (0, 0, "TZa"))
        self.assertEqual(loc(250, 125), (1, 1, "TZp"))
        self.assertEqual(loc(85, 150), (0, 1, "CZ"))
        self.assertEqual(loc(240, 160), (1, 1, "PZpm"))
        self.assertEqual(loc(185, 145), (1, 0, "PZpl"))
        self.assertEqual(loc(190, 105), (1, 0, "PZa"))
        self.assertEqual(loc(380, 150), (2, 2, "PZpm"))
        self.assertIsNone(loc(155, 40))

    def test_sketch_edit_flow(self):
        """An edit of lesion 1 survives selecting lesion 2 before the run; labels, tones and the overall follow."""
        captured = {}
        rp = _stand_in()
        stub = types.SimpleNamespace
        for kind in ("Choice", "Number", "Checkbox", "TextField", "Label", "Row", "Section", "Separator", "Button"):
            setattr(rp, kind, lambda *a, **k: stub())
        rp.Sketch = lambda *a, value=None, **k: captured.setdefault("value", value)
        rp.Table = lambda rows, csv=True: captured.setdefault("rows", [[str(c) for c in r] for r in rows])
        rp.Window = lambda *a, **k: stub()
        rp.Result = lambda windows: windows
        module = _load("pirads", rp)
        marks = [{"id": 1, "x": 185, "y": 145, "r": 8, "data": {}}, {"id": 2, "x": 85, "y": 150, "r": 6, "data": {}},
                 {"id": 3, "x": 155, "y": 40, "r": 5, "data": {}}]
        controls = {"t2_1": "4", "dwi_1": "3", "dce_1": "Positive", "size_1": 12.0,
                    "map": {"marks": marks, "selected": 2}}
        module.report(None, stub(controls=controls, event="map"))
        pz, cz, out = captured["value"]["marks"]
        self.assertEqual(pz["data"]["dce"], "Positive")
        self.assertEqual((pz["label"], pz["tone"]), ("L1 P4", "warn"))
        self.assertEqual((cz["label"], out["label"], out["tone"]), ("L2 P?", "?", "muted"))
        self.assertIn("Not assigned: a lesion has no category yet", [r[1] for r in captured["rows"]])
        self.assertIn(["Sector", "Peripheral zone, posterolateral (PZpl)"], captured["rows"])
        captured.clear()
        cz["data"]["manual"] = "PI-RADS 2"
        module.report(None, stub(controls={"map": {"marks": [pz, cz], "selected": None}}, event="map"))
        self.assertEqual(captured["value"]["marks"][1]["label"], "L2 P2")
        self.assertIn(["Overall assessment", "PI-RADS 4: high (clinically significant cancer is likely to be present)"],
                      captured["rows"])


class LiRadsTests(unittest.TestCase):
    L = R["lirads"]

    def test_diagnostic_table(self):
        t = self.L.table_category
        cases = [  # (aphe, size, washout, capsule, growth, expected)
            (False, 15, 0, 0, 0, "LR-3"), (False, 15, 1, 0, 0, "LR-3"), (False, 15, 1, 1, 0, "LR-4"),
            (False, 25, 0, 0, 0, "LR-3"), (False, 25, 0, 1, 0, "LR-4"), (False, 25, 1, 1, 1, "LR-4"),
            (True, 8, 0, 0, 0, "LR-3"), (True, 8, 1, 0, 0, "LR-4"), (True, 8, 1, 1, 1, "LR-4"),
            (True, 15, 0, 0, 0, "LR-3"), (True, 15, 0, 1, 0, "LR-4"), (True, 15, 1, 0, 0, "LR-5"),
            (True, 15, 0, 0, 1, "LR-5"), (True, 15, 0, 1, 1, "LR-5"),
            (True, 25, 0, 0, 0, "LR-4"), (True, 25, 0, 1, 0, "LR-5"),
        ]
        for aphe, size, w, c, g, want in cases:
            with self.subTest(aphe=aphe, size=size, w=w, c=c, g=g):
                self.assertEqual(t(aphe, size, bool(w), bool(c), bool(g)), want)

    def test_ancillary_features(self):
        a = self.L.adjust
        up, down = "Ancillary features favouring malignancy", "Ancillary features favouring benignity"
        self.assertEqual([a(k, up) for k in ("LR-2", "LR-3", "LR-4", "LR-5")], ["LR-3", "LR-4", "LR-4", "LR-5"])
        self.assertEqual([a(k, down) for k in ("LR-1", "LR-3", "LR-5")], ["LR-1", "LR-2", "LR-4"])
        self.assertEqual(a("LR-4", "Ancillary features favouring both (no adjustment)"), "LR-4")

    def test_locate(self):
        loc = self.L.locate
        self.assertEqual([loc(70, 100), loc(80, 180), loc(155, 90), loc(155, 180), loc(220, 90), loc(220, 175)],
                         ["VII", "VI", "VIII", "V", "IVa", "IVb"])
        self.assertEqual([loc(245, 132), loc(350, 80), loc(330, 130)], ["I", "II", "III"])
        self.assertIsNone(loc(10, 10))
        self.assertIsNone(loc(400, 200))

    def test_sketch_edit_flow(self):
        """Editing a control writes it into its mark; labels, tones and the summary follow the marks."""
        captured = {}
        rp = _stand_in()
        stub = types.SimpleNamespace
        for kind in ("Choice", "Number", "Checkbox", "TextField", "Label", "Row", "Section", "Separator", "Button"):
            setattr(rp, kind, lambda *a, **k: stub())
        rp.Sketch = lambda *a, value=None, **k: captured.setdefault("value", value)
        rp.Table = lambda rows, csv=True: captured.setdefault("rows", [[str(c) for c in r] for r in rows])
        rp.Window = lambda *a, **k: stub()
        rp.Result = lambda windows: windows
        module = _load("lirads", rp)
        marks = [{"id": 1, "x": 155, "y": 180, "r": 8, "data": {}}, {"id": 2, "x": 350, "y": 80, "r": 6, "data": {}},
                 {"id": 3, "x": 10, "y": 10, "r": 4, "data": {}}]
        edit = {"size": 25.0, "path": "Diagnostic table", "aphe": "Nonrim arterial phase hyperenhancement",
                "washout": True, "capsule": False, "growth": False, "ancillary": "No ancillary features"}
        controls = {k + "_1": v for k, v in edit.items()}
        # the user edited observation 1, then selected observation 2 before that run started: the edit stays on 1
        controls["liver"] = {"marks": marks, "selected": 2}
        module.report(None, stub(controls=controls, event="liver"))
        one, two, out = captured["value"]["marks"]
        self.assertEqual(one["data"]["washout"], "1")
        self.assertEqual((one["label"], one["tone"]), ("O1 LR5", "error"))
        self.assertEqual((two["label"], two["tone"]), ("O2", "accent"))  # no size yet: not assigned
        self.assertEqual((out["label"], out["tone"]), ("?", "muted"))
        self.assertIn(["Segment", "V"], captured["rows"])
        self.assertIn("Not assigned: an observation has no category yet", [r[1] for r in captured["rows"]])
        two["data"] = {"path": "LR-M: probably or definitely malignant, not HCC specific"}
        captured.clear()
        module.report(None, stub(controls={"liver": {"marks": [one, two], "selected": None}}, event="liver"))
        self.assertEqual(captured["value"]["marks"][1]["label"], "O2 LRM")
        self.assertEqual(dict((r[0], r[1]) for r in captured["rows"])["Most worrying observation"],
                         "LR-M: probably or definitely malignant, not HCC specific")


class LungRadsTests(unittest.TestCase):
    G = R["lungrads"]

    def test_solid(self):
        c = self.G.category
        self.assertEqual([c("solid", "baseline", d, 0) for d in (5.9, 6, 7.9, 8, 14.9, 15)],
                         ["2", "3", "3", "4A", "4A", "4B"])
        self.assertEqual([c("solid", "new", d, 0) for d in (3.9, 4, 5.9, 6, 7.9, 8)],
                         ["2", "3", "3", "4A", "4A", "4B"])
        self.assertEqual([c("solid", "growing", d, 0) for d in (7.9, 8)], ["4A", "4B"])
        self.assertEqual(c("solid", "slow", 6, 0), "4B")
        self.assertEqual([c("solid", s, 20, 0) for s in ("stable", "after3", "after4a")], ["2", "2", "3"])

    def test_part_solid_ground_glass_juxtapleural(self):
        c = self.G.category
        self.assertEqual([c("part", "baseline", d, s) for d, s in ((5.9, 3), (10, 5.9), (10, 6), (10, 8))],
                         ["2", "3", "4A", "4B"])
        self.assertEqual([c("part", "new", d, s) for d, s in ((5, 2), (8, 3.9), (8, 4))], ["3", "4A", "4B"])
        self.assertEqual([c("part", "growing", 10, s) for s in (3.9, 4)], ["4A", "4B"])
        self.assertEqual([c("gg", s, d, 0) for s, d in (("baseline", 29), ("new", 30), ("growing", 20),
                                                       ("slow", 35), ("growing", 35))], ["2", "3", "2", "2", None])
        self.assertEqual([c("juxta", "baseline", 9.9, 0), c("juxta", "baseline", 10, 0)], ["2", "4A"])

    def test_airway_and_cysts(self):
        c = self.G.category
        self.assertEqual([c("airway_sub", s, 0, 0) for s in ("baseline", "stable", "growing")], ["2", "2", None])
        self.assertEqual([c("airway_seg", s, 0, 0) for s in ("new", "stable", "after4a")], ["4A", "4B", "4B"])
        self.assertEqual([c(k, "baseline", 0, 0) for k in ("benign", "cyst_3", "cyst_4a", "cyst_4b")],
                         ["1", "3", "4A", "4B"])
        self.assertIsNone(c("part", "baseline", 10, 0))  # solid component not entered

    def test_locate(self):
        loc = self.G.locate
        cases = {(100, 70): 0, (150, 140): 1, (70, 200): 2, (345, 80): 3, (320, 180): 4, (395, 215): 5,
                 (230, 130): None, (10, 10): None}
        for (x, y), want in cases.items():
            self.assertEqual(loc(x, y), want, (x, y))

    def test_sketch_edit_flow(self):
        """An edit of nodule 1 survives selecting nodule 2 before the run; labels, tones and the exam follow."""
        captured = {}
        rp = _stand_in()
        stub = types.SimpleNamespace
        for kind in ("Choice", "Number", "Checkbox", "TextField", "Label", "Row", "Section", "Separator", "Button"):
            setattr(rp, kind, lambda *a, **k: stub())
        rp.Sketch = lambda *a, value=None, **k: captured.setdefault("value", value)
        rp.Table = lambda rows, csv=True: captured.setdefault("rows", [[str(c) for c in r] for r in rows])
        rp.Window = lambda *a, **k: stub()
        rp.Result = lambda windows: windows
        module = _load("lungrads", rp)
        marks = [{"id": 1, "x": 100, "y": 70, "r": 6, "data": {}}, {"id": 2, "x": 395, "y": 215, "r": 6, "data": {}},
                 {"id": 3, "x": 230, "y": 130, "r": 6, "data": {}}]
        controls = {"type_1": "Solid", "status_1": "Baseline", "d_1": 9.0, "x_1": False, "manual_1": "Computed",
                    "lungs": {"marks": marks, "selected": 2}}
        module.report(None, stub(controls=controls, event="lungs"))
        a, b, out = captured["value"]["marks"]
        self.assertEqual(a["data"]["d"], "9")
        self.assertEqual((a["label"], a["tone"]), ("N1 4A", "warn"))
        self.assertEqual((b["label"], b["tone"]), ("N2 ?", "warn"))  # no diameter yet
        self.assertEqual((out["label"], out["tone"]), ("?", "muted"))
        self.assertIn("Not assigned: a finding has no category yet", [r[1] for r in captured["rows"]])
        captured.clear()
        controls = {"d_2": 3.0, "lungs": {"marks": [a, b], "selected": 2}}
        module.report(None, stub(controls=controls, event="d_2"))
        self.assertEqual(captured["value"]["marks"][1]["label"], "N2 2")
        self.assertIn("Lung-RADS 4A: suspicious", [r[1] for r in captured["rows"]])


class SummaryTests(unittest.TestCase):
    """A report never states a finding nobody entered, nor an exam category a finding without one cannot support."""

    def test_defaults_and_unassigned(self):
        stub = types.SimpleNamespace
        captured = {}

        def window(id, title=None, blocks=(), size=None, icon=None, keep=False, reopen=False):
            captured.setdefault("windows", []).append(id)
            for b in blocks:
                if isinstance(b, stub) and b.kind == "table":
                    captured["rows"] = [[str(c) for c in r] for r in b.rows]
            return stub()

        rp = _stand_in()
        for kind in ("Choice", "Number", "Checkbox", "TextField", "Label", "Row", "Section", "Separator", "Sketch",
                     "Button"):
            setattr(rp, kind, lambda *a, _k=kind, **k: stub(kind=_k))
        rp.Table = lambda rows, csv=True: stub(kind="table", rows=rows)
        rp.Window = window
        rp.Result = lambda windows: windows
        cases = {
            "birads": ({}, {"breasts": {"marks": [{"id": 1, "x": 120, "y": 60, "r": 8, "data": {}}], "selected": None}},
                       "Not assigned: a finding has no category yet"),
            "pirads": ({}, {"map": {"marks": [{"id": 1, "x": 85, "y": 150, "r": 6, "data": {}}], "selected": None}},
                       "Not assigned: a lesion has no category yet"),
            "lirads": ({}, {"liver": {"marks": [{"id": 1, "x": 155, "y": 180, "r": 8, "data": {}}], "selected": None}},
                       "Not assigned: an observation has no category yet"),
            "lungrads": ({}, {"lungs": {"marks": [{"id": 1, "x": 100, "y": 70, "r": 6, "data": {}}], "selected": None}},
                         "Not assigned: a finding has no category yet"),
            "tirads": ({}, None, None),
        }
        for name, (first, partial, text) in cases.items():
            with self.subTest(plugin=name):
                module = _load(name, rp)
                captured.clear()
                module.report(None, stub(controls=first, event=None))
                self.assertEqual(captured["windows"], ["main"])  # first open: no finding windows
                if partial is not None:
                    captured.clear()
                    module.report(None, stub(controls=partial, event=None))
                    self.assertIn(text, [r[1] for r in captured["rows"]])


class BiRadsTests(unittest.TestCase):
    B = R["birads"]

    def test_hierarchy(self):
        o = self.B.overall
        self.assertEqual(o([]), "1")
        self.assertEqual(o(["2", "6", "3"]), "6")
        self.assertEqual(o(["6", "0"]), "0")
        self.assertEqual(o(["0", "4A"]), "4A")
        self.assertEqual(o(["4C", "5", "4B"]), "5")
        self.assertIsNone(o(["4C", None]))

    def test_subcategories_by_modality(self):
        self.assertNotIn("4", self.B.codes("mammo"))
        self.assertIn("4B", self.B.codes("us"))
        self.assertEqual([k for k in self.B.codes("mri") if k.startswith("4")], ["4"])

    def test_locate(self):
        loc = self.B.locate
        self.assertEqual(loc(120, 140), (0, "Retroareolar"))
        self.assertEqual(loc(120, 60), (0, "12:00"))  # right breast, up
        self.assertEqual(loc(200, 140), (0, "3:00"))  # right breast, reader's right (medial)
        self.assertEqual(loc(40, 140), (0, "9:00"))  # right breast, lateral
        self.assertEqual(loc(340, 220), (1, "6:00"))
        self.assertEqual(loc(390, 54), (1, "1:00"))
        self.assertIsNone(loc(230, 30))  # between the breasts

    def test_sketch_edit_flow(self):
        """An edit of finding 1 survives selecting finding 2 before the run; labels, tones and the summary follow."""
        captured = {}
        rp = _stand_in()
        stub = types.SimpleNamespace
        for kind in ("Choice", "Number", "Checkbox", "TextField", "Label", "Row", "Section", "Separator", "Button"):
            setattr(rp, kind, lambda *a, **k: stub())
        rp.Sketch = lambda *a, value=None, **k: captured.setdefault("value", value)
        rp.Table = lambda rows, csv=True: captured.setdefault("rows", [[str(c) for c in r] for r in rows])
        rp.Window = lambda *a, **k: stub()
        rp.Result = lambda windows: windows
        module = _load("birads", rp)
        marks = [{"id": 1, "x": 120, "y": 60, "r": 8, "data": {}}, {"id": 2, "x": 340, "y": 140, "r": 6, "data": {}},
                 {"id": 3, "x": 230, "y": 30, "r": 4, "data": {}}]
        controls = {"type_1": "Mass", "cat_1": "BI-RADS 4B: moderate suspicion for malignancy", "size_1": 12.0,
                    "breasts": {"marks": marks, "selected": 2}}
        module.report(None, stub(controls=controls, event="breasts"))
        one, two, out = captured["value"]["marks"]
        self.assertEqual(one["data"]["cat"], "BI-RADS 4B: moderate suspicion for malignancy")
        self.assertEqual((one["label"], one["tone"]), ("F1 4B", "error"))
        self.assertEqual((two["label"], two["tone"]), ("F2", "accent"))
        self.assertEqual((out["label"], out["tone"]), ("?", "muted"))
        rows = captured["rows"]
        self.assertIn(["Location", "12:00"], rows)
        self.assertIn(["Location", "Retroareolar"], rows)
        self.assertIn("Not assigned: a finding has no category yet", [r[1] for r in rows])
        two["data"] = {"cat": "BI-RADS 2: benign"}
        captured.clear()
        module.report(None, stub(controls={"breasts": {"marks": [one, two, out], "selected": None}}, event="breasts"))
        self.assertEqual(captured["value"]["marks"][1]["tone"], "ok")
        self.assertIn(["Overall assessment", "BI-RADS 4B: moderate suspicion for malignancy"], captured["rows"])


class CatalogTests(unittest.TestCase):
    def test_spanish_catalogs_match_templates(self):
        holes = re.compile(r"\{\w+\}")
        for name in PLUGINS:
            with self.subTest(plugin=name):
                lang = ROOT / ("org.radspider." + name) / "lang"
                template = tomllib.loads((lang / "template.toml").read_text(encoding="utf-8"))["strings"]
                es = tomllib.loads((lang / "es.toml").read_text(encoding="utf-8"))["strings"]
                self.assertEqual(set(template), set(es))
                for key, value in es.items():
                    forms = value.values() if isinstance(value, dict) else [value]
                    for form in forms:
                        self.assertTrue(form, key)
                        self.assertEqual(set(holes.findall(form)), set(holes.findall(key)), key)


RP = _real_sdk()


@unittest.skipIf(RP is None, "no radspider checkout beside this repository")
class WindowLimitTests(unittest.TestCase):
    """Every form at its largest, wired by the real SDK, within the host's limits (radspider docs/PLUGINS.md)."""

    def controls(self, blocks):
        for b in blocks:
            if b["kind"] == "control":
                yield b["control"]["name"]
            yield from self.controls(b.get("blocks", []))
            for tab in b.get("tabs", []):
                yield from self.controls(tab["blocks"])

    def test_largest_forms(self):
        largest = {"birads": {"modality": "Mammography and ultrasound", "type_1": "Mass",
                              "breasts": {"marks": [{"id": 1, "x": 120, "y": 60, "r": 8, "data": {}}], "selected": 1}},
                   "pirads": {"map": {"marks": [{"id": 1, "x": 85, "y": 150, "r": 6, "data": {"dwi": "Inadequate"}}],
                                      "selected": 1}},
                   "lirads": {"liver": {"marks": [{"id": 1, "x": 155, "y": 180, "r": 10, "data": {}}], "selected": 1}},
                   "lungrads": {"lungs": {"marks": [{"id": 1, "x": 100, "y": 70, "r": 6,
                                                     "data": {"type": "Part-solid"}}], "selected": 1}},
                   "tirads": {"neck": {"marks": [{"id": 1, "x": 195, "y": 140, "r": 10, "data": {}}], "selected": 1},
                              "staging": "Differentiated thyroid carcinoma (AJCC 8th edition)"}}
        for name, controls in largest.items():
            with self.subTest(plugin=name):
                RP._REGISTRY["tool"].clear()  # every plugin registers "report"; the host runs one plugin per process
                module = _load(name, RP)
                result = module.report(None, types.SimpleNamespace(controls=controls, event="count"))
                with tempfile.TemporaryDirectory() as tmp:
                    wired = [w._wire(RP._Emit(tmp)) for w in result.windows]
                self.assertLessEqual(len(wired), 8)
                names = []
                for w in wired:
                    found = list(self.controls(w["blocks"]))
                    self.assertLessEqual(len(found), 32, w["id"])
                    self.assertLessEqual(len(w["blocks"]), 256, w["id"])
                    names += found
                self.assertLessEqual(len(names), 64)
                self.assertEqual(len(names), len(set(names)))
                self.assertTrue(any(b["kind"] == "table" for b in wired[0]["blocks"]))
                json.dumps(wired)  # the answer must serialise as it is sent


if __name__ == "__main__":
    unittest.main()

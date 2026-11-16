"""Tests of org.radspider.series-identifier/seriesid_rules.py (pure Python, loaded by path)."""

import importlib.util
import math
import unittest
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "org.radspider.series-identifier" / "seriesid_rules.py"
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
        self.assertEqual(R.text(["a", " b "]), "A\B")
        self.assertIsNone(R.text(["", None]))
        self.assertEqual(R.numbers([0.5, 0.5]), [0.5, 0.5])
        self.assertIsNone(R.number("x"))
        self.assertEqual(R.number(" 2.5 "), 2.5)
        self.assertEqual(R.number([3]), 3.0)
        self.assertIsNone(R.number(None))
        self.assertIsNone(R.number(math.nan))
        self.assertEqual(R.numbers("1\2.5"), [1.0, 2.5])
        self.assertIsNone(R.numbers([1, "x"]))
        self.assertIsNone(R.numbers([]))

    def test_finding_is_frozen(self):
        f = R.Finding("plane", "axial", "x", ("a",))
        with self.assertRaises(Exception):
            f.item = "series"


if __name__ == "__main__":
    unittest.main()

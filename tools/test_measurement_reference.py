"""Tests of org.radspider.measurement-reference/reference.py (loaded by path, with a stand-in for the host's SDK).

Skipped without Pillow. They also check every shipped entry: a title, a region, a picture that decodes, a Source
section that names the picture's licence."""

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

_DIR = Path(__file__).resolve().parent.parent / "org.radspider.measurement-reference"

try:
    import PIL  # noqa: F401
except ImportError:
    PIL = None


def _load():
    """reference.py with `radspider_plugin` replaced by classes that only keep what they were given."""
    rp = types.ModuleType("radspider_plugin")

    def kind(name):
        return type(name, (), {"__init__": lambda self, *a, **k: self.__dict__.update(a=a, k=k)})

    for name in ("Label", "Table", "Image", "Section", "Row", "Separator", "TextField", "Choice", "Window", "Result"):
        setattr(rp, name, kind(name))
    rp.tool = lambda name: lambda f: f
    with mock.patch.dict(sys.modules, {"radspider_plugin": rp}):
        spec = importlib.util.spec_from_file_location("measurement_reference", _DIR / "reference.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


@unittest.skipIf(PIL is None, "Pillow is not installed")
class MeasurementReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = _load()

    def run_guide(self, controls=None, event=None, user=None):
        ctx = types.SimpleNamespace(controls=controls or {}, event=event)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(self.R, "USER", Path(user or tmp)):
            return self.R.guide(None, ctx).k["windows"][0].a[2]

    def test_every_shipped_entry_is_complete(self):
        paths = [p for p in sorted((_DIR / "references").glob("*.md")) if not p.name.startswith("_")]
        self.assertGreater(len(paths), 0)
        titles = set()
        for path in paths:
            with self.subTest(entry=path.name):
                e = self.R.parse(path)
                self.assertNotEqual(e["title"], path.stem, "no '# title' line")
                self.assertNotIn(e["title"], titles, "title used twice")
                titles.add(e["title"])
                self.assertNotEqual(e["region"], "Other", "no Region")
                self.assertIsNotNone(e["image"], "no picture")
                self.assertIsInstance(self.R.picture(e), self.R.rp.Image, "picture missing")
                source = e["body"].split("## Source")[1]
                self.assertRegex(source, r"CC0|CC BY|Public domain", "picture licence not stated")
                self.assertLessEqual(len(e["title"]), 200)

    def test_search_ignores_case_and_accents_and_puts_title_matches_first(self):
        mk = lambda title, body: {"title": title, "region": "Foot", "text": self.R.fold(title + " " + body)}  # noqa: E731
        items = [mk("Calcaneal pitch", "see also Bohler"), mk("Böhler angle", "calcaneus"), mk("Cobb angle", "spine")]
        self.assertEqual([e["title"] for e in self.R.search(items, "BOHLER", "All")], ["Böhler angle", "Calcaneal pitch"])
        self.assertEqual([e["title"] for e in self.R.search(items, "angle calc", "All")], ["Böhler angle"])
        self.assertEqual(self.R.search(items, "", "Spine"), [])

    def test_markdown_becomes_tables_and_labels(self):
        blocks = self.R.text_blocks("Intro **bold**\n- item\n\n| A | B |\n|---|---|\n| 1 |\n\n\n")
        self.assertEqual(blocks[0].a[0], "Intro bold\n• item")
        self.assertEqual(blocks[1].a[0], [["A", "B"], ["1", ""]])
        self.assertEqual(len(blocks), 2)

    def test_user_entry_replaces_shipped_one_and_template_is_copied(self):
        shipped = next(p for p in sorted((_DIR / "references").glob("*.md")) if not p.name.startswith("_"))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / shipped.name).write_text("# Mine zzzunique\nRegion: Test\n\nHello\n", encoding="utf-8")
            blocks = self.run_guide({"query": "zzzunique"}, "query", user=tmp)
            self.assertTrue((Path(tmp) / "_template.md").is_file())
        choice = next(b for b in blocks if isinstance(b, self.R.rp.Choice))
        self.assertEqual(choice.a[2], ["Mine zzzunique"])

    def test_pick_stays_until_a_new_search(self):
        titles = next(b for b in self.run_guide() if isinstance(b, self.R.rp.Choice)).a[2]
        last = titles[-1]
        picked = lambda blocks: next(b for b in blocks if isinstance(b, self.R.rp.Choice)).a[3]  # noqa: E731
        self.assertEqual(picked(self.run_guide({"entry": last}, "entry")), last)
        self.assertEqual(picked(self.run_guide({"entry": last, "query": ""}, "query")), titles[0])

    def test_no_match_says_so(self):
        blocks = self.run_guide({"query": "qqqqnothing"}, "query")
        self.assertFalse(any(isinstance(b, self.R.rp.Choice) and b.a[0] == "entry" for b in blocks))


if __name__ == "__main__":
    unittest.main()

"""Tests for tools/marketplace.py and tools/validate_plugins.py. Standard library only.

Run: ``python -m unittest discover -s tools -v``
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import marketplace  # noqa: E402
import validate_plugins  # noqa: E402

VECTORS = json.loads((Path(__file__).resolve().parent / "semver_vectors.json").read_text(encoding="utf-8"))


class SemverVectors(unittest.TestCase):
    def test_ascending_is_a_total_order(self):
        versions = VECTORS["ascending"]
        for i, a in enumerate(versions):
            for j, b in enumerate(versions):
                ka, kb = marketplace.version_key(a), marketplace.version_key(b)
                self.assertEqual((ka > kb) - (ka < kb), (i > j) - (i < j), f"{a} vs {b}")

    def test_equal_ignores_build_metadata(self):
        for a, b in VECTORS["equal"]:
            self.assertEqual(marketplace.version_key(a), marketplace.version_key(b), f"{a} == {b}")

    def test_invalid_is_rejected(self):
        for v in VECTORS["invalid"]:
            with self.assertRaises(ValueError, msg=repr(v)):
                marketplace.version_key(v)
            self.assertIsNone(validate_plugins.SEMVER.match(v), repr(v))

    def test_validator_accepts_every_valid_vector(self):
        for v in VECTORS["ascending"] + [x for pair in VECTORS["equal"] for x in pair]:
            self.assertTrue(validate_plugins.SEMVER.match(v), v)


class RequirementLint(unittest.TestCase):
    OK = [
        "numpy",
        "numpy>=1.26",
        "torch>=2.4,<3",
        "monai >= 1.3",
        "requests[socks]==2.32.3",
        "pkg~=1.4.2",
        "pkg==1.*",
        "pkg>=1.0; python_version < '3.12'",
        "Dynamic_Network.Architectures>=0.4",
        "pyradiomics @ git+https://github.com/AIM-Harvard/pyradiomics@67d1f268c67c2caffdbe043362f3f7333472af0f",
    ]
    BAD = [
        "-r other.txt",
        "-e .",
        "-e git+https://github.com/x/y.git#egg=y",
        "--index-url https://example.com/simple",
        "--extra-index-url https://example.com/simple",
        "--find-links ./wheels",
        "-f ./wheels",
        "--trusted-host example.com",
        "https://example.com/pkg.tar.gz",
        "git+https://github.com/x/y.git",
        "pkg @ https://example.com/pkg.whl",
        "pkg @ git+https://github.com/x/y@v1.0",
        "pkg @ git+https://github.com/x/y@main",
        "pkg @ git+https://github.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0",
        "pkg @ git+https://github.com/x/y",
        "pkg @ git+https://gitlab.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0f",
        "pkg @ git+http://github.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0f",
        "pkg @ git+ssh://git@github.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0f",
        "pkg @ git+https://github.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0f#subdirectory=z",
        "pkg @ git+https://github.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0f --hash=sha256:abc",
        "pkg @ git+https://github.com/x/y/z@67d1f268c67c2caffdbe043362f3f7333472af0f",
        "pkg @ git+https://user:token@github.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0f",
        "pkg[extra] @ git+https://github.com/x/y@67d1f268c67c2caffdbe043362f3f7333472af0f",
        "pkg@https://example.com/pkg.whl",
        "pkg==1.0@https://example.com",
        "./local",
        "../local",
        "/abs/path/pkg",
        "~/pkg",
        "C:\\pkgs\\pkg",
        "C:/pkgs/pkg",
        "wheels\\pkg",
        "pkg-1.0-py3-none-any.whl",
        "pkg.zip",
        "pkg>=1.0 --hash=sha256:abc",
        "pkg>=",
    ]

    def test_plain_requirements_pass(self):
        for line in self.OK:
            self.assertIsNone(validate_plugins.requirement_error(line), line)

    def test_unsafe_requirements_fail(self):
        for line in self.BAD:
            self.assertIsNotNone(validate_plugins.requirement_error(line), line)

    def test_reasons_are_specific(self):
        self.assertIn("option", validate_plugins.requirement_error("--extra-index-url https://x"))
        self.assertIn("URL", validate_plugins.requirement_error("pkg @ https://x/y.whl"))
        self.assertIn("path", validate_plugins.requirement_error("./local"))

    def test_check_requirements_reports_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "org.radspider.demo"
            plugin.mkdir()
            (plugin / "requirements.txt").write_text(
                "# c\nnumpy>=1\n--extra-index-url https://x/simple\n", encoding="utf-8"
            )
            errors: list[str] = []
            validate_plugins.check_requirements(plugin, {"requirements": "requirements.txt"}, errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("requirements.txt:3", errors[0])

    def test_real_requirements_pass(self):
        for req in marketplace.ROOT.glob("org.radspider.*/requirements.txt"):
            for line in req.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    self.assertIsNone(validate_plugins.requirement_error(line), f"{req}: {line}")


class IndexExtras(unittest.TestCase):
    def test_second_volume(self):
        self.assertTrue(marketplace.has_second_volume({"tool": [{"name": "a"}, {"name": "b", "second_volume": True}]}))
        self.assertFalse(marketplace.has_second_volume({"tool": [{"name": "a"}], "segmentation": []}))

    def test_extra_must_be_non_empty_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extra.toml"
            path.write_text('"org.radspider.x" = 5\n', encoding="utf-8")
            with self.assertRaises(SystemExit):
                marketplace.load_extra(path)
            path.write_text('"org.radspider.x" = "  "\n', encoding="utf-8")
            with self.assertRaises(SystemExit):
                marketplace.load_extra(path)

    def test_extra_with_unknown_id_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "marketplace").mkdir()
            (root / "marketplace" / "extra.toml").write_text('"org.radspider.ghost" = "x"\n', encoding="utf-8")
            with self.assertRaises(SystemExit):
                marketplace.build_index(root)

    def test_real_index_carries_the_extras(self):
        index = json.loads(marketplace.INDEX.read_text(encoding="utf-8"))
        extra = marketplace.load_extra()
        self.assertEqual(index["schema"], 1)
        for p in index["plugins"]:
            self.assertIsInstance(p["second_volume"], bool)
            self.assertEqual(p.get("first_run_download"), extra.get(p["id"]))


if __name__ == "__main__":
    unittest.main()

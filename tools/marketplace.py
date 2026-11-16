#!/usr/bin/env python3
"""Marketplace index and release packages for the plugins. Standard library only, Python >= 3.11.

Each plugin is versioned by ``version`` (semver) in its ``plugin.toml``. A package is the plugin folder zipped
deterministically (stored, sorted, fixed timestamps, ``<id>/`` at the top level), so its SHA-256 depends only on the
files. ``marketplace/index.json`` lists every plugin with its version, package URL and SHA-256.

Commands::

    marketplace.py update                  rewrite marketplace/index.json from the tree
    marketplace.py check [--base FILE]     fail if the index is stale; with --base, also enforce the version rules
    marketplace.py build OUTDIR            write <id>-<version>.zip for every plugin (what a release uploads)
    marketplace.py compare A B             print how index A's versions compare to index B's (update / same / downgrade)

Version rules (``check --base OLD_INDEX``): a plugin whose package changed must have a strictly greater version
than in OLD_INDEX; a version never goes down; a version never changes without a package change.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "marketplace" / "index.json"
EXTRA = ROOT / "marketplace" / "extra.toml"
REPO_URL = "https://github.com/rad-medica/radspider-plugins"
SCHEMA = 1
EXCLUDED_DIRS = {"__pycache__", ".venv", ".venvs", ".pytest_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
# The official regular expression of semver.org (2.0.0), so that every identifier rule is enforced.
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?\Z"
)


def version_key(version: str) -> tuple:
    """Sort key following semver 2.0 precedence (build metadata ignored, pre-release < release)."""
    m = SEMVER.match(version)
    if not m:
        raise ValueError(f"not a semver version: {version!r}")
    major, minor, patch, pre = int(m[1]), int(m[2]), int(m[3]), m[4]
    if pre is None:
        return (major, minor, patch, 1, ())
    ids = tuple((0, int(i), "") if i.isdigit() else (1, 0, i) for i in pre.split("."))
    return (major, minor, patch, 0, ids)


def package_files(plugin: Path) -> list[Path]:
    # Sorted by the POSIX path, not by `Path`: a WindowsPath compares with `\` and case-folded, so the same tree
    # zipped on Windows and on Linux would order its entries differently and get another SHA-256.
    return sorted(
        (
            p
            for p in plugin.rglob("*")
            if p.is_file()
            and not (set(p.relative_to(plugin).parts[:-1]) & EXCLUDED_DIRS)
            and p.suffix not in EXCLUDED_SUFFIXES
        ),
        key=lambda p: p.relative_to(plugin).as_posix(),
    )


def make_package(plugin: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for f in package_files(plugin):
            info = zipfile.ZipInfo(f"{plugin.name}/{f.relative_to(plugin).as_posix()}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            # ZipInfo records the OS that made it (0 on Windows, 3 elsewhere): pin it, so a package built on
            # Windows has the same bytes, and the same SHA-256, as the one the Linux release job builds.
            info.create_system = 3
            z.writestr(info, f.read_bytes())
    return buf.getvalue()


def plugin_dirs(root: Path = ROOT) -> list[Path]:
    return sorted(p for p in root.glob("org.radspider.*") if (p / "plugin.toml").is_file())


def load_extra(path: Path = EXTRA) -> dict[str, str]:
    """``marketplace/extra.toml``: plugin id -> text for ``first_run_download``. Absent file = no extras."""
    if not path.is_file():
        return {}
    extra = tomllib.loads(path.read_text(encoding="utf-8"))
    for pid, text in extra.items():
        if not isinstance(text, str) or not text.strip():
            raise SystemExit(f"{path.name}: {pid!r} must map to a non-empty string")
    return extra


def index_icon(manifest: dict) -> str | None:
    """The plugin's `icon` when it is a Phosphor name: the index carries no pictures (nothing is downloaded before
    install), so a PNG icon (a path ending in `.png`) is left out and the client shows its default."""
    icon = manifest.get("icon")
    if isinstance(icon, str) and icon and not icon.lower().endswith(".png"):
        return icon
    return None


def has_second_volume(manifest: dict) -> bool:
    return any(e.get("second_volume") is True for k in ("synth_node", "segmentation", "tool") for e in manifest.get(k, []))


def describe(plugin: Path, extra: dict[str, str] | None = None) -> dict:
    manifest = tomllib.loads((plugin / "plugin.toml").read_text(encoding="utf-8"))
    if manifest.get("id") != plugin.name:
        raise SystemExit(f"{plugin.name}: id {manifest.get('id')!r} differs from the folder name")
    version = str(manifest["version"])
    version_key(version)
    package = make_package(plugin)
    req = manifest.get("requirements")
    requirements = (
        [ln.strip() for ln in (plugin / req).read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if req
        else []
    )
    tag = f"{plugin.name}-v{version}"
    described = {
        "id": plugin.name,
        "name": manifest["name"],
        "version": version,
        "api": manifest["api"],
        "description": manifest["description"],
        "entries": {k: len(manifest.get(k, [])) for k in ("synth_node", "segmentation", "tool")},
        "requirements": requirements,
        "package": {
            "file": f"{plugin.name}-{version}.zip",
            "url": f"{REPO_URL}/releases/download/{tag}/{plugin.name}-{version}.zip",
            "sha256": hashlib.sha256(package).hexdigest(),
            "size": len(package),
        },
        "tag": tag,
        "second_volume": has_second_volume(manifest),
    }
    icon = index_icon(manifest)
    if icon:
        described["icon"] = icon
    first_run = (extra or {}).get(plugin.name)
    if first_run:
        described["first_run_download"] = first_run
    return described


def build_index(root: Path = ROOT) -> dict:
    plugins = plugin_dirs(root)
    extra = load_extra(root / "marketplace" / "extra.toml")
    unknown = sorted(extra.keys() - {p.name for p in plugins})
    if unknown:
        raise SystemExit(f"extra.toml: unknown plugin id(s): {', '.join(unknown)}")
    return {"schema": SCHEMA, "repository": REPO_URL, "plugins": [describe(p, extra) for p in plugins]}


def render(index: dict) -> str:
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def by_id(index: dict) -> dict[str, dict]:
    return {p["id"]: p for p in index["plugins"]}


def cmd_update(_: argparse.Namespace) -> int:
    INDEX.parent.mkdir(exist_ok=True)
    INDEX.write_text(render(build_index()), encoding="utf-8", newline="\n")
    print(f"wrote {INDEX.relative_to(ROOT)}")
    return 0


def version_errors(new: dict, old: dict) -> list[str]:
    errors = []
    old_by = by_id(old)
    for pid, n in by_id(new).items():
        o = old_by.get(pid)
        if o is None:
            continue
        changed = n["package"]["sha256"] != o["package"]["sha256"]
        kn, ko = version_key(n["version"]), version_key(o["version"])
        if kn < ko:
            errors.append(f"{pid}: version went down {o['version']} -> {n['version']}")
        elif changed and kn == ko:
            errors.append(f"{pid}: files changed but version is still {n['version']}: bump it in plugin.toml")
        elif not changed and kn > ko:
            errors.append(f"{pid}: version {o['version']} -> {n['version']} without any file change")
    for pid in old_by.keys() - by_id(new).keys():
        errors.append(f"{pid}: removed from the repository (publish a final version or keep it)")
    return errors


def cmd_check(args: argparse.Namespace) -> int:
    errors = []
    fresh = build_index()
    if not INDEX.is_file() or INDEX.read_text(encoding="utf-8") != render(fresh):
        errors.append("marketplace/index.json is stale: run `python tools/marketplace.py update` and commit it")
    if args.base:
        base = Path(args.base)
        if base.is_file() and base.stat().st_size:
            errors += version_errors(fresh, json.loads(base.read_text(encoding="utf-8")))
        else:
            print("no base index: version rules skipped (first publication)")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    print(f"{len(fresh['plugins'])} plugins, {len(errors)} errors")
    return 1 if errors else 0


def cmd_build(args: argparse.Namespace) -> int:
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    for p in plugin_dirs():
        d = describe(p)
        (out / d["package"]["file"]).write_bytes(make_package(p))
        print(d["package"]["file"], d["package"]["sha256"])
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    a, b = (json.loads(Path(x).read_text(encoding="utf-8")) for x in (args.a, args.b))
    b_by = by_id(b)
    for pid, p in sorted(by_id(a).items()):
        o = b_by.get(pid)
        if o is None:
            print(f"{pid}: new ({p['version']})")
            continue
        ka, kb = version_key(p["version"]), version_key(o["version"])
        state = "update" if ka > kb else "downgrade" if ka < kb else "same"
        print(f"{pid}: {o['version']} -> {p['version']} [{state}]")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("update").set_defaults(fn=cmd_update)
    c = sub.add_parser("check")
    c.add_argument("--base", help="index of the base branch, for the version rules")
    c.set_defaults(fn=cmd_check)
    b = sub.add_parser("build")
    b.add_argument("outdir")
    b.set_defaults(fn=cmd_build)
    k = sub.add_parser("compare")
    k.add_argument("a")
    k.add_argument("b")
    k.set_defaults(fn=cmd_compare)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

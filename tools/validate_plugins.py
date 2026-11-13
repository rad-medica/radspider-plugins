#!/usr/bin/env python3
"""Static validation of every plugin in the repository. Standard library only, Python >= 3.11.

Checks, per ``org.radspider.*`` folder:

* ``plugin.toml`` parses, folder name equals ``id``, ``version`` is semver, ``api`` is 1-3;
* the module (``module`` key, default ``plugin``) exists and compiles;
* ``requirements`` points at an existing file, and every requirement line is a bounded or named package;
* every ``[[synth_node]]`` / ``[[segmentation]]`` / ``[[tool]]`` has a unique ``name`` and a ``label``, and the
  module registers exactly the same names with ``@rp.<kind>("name")``;
* parameter ``name`` is unique per entry and ``min <= default <= max`` when bounds are given;
* ``second_volume`` is only used with ``api >= 3``;
* the plugin has a page in ``docs/plugins/`` (or none required for ``examples`` / ``numpy-demo`` / ``testkit``,
  which are documented in the README) and is listed in the README table.

Exit status 0 when clean, 1 otherwise. Usage: ``python tools/validate_plugins.py [repo_root]``.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

KINDS = {"synth_node": "synth_node", "segmentation": "segmentation", "tool": "tool"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
REQUIREMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?\s*(?:(?:>=|==|~=|<=|<|>|!=)\s*[^\s#;]+(?:\s*,\s*(?:>=|<=|<|>|!=)\s*[^\s#;]+)*)?\s*(?:;.*)?$")
DOC_OPTIONAL = {"examples", "numpy-demo", "testkit"}


def registered_entries(module: Path, errors: list[str]) -> dict[str, set[str]]:
    """Names registered with ``@rp.<kind>("name")`` in ``module``, by kind."""
    found: dict[str, set[str]] = {k: set() for k in KINDS}
    try:
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    except SyntaxError as exc:
        errors.append(f"{module}: syntax error: {exc}")
        return found
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr in KINDS and dec.args and isinstance(dec.args[0], ast.Constant):
                found[dec.func.attr].add(str(dec.args[0].value))
    return found


def check_params(where: str, entry: dict, errors: list[str]) -> None:
    seen: set[str] = set()
    for p in entry.get("params", []):
        name = p.get("name")
        if not name:
            errors.append(f"{where}: parameter without name")
            continue
        if name in seen:
            errors.append(f"{where}: duplicate parameter {name!r}")
        seen.add(name)
        if "default" not in p:
            errors.append(f"{where}: parameter {name!r} has no default")
            continue
        lo, hi, d = p.get("min"), p.get("max"), p["default"]
        if lo is not None and hi is not None and lo > hi:
            errors.append(f"{where}: parameter {name!r} has min > max")
        if lo is not None and d < lo or hi is not None and d > hi:
            errors.append(f"{where}: parameter {name!r} default {d} outside [{lo}, {hi}]")


def check_requirements(plugin: Path, manifest: dict, errors: list[str]) -> None:
    req = manifest.get("requirements")
    if req is None:
        return
    path = plugin / req
    if not path.is_file():
        errors.append(f"{plugin.name}: requirements file {req!r} missing")
        return
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if line and not line.startswith("#") and not REQUIREMENT.match(line):
            errors.append(f"{path.name}:{n}: unparsable requirement {line!r}")


def check_plugin(root: Path, plugin: Path, readme: str) -> list[str]:
    errors: list[str] = []
    short = plugin.name.removeprefix("org.radspider.")
    manifest_path = plugin / "plugin.toml"
    if not manifest_path.is_file():
        return [f"{plugin.name}: plugin.toml missing"]
    try:
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"{plugin.name}/plugin.toml: {exc}"]

    if manifest.get("id") != plugin.name:
        errors.append(f"{plugin.name}: id {manifest.get('id')!r} differs from the folder name")
    for key in ("name", "version", "api", "description"):
        if key not in manifest:
            errors.append(f"{plugin.name}: missing {key!r}")
    if "version" in manifest and not SEMVER.match(str(manifest["version"])):
        errors.append(f"{plugin.name}: version {manifest['version']!r} is not semver")
    api = manifest.get("api")
    if api not in (1, 2, 3):
        errors.append(f"{plugin.name}: api must be 1, 2 or 3, got {api!r}")

    module = plugin / f"{manifest.get('module', 'plugin')}.py"
    if not module.is_file():
        errors.append(f"{plugin.name}: module {module.name} missing")
        registered = {k: set() for k in KINDS}
    else:
        registered = registered_entries(module, errors)

    check_requirements(plugin, manifest, errors)

    declared: dict[str, set[str]] = {k: set() for k in KINDS}
    for kind in KINDS:
        for entry in manifest.get(kind, []):
            name = entry.get("name")
            where = f"{plugin.name}: {kind} {name!r}"
            if not name:
                errors.append(f"{plugin.name}: {kind} without name")
                continue
            if name in declared[kind]:
                errors.append(f"{where}: declared twice")
            declared[kind].add(name)
            if not entry.get("label"):
                errors.append(f"{where}: no label")
            if entry.get("second_volume") and isinstance(api, int) and api < 3:
                errors.append(f"{where}: second_volume needs api >= 3")
            check_params(where, entry, errors)
        for name in sorted(declared[kind] - registered[kind]):
            errors.append(f"{plugin.name}: {kind} {name!r} is in plugin.toml but not registered in the module")
        for name in sorted(registered[kind] - declared[kind]):
            errors.append(f"{plugin.name}: {kind} {name!r} is registered in the module but not in plugin.toml")
    if not any(declared.values()):
        errors.append(f"{plugin.name}: declares no entries")

    if f"`{plugin.name}`" not in readme:
        errors.append(f"{plugin.name}: not listed in README.md")
    if short not in DOC_OPTIONAL and not (root / "docs" / "plugins" / f"{short}.md").is_file():
        errors.append(f"{plugin.name}: docs/plugins/{short}.md missing")
    return errors


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else Path(__file__).resolve().parent.parent).resolve()
    plugins = sorted(p for p in root.glob("org.radspider.*") if p.is_dir())
    if not plugins:
        print(f"no plugins under {root}", file=sys.stderr)
        return 1
    readme = (root / "README.md").read_text(encoding="utf-8")
    errors = [e for p in plugins for e in check_plugin(root, p, readme)]
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    print(f"{len(plugins)} plugins checked, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

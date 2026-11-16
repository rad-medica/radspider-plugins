"""Write lang/template.toml of org.radspider.series-identifier: the SDK's template plus the table ids.

    python tools/series_identifier_template.py [<radspider checkout>/assets/python]

The SDK's generator (`python -m radspider_plugin template <plugin dir>`) lists the manifest texts and the literal
first arguments of rp.tr. The plugin's result ids and explanation paragraphs come from the tables of
seriesid_tables.py, so the generator cannot see them; this script runs it and appends them, with empty values, so a
translator who copies the template gets every text the plugin shows. tools/test_series_identifier.py checks it ran.
"""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "org.radspider.series-identifier"
TEMPLATE = PLUGIN / "lang" / "template.toml"
HEAD = ("\n# seriesid_tables.py: results and explanations. Not literal rp.tr calls, so the generator cannot list them;"
        "\n# appended by tools/series_identifier_template.py, which also runs the generator.\n")


def table_ids():
    """The ids seriesid.py passes to rp.tr from the tables, in a stable order: results, then explanation paragraphs."""
    sys.dont_write_bytecode = True
    if str(PLUGIN) not in sys.path:
        sys.path.insert(0, str(PLUGIN))
    import seriesid_tables as T

    results = T.all_result_ids() | T.all_explain_ids()
    ordered = [k for k in T.EXPLAIN if k in results] + sorted(results - set(T.EXPLAIN))
    return ordered + [v for v in T.EXPLAIN.values() if v not in results]


def quote(s):
    """A TOML basic string, as the SDK's generator writes keys."""
    out = []
    for c in s:
        if c in '"\\':
            out.append("\\" + c)
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            out.append("\\u%04X" % ord(c))
        else:
            out.append(c)
    return '"%s"' % "".join(out)


def main(argv):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if argv:
        env["PYTHONPATH"] = os.pathsep.join(p for p in (argv[0], env.get("PYTHONPATH")) if p)
    subprocess.run([sys.executable, "-m", "radspider_plugin", "template", str(PLUGIN)], env=env, check=True)
    existing = set(tomllib.loads(TEMPLATE.read_text(encoding="utf-8"))["strings"])
    lines = ['%s = ""' % quote(i) for i in table_ids() if i not in existing]
    with open(TEMPLATE, "a", encoding="utf-8", newline="\n") as f:
        f.write(HEAD + "".join(line + "\n" for line in lines))
    print("appended %d table ids to %s" % (len(lines), TEMPLATE))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

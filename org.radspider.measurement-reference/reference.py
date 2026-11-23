"""Measurement reference: a searchable guide of radiological measurements.

Every entry is one Markdown file: `references/*.md` in this folder (shipped) and the user's own folder
(`~/radspider-references`, or `RADSPIDER_REFERENCE_DIR`), where a file with the same name replaces a shipped one and
survives plugin updates. The format is in `references/_template.md`. The host has no Markdown widget: headings become
sections, pipe tables become tables, the first picture is decoded with Pillow and the rest is shown as text."""

import os
import re
import unicodedata
from pathlib import Path

from PIL import Image

import radspider_plugin as rp

BUILTIN = Path(__file__).resolve().parent / "references"
USER = Path(os.environ.get("RADSPIDER_REFERENCE_DIR") or Path.home() / "radspider-references")
ALL = "All"
MAX_SIDE = 1000  # pixels: the window scales pictures down to its width anyway
MAX_OPTIONS = 256  # the host's limit of a choice

META = re.compile(r"(Region|Keywords):\s*(.*)", re.I)
PICTURE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def fold(text):
    """Lower case without accents, so `bohler` finds `Böhler`."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def parse(path):
    entry = {"path": path, "title": path.stem, "region": "Other", "keywords": "", "image": None, "caption": ""}
    body, titled = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        meta, pic = META.fullmatch(line.strip()), PICTURE.fullmatch(line.strip())
        if line.startswith("# ") and not titled:
            entry["title"], titled = line[2:].strip(), True
        elif meta:
            entry[meta[1].lower()] = meta[2].strip()
        elif pic and entry["image"] is None:
            entry["caption"], entry["image"] = pic[1], pic[2]
        else:
            body.append(line)
    entry["body"] = "\n".join(body)
    entry["text"] = fold(" ".join((entry["title"], entry["region"], entry["keywords"], entry["body"])))
    return entry


def entries():
    """Shipped entries, then the user's: the same file name replaces. `_*.md` (the template) is not an entry."""
    found = {}
    for folder in (BUILTIN, USER):
        for path in sorted(folder.glob("*.md")):
            if not path.name.startswith("_"):
                found[path.name] = parse(path)
    return sorted(found.values(), key=lambda e: fold(e["title"]))


def prepare_user_folder():
    """Make the user's folder with the template in it. A home that cannot be written only means no user entries."""
    try:
        USER.mkdir(parents=True, exist_ok=True)
        template = USER / "_template.md"
        if not template.exists():
            template.write_bytes((BUILTIN / "_template.md").read_bytes())
    except OSError as e:
        print("measurement-reference: cannot prepare %s: %s" % (USER, e))


def search(items, query, region):
    words = fold(query).split()
    hits = [e for e in items if region in (ALL, e["region"]) and all(w in e["text"] for w in words)]
    # Entries whose title holds every word come first; the sort is stable, so each group stays alphabetical.
    hits.sort(key=lambda e: not all(w in fold(e["title"]) for w in words))
    return hits


def text_blocks(text):
    """Paragraphs separated by blank lines: all lines starting with `|` make a table, anything else a label."""
    out = []
    for chunk in re.split(r"\n\s*\n", text):
        lines = [re.sub(r"\*\*|`", "", line.rstrip()) for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.lstrip().startswith("|") for line in lines):
            rows = [[c.strip() for c in line.strip().strip("|").split("|")]
                    for line in lines if not re.fullmatch(r"[\s|:-]+", line)]
            width = max(len(r) for r in rows)
            out.append(rp.Table([r + [""] * (width - len(r)) for r in rows], csv=False))
        else:
            out.append(rp.Label("\n".join(re.sub(r"^\s*[-*] ", "• ", line) for line in lines)))
    return out


def picture(entry):
    path = entry["path"].parent / entry["image"]
    if not path.is_file():
        return rp.Label("Picture not found: %s" % path, weak=True)
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        return rp.Image(entry["caption"], im.width, im.height, im.tobytes())


def entry_blocks(entry):
    """`## Heading` starts a collapsible section; what precedes the first one sits above the picture."""
    parts = re.split(r"^## +(.+)$", entry["body"], flags=re.M)
    out = text_blocks(parts[0])
    if entry["image"]:
        out.append(picture(entry))
    for title, text in zip(parts[1::2], parts[2::2]):
        out.append(rp.Section(title.strip()[:200], text_blocks(text)))
    out.append(rp.Label("File: %s" % entry["path"], weak=True))
    return out


@rp.tool("guide")
def guide(volume, ctx):
    prepare_user_folder()
    items = entries()
    c = ctx.controls
    query, region = str(c.get("query", "")), c.get("region", ALL)
    regions = [ALL] + sorted({e["region"] for e in items})
    if region not in regions:
        region = ALL
    hits = search(items, query, region)[:MAX_OPTIONS]
    titles = [e["title"][:200] for e in hits]
    # A new search shows its best match; otherwise the entry the user picked stays.
    picked = c.get("entry") if ctx.event not in ("query", "region") and c.get("entry") in titles else None
    blocks = [
        rp.Row([rp.TextField("query", "Search", query, max_length=100), rp.Choice("region", "Region", regions, region)]),
    ]
    if hits:
        entry = hits[titles.index(picked)] if picked else hits[0]
        blocks += [
            rp.Choice("entry", "Measurement (%d)" % len(hits), titles, entry["title"][:200]),
            rp.Separator(),
            rp.Label("%s · %s" % (entry["title"], entry["region"])),
            *entry_blocks(entry),
        ]
    else:
        blocks.append(rp.Label("No measurement matches. Try fewer words or region All."))
    blocks += [rp.Separator(), rp.Label("Your own entries (Markdown, see _template.md): %s" % USER, weak=True)]
    return rp.Result(windows=[rp.Window("main", "Measurement reference", blocks)])

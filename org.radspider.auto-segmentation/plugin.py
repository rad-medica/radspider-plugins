"""Automatic CT segmentation: one entry whose model is a parameter, and a window that manages the downloaded weights.

The models keep their pipelines in their own modules, as they were in the plugins this one replaces:

* ``autoseg_totalseg``: TotalSegmentator v2, 117 structures, 3 mm, ONNX Runtime (was ``org.radspider.totalsegmentator``);
* ``autoseg_monai``: MONAI ``wholeBody_ct_segmentation``, 104 structures, 3 or 1.5 mm (was
  ``org.radspider.monai-wholebody``);
* ``autoseg_cads``: CADS, 167 structures in nine task groups, 1.5 mm (was ``org.radspider.cads``).

This file only picks the model and lists, downloads and deletes the cached weights.
"""

import os
import shutil

import radspider_plugin as rp

import autoseg_cads as cads
import autoseg_monai as monai
import autoseg_totalseg as totalseg

# The `model` choice of plugin.toml, option text -> model. The texts must be the manifest's, character for character.
TOTALSEG = "TotalSegmentator: 117 structures (3 mm)"
MONAI_3 = "MONAI whole body: 104 structures (3 mm)"
MONAI_15 = "MONAI whole body: 104 structures (1.5 mm)"
CADS_GROUPS = {
    551: "core organs", 552: "spine", 553: "heart & vessels", 554: "trunk muscles", 555: "ribs",
    556: "RT risk organs", 557: "brain tissues", 558: "head-neck organs", 559: "body regions",
}
CADS_TASKS = {"CADS %d: %s (%d structures)" % (t, g, len(cads.NAMES[t])): t for t, g in CADS_GROUPS.items()}
MODELS = [TOTALSEG, MONAI_3, MONAI_15, *CADS_TASKS]
DEFAULT_STEP = 0.5  # nnU-Net's tile_step_size; MONAI's overlap 0.25 is a step of 0.75


# ---- segmentation -------------------------------------------------------------------------------------------------


@rp.segmentation("segment")
def segment(volume, ctx):
    model = ctx.params["model"]
    step = float(ctx.params["window_step"])
    step = min(max(step, 0.25), 1.0) if step > 0 else None  # 0 = the model's own default
    if model == TOTALSEG:
        return totalseg.segment(volume, ctx, step or DEFAULT_STEP)
    if model in (MONAI_3, MONAI_15):
        return monai.segment(volume, ctx, model == MONAI_15, 1.0 - step if step else 0.25)
    if model in CADS_TASKS:
        variant = "research" if ctx.params["cads_weights"].startswith("research") else "open"
        return cads.segment(volume, ctx, CADS_TASKS[model], variant, bool(ctx.params["cads_postprocess"]),
                            step or DEFAULT_STEP)
    raise ValueError("Unknown model %r" % model)


# ---- weights in the cache -----------------------------------------------------------------------------------------


class Weights:
    """One downloadable set of weights: where it lives, whether an environment variable replaces it, how to get it."""

    def __init__(self, label, model, licence, download, file, fetch, override=None):
        self.label, self.model, self.licence, self.download = label, model, licence, download
        self.file, self.fetch, self.override = file, fetch, override

    def external(self):
        """The environment variable that points to a file of the user's instead, when it is set."""
        return self.override if self.override and os.environ.get(self.override) else None

    def path(self):
        return self.file()

    def size(self):
        p = self.path()
        return os.path.getsize(p) if os.path.isfile(p) else 0


def catalog():
    out = [
        Weights("TotalSegmentator 3 mm", "TotalSegmentator v2, task 297", "Apache-2.0", "135 MB → 65 MB ONNX",
                totalseg.onnx_file, totalseg.model_path, "RADSPIDER_TOTALSEG_ONNX"),
    ]
    for highres, mm in ((False, "3 mm"), (True, "1.5 mm")):
        out.append(Weights("MONAI whole body " + mm, "MONAI wholeBody_ct_segmentation", "Apache-2.0", "71 MB",
                           lambda h=highres: monai.weights_file(h), lambda progress, h=highres: monai.weights_path(h),
                           "RADSPIDER_MONAI_WHOLEBODY_WEIGHTS"))
    for variant, (release, licence) in cads.VARIANTS.items():
        for task, group in CADS_GROUPS.items():
            out.append(Weights("CADS %d %s · %s" % (task, group, variant), release, licence, "760 MB → 410 MB",
                               lambda v=variant, t=task: cads.task_file(v, t),
                               lambda progress, v=variant, t=task: cads.ensure_task(v, t, progress)))
    return out


def cache_dirs():
    return [totalseg.cache_dir(), monai.cache_dir(), cads.cache_dir()]


def leftovers():
    """Files and folders an interrupted download or conversion leaves behind: the temporary folders of TotalSegmentator
    and CADS, ``*.part`` files, and Hugging Face's ``*.incomplete`` downloads."""
    found = []
    for top in cache_dirs():
        for root, dirs, files in os.walk(top):
            for d in list(dirs):
                if d.startswith("tmp"):
                    found.append(os.path.join(root, d))
                    dirs.remove(d)
            found += [os.path.join(root, f) for f in files if f.endswith((".part", ".incomplete"))]
    return found


def size_of(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024


def remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


def delete(w):
    """Removes one set of weights from the cache; returns the bytes freed."""
    freed = w.size()
    remove(w.path())
    if w.label.startswith("MONAI"):  # huggingface_hub's note of the download, so the next run fetches it again
        rel = os.path.relpath(w.path(), monai.cache_dir())
        for note in (".metadata", ".lock"):
            remove(os.path.join(monai.cache_dir(), ".cache", "huggingface", "download", rel + note))
    return freed


# ---- the window ---------------------------------------------------------------------------------------------------


@rp.tool("models")
def models(volume, ctx):
    weights = catalog()
    by_label = {w.label: w for w in weights}
    picked = ctx.controls.get("item")
    w = by_label.get(picked) or weights[0]
    note = None

    if ctx.event == "download":
        if w.external():
            note = rp.tr("{item} comes from {var}: nothing to download", item=w.label, var=w.external())
        elif w.size():
            note = rp.tr("{item} is already downloaded", item=w.label)
        else:
            ctx.progress(0.0, rp.tr("Downloading {item}", item=w.label))
            w.fetch(ctx.progress)
            note = rp.tr("{item} downloaded ({size})", item=w.label, size=human(w.size()))
    elif ctx.event == "delete":
        if w.external():
            note = rp.tr("{item} comes from {var}: it is not deleted", item=w.label, var=w.external())
        elif not w.size():
            note = rp.tr("{item} is not downloaded", item=w.label)
        else:
            note = rp.tr("{item} deleted: {size} freed", item=w.label, size=human(delete(w)))
    elif ctx.event == "clean":
        found = leftovers()
        freed = sum(size_of(p) for p in found)
        for p in found:
            remove(p)
        note = rp.trn(len(found), "{n} leftover removed: {size} freed", "{n} leftovers removed: {size} freed",
                      size=human(freed))

    rows = [[rp.tr("Weights"), rp.tr("Model"), rp.tr("Licence"), rp.tr("Download"), rp.tr("On disk"), rp.tr("Status")]]
    total = 0
    for x in weights:
        size = x.size()
        total += size
        if x.external():
            status = rp.tr("Your file ({var})", var=x.external())
        elif size:
            status = rp.tr("Ready")
        else:
            status = rp.tr("Not downloaded")
        rows.append([x.label, x.model, x.licence, x.download, human(size) if size else "", status])
    rest = leftovers()
    rest_size = sum(size_of(p) for p in rest)
    rows.append([rp.tr("Leftovers of interrupted downloads"), "", "", "", human(rest_size) if rest else "",
                 rp.trn(len(rest), "{n} item", "{n} items")])
    rows.append([rp.tr("Total"), "", "", "", human(total + rest_size), ""])

    blocks = [
        rp.Row([
            rp.Choice("item", rp.tr("Weights"), [x.label for x in weights], w.label),
            rp.Button("download", rp.tr("Download"), icon="download-simple",
                      help=rp.tr("Downloads, checks and converts the weights now instead of on the first run")),
            rp.Button("delete", rp.tr("Delete"), icon="trash",
                      help=rp.tr("Removes the weights from the cache; the next run downloads them again")),
            rp.Button("clean", rp.tr("Clean up"), icon="broom",
                      help=rp.tr("Removes what interrupted downloads left behind. Not while a segmentation is "
                                 "downloading")),
            rp.Button("refresh", rp.tr("Refresh"), icon="arrow-clockwise"),
        ]),
        rp.Table(rows),
        rp.Label(rp.tr("Cache: {dirs}", dirs="  ·  ".join(cache_dirs())), weak=True),
        rp.Label(rp.tr("CADS 557 and 558 with post-processing also need CADS 553 (and 558 sometimes 552) of the same "
                       "weights."), weak=True),
    ]
    if note is not None:
        blocks.insert(1, rp.Label(note))
    return rp.Result(windows=[rp.Window("main", rp.tr("Segmentation models"), blocks, icon="database")])

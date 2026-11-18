"""Automatic CT segmentation: one entry whose model is a parameter, and a window that manages the downloaded weights.

The models keep their pipelines in their own modules, as they were in the plugins this one replaces:

* ``autoseg_totalseg``: TotalSegmentator v2, 117 structures, 3 mm, ONNX Runtime (was ``org.radspider.totalsegmentator``);
* ``autoseg_monai``: MONAI ``wholeBody_ct_segmentation``, 104 structures, 3 or 1.5 mm (was
  ``org.radspider.monai-wholebody``);
* ``autoseg_cads``: CADS, 167 structures in nine task groups, 1.5 mm (was ``org.radspider.cads``).

This file only picks the model and lists, downloads and deletes the cached weights; ``autoseg_jobs`` runs the
downloads in the background.
"""

import os
import re
import shutil
import time
import webbrowser

import radspider_plugin as rp

import autoseg_cads as cads
import autoseg_jobs as jobs
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
    ensure_weights(model, ctx)
    if model == TOTALSEG:
        return totalseg.segment(volume, ctx, step or DEFAULT_STEP)
    if model in (MONAI_3, MONAI_15):
        return monai.segment(volume, ctx, model == MONAI_15, 1.0 - step if step else 0.25)
    if model in CADS_TASKS:
        variant = "research" if ctx.params["cads_weights"].startswith("research") else "open"
        return cads.segment(volume, ctx, CADS_TASKS[model], variant, bool(ctx.params["cads_postprocess"]),
                            step or DEFAULT_STEP)
    raise ValueError("Unknown model %r" % model)


def weights_for(model, params):
    """The labels of the weights a run of ``model`` needs (the CADS head tasks with post-processing need 553)."""
    if model == TOTALSEG:
        return ["TotalSegmentator 3 mm"]
    if model in (MONAI_3, MONAI_15):
        return ["MONAI whole body " + ("1.5 mm" if model == MONAI_15 else "3 mm")]
    variant = "research" if params["cads_weights"].startswith("research") else "open"
    task = CADS_TASKS[model]
    tasks = [553, task] if task in (557, 558) and bool(params["cads_postprocess"]) else [task]
    # shortcut: 558 sometimes also needs 552, which the CADS module then downloads in this run, outside the jobs.
    return ["CADS %d %s · %s" % (t, CADS_GROUPS[t], variant) for t in tasks]


def ensure_weights(model, ctx):
    """Downloads missing weights through the same background job as the window, so a run and the window never fetch
    the same file twice, and a cancelled run leaves its download going."""
    by_label = {w.label: w for w in catalog()}
    for label in weights_for(model, ctx.params):
        w = by_label[label]
        if w.external() or w.size():
            continue
        jobs.start(label)
        jobs.wait(label, ctx.progress, rp.tr("Downloading {item}", item=label))
        if not w.size():
            raise ValueError("The download of %s was stopped; start the run again or download it in Segmentation "
                             "models" % label)


# ---- weights in the cache -----------------------------------------------------------------------------------------


class Weights:
    """One downloadable set of weights: where it lives, whether an environment variable replaces it, how to get it."""

    def __init__(self, label, family, part, download, need, file, fetch, override=None, convert_at=1.0):
        self.label, self.family, self.part, self.download, self.need = label, family, part, download, need
        self.file, self.fetch, self.override = file, fetch, override
        # The progress value at which the download ends and the conversion starts (None: no progress reported).
        self.convert_at = convert_at

    def external(self):
        """The environment variable that points to a file of the user's instead, when it is set."""
        return self.override if self.override and os.environ.get(self.override) else None

    def path(self):
        return self.file()

    def size(self):
        p = self.path()
        return os.path.getsize(p) if os.path.isfile(p) else 0


MB = 1 << 20

# Window sections, in order: title, description, licence, web page. Descriptions from docs/plugins/auto-segmentation.md.
FAMILIES = {
    "totalseg": (rp.tr("TotalSegmentator v2"),
                 rp.tr("117 anatomical structures on CT at 3 mm (nnU-Net, task 297), run with ONNX Runtime on the CPU. "
                       "The checkpoint is converted to ONNX once, after its SHA-256 check."),
                 "Apache-2.0", "https://github.com/wasserth/TotalSegmentator"),
    "monai": (rp.tr("MONAI whole body"),
              rp.tr("SegResNet bundle of the MONAI Model Zoo: 104 structures on CT at 3 or 1.5 mm. CUDA is used when "
                    "PyTorch has it."),
              "Apache-2.0", "https://huggingface.co/MONAI/wholeBody_ct_segmentation"),
    "cads_open": (rp.tr("CADS · open weights"),
                  rp.tr("Nine nnU-Net networks, 167 structures at 1.5 mm. A GPU-class model: on the CPU about 20 s per "
                        "window and 9 GB of RAM. 557 and 558 with post-processing also need 553 (558 sometimes 552)."),
                  "CC BY-SA 4.0", "https://github.com/murong-xu/CADS"),
    "cads_research": (rp.tr("CADS · research weights"),
                      rp.tr("The same nine groups under the research licence: academic and non-commercial use only."),
                      "CC BY-NC-SA 4.0", "https://github.com/murong-xu/CADS"),
}


def catalog():
    out = [
        Weights("TotalSegmentator 3 mm", "totalseg", rp.tr("3 mm · 117 structures"), "65 MB", 200 * MB,
                totalseg.onnx_file, totalseg.model_path, "RADSPIDER_TOTALSEG_ONNX", convert_at=0.04),
    ]
    for highres, mm in ((False, "3 mm"), (True, "1.5 mm")):
        # shortcut: hf_hub_download reports no progress, so MONAI shows no percentage; read the .incomplete size if
        # users ask for one.
        out.append(Weights("MONAI whole body " + mm, "monai", rp.tr("{mm} · 104 structures", mm=mm), "71 MB", 80 * MB,
                           lambda h=highres: monai.weights_file(h), lambda progress, h=highres: monai.weights_path(h),
                           "RADSPIDER_MONAI_WHOLEBODY_WEIGHTS", convert_at=None))
    for variant in cads.VARIANTS:
        for task, group in CADS_GROUPS.items():
            out.append(Weights("CADS %d %s · %s" % (task, group, variant), "cads_" + variant,
                               rp.tr("{task} {group} ({n} structures)", task=task, group=group, n=len(cads.NAMES[task])),
                               "410 MB", 1200 * MB, lambda v=variant, t=task: cads.task_file(v, t),
                               lambda progress, v=variant, t=task: cads.ensure_task(v, t, progress), convert_at=0.8))
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


def free_space(path):
    while not os.path.isdir(path):
        path = os.path.dirname(path)
    return shutil.disk_usage(path).free


def status(w, job, confirm):
    """The state text of one row and its one action: (text, button or None)."""
    if w.external():
        return rp.tr("Your file ({var})", var=w.external()), None
    i = w.index
    if job and job["running"]:
        f = float(job.get("fraction") or 0.0)
        if w.convert_at is None:
            text = rp.tr("Downloading…")
        elif f >= 1.0:
            text = rp.tr("Converting (once)…")
        else:
            text = rp.tr("Downloading: {pct} %", pct=int(f * 100))
        return text, rp.Button("stop_%d" % i, rp.tr("Stop"), icon="stop",
                               help=rp.tr("Stops the download and removes what it wrote"))
    if job and job.get("error"):
        return rp.tr("Failed: {error}", error=job["error"]), rp.Button("dl_%d" % i, rp.tr("Retry"),
                                                                        icon="arrow-clockwise")
    size = w.size()
    if size and confirm:
        return rp.tr("{size} · ready", size=human(size)), rp.Button(
            "yes_%d" % i, rp.tr("Confirm delete"), icon="check",
            help=rp.tr("Removes the weights from the cache; the next run downloads them again"))
    if size:
        return rp.tr("{size} · ready", size=human(size)), rp.Button("del_%d" % i, rp.tr("Delete…"), icon="trash")
    return rp.tr("Not downloaded ({size})", size=w.download), rp.Button(
        "dl_%d" % i, rp.tr("Download"), icon="download-simple",
        help=rp.tr("Downloads, checks and converts the weights in the background; the window can be closed"))


def act(weights, event):
    """Carries out a button of the window; returns the note to show, or None."""
    if event in ("refresh", None):
        return None
    if event == "clean":
        if any((jobs.state(w.label) or {}).get("running") for w in weights):
            return rp.tr("Not while a download runs: its files would be removed")
        found = leftovers()
        freed = sum(size_of(p) for p in found)
        for p in found:
            remove(p)
        return rp.trn(len(found), "{n} leftover removed: {size} freed", "{n} leftovers removed: {size} freed",
                      size=human(freed))
    m = re.fullmatch(r"(dl|stop|del|yes|web)_(\w+)", event)
    if not m:
        return None
    what, arg = m.groups()
    if what == "web":
        url = FAMILIES[arg][3]
        if webbrowser.open(url):
            return rp.tr("Opened {url} in the browser", url=url)
        return rp.tr("No browser could be opened: {url}", url=url)
    w = weights[int(arg)]
    if what == "dl":
        if w.external() or w.size():
            return None
        if free_space(w.path()) < w.need:
            return rp.tr("Not enough free disk space for {item}: it needs {size}", item=w.label, size=human(w.need))
        jobs.start(w.label)
        return rp.tr("Downloading {item} in the background", item=w.label)
    if what == "stop":
        jobs.stop(w.label)
        return rp.tr("{item}: download stopped", item=w.label)
    if what == "del":
        return rp.tr("Press Confirm delete to remove {item}", item=w.label)
    if w.external():
        return rp.tr("{item} comes from {var}: it is not deleted", item=w.label, var=w.external())
    return rp.tr("{item} deleted: {size} freed", item=w.label, size=human(delete(w)))


def watch(weights, ctx):
    """While downloads run, shows their progress on the window's bar and returns once one of them ends, so the rows
    are drawn again. Any button press ends the wait (the host replaces this run); the downloads go on."""
    running = {w.label for w in weights if (jobs.state(w.label) or {}).get("running")}
    while running:
        states = [jobs.state(label) for label in running]
        if any(not s or not s["running"] for s in states):
            return
        ctx.progress(sum(float(s.get("fraction") or 0.0) for s in states) / len(states),
                     rp.trn(len(states), "{n} download running", "{n} downloads running"))
        time.sleep(jobs.POLL)


@rp.tool("models")
def models(volume, ctx):
    weights = catalog()
    for i, w in enumerate(weights):
        w.index = i
    note = act(weights, ctx.event)
    if "main" in ctx.windows and (ctx.event is None or ctx.event.startswith("dl_")):  # not before a first answer
        watch(weights, ctx)
    confirm = ctx.event[4:] if (ctx.event or "").startswith("del_") else None

    states = {w.label: jobs.state(w.label) for w in weights}
    running = sum(1 for s in states.values() if s and s["running"])
    ready = [w.size() for w in weights if w.size()]
    rest = [] if running else leftovers()
    summary = rp.tr("{d} downloading · {r} ready ({size}) · {free} free on disk", d=running, r=len(ready),
                    size=human(sum(ready)), free=human(free_space(cache_dirs()[0])))
    blocks = [rp.Row([rp.Label(summary), rp.Button("refresh", rp.tr("Refresh"), icon="arrow-clockwise")])]
    if note is not None:
        blocks.append(rp.Label(note))
    for family, (title, description, licence, url) in FAMILIES.items():
        inner = [
            rp.Label(description),
            rp.Row([rp.Label(rp.tr("Licence: {licence}", licence=licence), weak=True),
                    rp.Button("web_" + family, rp.tr("Website"), icon="globe", help=url)]),
            rp.Separator(),
        ]
        for w in weights:
            if w.family == family:
                text, button = status(w, states[w.label], confirm == str(w.index))
                inner.append(rp.Row([rp.Label(w.part), rp.Label(text, weak=True), *([button] if button else [])]))
        blocks.append(rp.Section(title, inner, open=family != "cads_research"))
    blocks.append(rp.Section(rp.tr("Storage"), [
        rp.Label(rp.tr("Cache: {dirs}", dirs="  ·  ".join(cache_dirs())), weak=True),
        rp.Row([rp.Label(rp.tr("Leftovers are counted when no download runs") if running else
                         rp.trn(len(rest), "{n} leftover of interrupted downloads ({size})",
                                "{n} leftovers of interrupted downloads ({size})",
                                size=human(sum(size_of(p) for p in rest))), weak=True),
                rp.Button("clean", rp.tr("Clean up"), icon="broom",
                          help=rp.tr("Removes what interrupted downloads left behind. Not while a download runs"))]),
        rp.Label(rp.tr("Downloads go on when this window closes and stop when radspider closes."), weak=True),
    ], open=False))
    return rp.Result(windows=[rp.Window("main", rp.tr("Segmentation models"), blocks, icon="database")])

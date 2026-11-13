"""SAM ViT-B on single slices (ONNX), after OHIF 3.10 / Cornerstone3D ``packages/ai``.

* ``prompt``: Probe = include marker, Text '-' = exclude marker (OHIF's marker tool), one slice at a time.
* ``propagate``: OHIF's Labelmap Assist: random points of the neighbouring slice's mask prompt the next slice.
* ``bidirectional``: OHIF's "bidirectional measurement for segments": largest slice, longest diameter, longest
  perpendicular chord. No model.

Models: Meta SAM ViT-B (Apache-2.0) exported to ONNX, the same files OHIF loads from Hugging Face ``schmuell/sam-b-fp16``.
Unlike OHIF (which squashes the slice to 1024 x 1024) the slice keeps its aspect ratio and is padded, as in Meta's own
pipeline; the decoder resizes the mask back to the slice.
"""

import math
import os
import random

import numpy as np

import radspider_plugin as rp

REPO = "schmuell/sam-b-fp16"
ENCODER, DECODER = "sam_vit_b_01ec64.encoder-fp16.onnx", "sam_vit_b_01ec64.decoder.onnx"
SIZE = 1024
MEAN = np.array([123.675, 116.28, 103.53], dtype=np.float32)
STD = np.array([58.395, 57.12, 57.375], dtype=np.float32)
NEGATIVE = ("-", "neg", "negative")
LIMIT_MM = 6.0  # how far a propagated mask may leave the neighbour's mask
POINTS = 5  # random points of the neighbour's mask, as OHIF's numRandomPoints


# ---- image and prompts ------------------------------------------------------------------------------------------


def resize_bilinear(img, h, w):
    """img (H, W, C) float -> (h, w, C), half-pixel centres, numpy only."""
    H, W = img.shape[:2]
    ys = np.clip((np.arange(h) + 0.5) * H / h - 0.5, 0, H - 1)
    xs = np.clip((np.arange(w) + 0.5) * W / w - 0.5, 0, W - 1)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, H - 1), np.minimum(x0 + 1, W - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    top = img[y0][:, x0] * (1 - fx) + img[y0][:, x1] * fx
    bot = img[y1][:, x0] * (1 - fx) + img[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


def model_input(sl, center, width):
    """Slice (rows, cols) -> (1, 3, 1024, 1024) float32: window to 8 bit, long side to 1024, SAM mean/std, zero pad."""
    lo, hi = center - width / 2.0, center + width / 2.0
    g = np.clip((np.nan_to_num(sl, nan=lo) - lo) / (hi - lo), 0.0, 1.0) * 255.0
    h, w = g.shape
    s = SIZE / max(h, w)
    nh, nw = max(1, int(round(h * s))), max(1, int(round(w * s)))
    rgb = resize_bilinear(np.repeat(g[:, :, None], 3, axis=2).astype(np.float32), nh, nw)
    rgb = (rgb - MEAN) / STD
    out = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    out[:nh, :nw] = rgb
    return np.ascontiguousarray(out.transpose(2, 0, 1)[None]), s


def prompts_by_slice(rois, dims):
    """{slice: ([(x, y)] include, [(x, y)] exclude)} from Probe / Text '-' measurements."""
    out = {}
    for r in rois:
        if r.kind == "probe":
            k = 0
        elif r.kind == "text" and r.text.strip().lower() in NEGATIVE:
            k = 1
        else:
            continue
        x, y = r.points[0]
        if not (0 <= x <= dims[0] - 1 and 0 <= y <= dims[1] - 1 and 0 <= r.slice < dims[2]):
            raise ValueError("A prompt lies outside the volume")
        out.setdefault(r.slice, ([], []))[k].append((x, y))
    out = {z: v for z, v in out.items() if v[0]}
    if not out:
        raise ValueError("No prompt: place a Probe measurement on the object (Text '-' marks background), then run again")
    return out


# ---- models -----------------------------------------------------------------------------------------------------


class Sam:
    def __init__(self):
        import onnxruntime as ort

        def path(name, env):
            if os.environ.get(env):
                return os.environ[env]
            from huggingface_hub import hf_hub_download

            return hf_hub_download(repo_id=REPO, filename=name)

        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.encoder = ort.InferenceSession(path(ENCODER, "RADSPIDER_SAM_ENCODER"), opts, providers=providers)
        self.decoder = ort.InferenceSession(path(DECODER, "RADSPIDER_SAM_DECODER"), opts, providers=providers)

    def embed(self, x):
        return self.encoder.run(None, {"input_image": x})[0]

    def mask(self, emb, include, exclude, scale, hw, prev=None):
        """Boolean (h, w) mask from include / exclude points (x, y) in slice pixels. ``prev``: low-res logits to refine."""
        pts = [((x + 0.5) * scale, (y + 0.5) * scale) for x, y in include + exclude] + [(0.0, 0.0)]
        lab = [1.0] * len(include) + [0.0] * len(exclude) + [-1.0]  # the last is Meta's "no box" padding point
        out = self.decoder.run(None, {
            "image_embeddings": emb,
            "point_coords": np.array([pts], dtype=np.float32),
            "point_labels": np.array([lab], dtype=np.float32),
            "mask_input": np.zeros((1, 1, 256, 256), np.float32) if prev is None else prev,
            "has_mask_input": np.array([0.0 if prev is None else 1.0], dtype=np.float32),
            "orig_im_size": np.array(hw, dtype=np.float32),
        })
        return out[0][0, 0] > 0.0, out[2]


# ---- entries ----------------------------------------------------------------------------------------------------


@rp.segmentation("prompt")
def prompt(volume, ctx):
    a = volume.numpy()
    dims = volume.dims
    groups = prompts_by_slice(ctx.rois, dims)
    ctx.progress(0.02, "Loading SAM ViT-B (first run downloads ~190 MB)")
    sam = Sam()
    labels = np.zeros(a.shape, dtype=np.uint8)
    names = []
    for n, z in enumerate(sorted(groups)):
        ctx.progress(0.1 + 0.85 * n / len(groups), "Slice %d" % z)
        inc, exc = groups[z]
        x, scale = model_input(a[z], ctx.params["center"], ctx.params["width"])
        m, _ = sam.mask(sam.embed(x), inc, exc, scale, a[z].shape)
        if ctx.params["separate"] >= 0.5:
            if len(names) >= 255:
                raise ValueError("More than 255 slices with prompts")
            labels[z][m] = len(names) + 1
            names.append("SAM slice %d" % z)
        else:
            labels[z][m] = 1
    return (labels, names) if names else (labels, ["SAM"])


@rp.segmentation("propagate")
def propagate(volume, ctx):
    a = volume.numpy()
    segs = ctx.segments
    if not segs:
        raise ValueError("No segment to propagate: open MPR on the series and make a segment first")
    k = int(round(ctx.params["segment"])) - 1
    if not 0 <= k < len(segs):
        raise ValueError("The series has %d segment(s); segment %d does not exist" % (len(segs), k + 1))
    mask = segs[k].mask()
    zs = np.nonzero(mask.reshape(mask.shape[0], -1).any(axis=1))[0]
    if zs.size == 0:
        raise ValueError("Segment '%s' is empty" % segs[k].name)
    ctx.progress(0.02, "Loading SAM ViT-B (first run downloads ~190 MB)")
    sam = Sam()
    out = mask.copy()
    rng = random.Random(0)  # same points every run
    steps = int(round(ctx.params["slices"]))
    total = 2 * steps
    done = 0
    for z_from, direction in ((int(zs[0]), -1), (int(zs[-1]), 1)):
        prev = mask[z_from]
        for i in range(1, steps + 1):
            z = z_from + direction * i
            done += 1
            if not 0 <= z < a.shape[0]:
                break
            ctx.progress(0.1 + 0.85 * done / total, "Slice %d" % z)
            ys, xs = np.nonzero(prev)
            pick = rng.sample(range(len(ys)), min(POINTS, len(ys)))
            x, scale = model_input(a[z], ctx.params["center"], ctx.params["width"])
            m, _ = sam.mask(sam.embed(x), [(float(xs[j]), float(ys[j])) for j in pick], [], scale, a[z].shape)
            # Deviation from OHIF: the new slice may only grow ~LIMIT_MM beyond the neighbour's mask. SAM on its own
            # often floods into the organ next door when prompted with points of one slice.
            m &= dilate(prev, max(1, int(round(LIMIT_MM / min(volume.spacing[0], volume.spacing[1])))))
            if not m.any():
                break
            out[z] |= m
            prev = m
    return out.astype(np.uint8), [segs[k].name + " + SAM"]


def dilate(m, n):
    """Binary dilation by n pixels (square element), numpy only."""
    out = m.copy()
    for _ in range(n):
        p = np.pad(out, 1)
        out = out | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return out


def hull(points):
    """Convex hull of (x, y) tuples, Andrew's monotone chain."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def bidirectional_axes(m, sx, sy):
    """Mask (rows, cols) -> (long a, long b, short c, short d, long mm, short mm) in pixel (x, y); None if empty.

    The long axis joins the two farthest pixel corners; the short one is the longest chord perpendicular to it."""
    ys, xs = np.nonzero(m)
    if xs.size == 0:
        return None
    # pixel corners, so a one-pixel segment still measures one pixel
    corners = {(x + dx, y + dy) for x, y in zip(xs.tolist(), ys.tolist()) for dx in (-0.5, 0.5) for dy in (-0.5, 0.5)}
    h = hull(list(corners))
    best = (-1.0, h[0], h[0])
    for i, p in enumerate(h):
        for q in h[i:]:
            d = math.hypot((p[0] - q[0]) * sx, (p[1] - q[1]) * sy)
            if d > best[0]:
                best = (d, p, q)
    long_mm, a, b = best
    if long_mm == 0:
        return a, b, a, b, 0.0, 0.0
    ux, uy = (b[0] - a[0]) * sx / long_mm, (b[1] - a[1]) * sy / long_mm  # long axis direction in mm
    px, py = xs * sx, ys * sy
    u = px * ux + py * uy
    v = -px * uy + py * ux
    step = min(sx, sy)
    bins = np.floor((u - u.min()) / step).astype(int)
    short = (0.0, None)
    for bnum in np.unique(bins):
        sel = bins == bnum
        vs = v[sel]
        chord = vs.max() - vs.min() + step
        if chord > short[0]:
            ub = u[sel].mean()
            short = (chord, (ub, vs.min() - step / 2, vs.max() + step / 2))
    chord, (ub, v0, v1) = short
    to_px = lambda uu, vv: ((uu * ux - vv * uy) / sx, (uu * uy + vv * ux) / sy)
    c, d = to_px(ub, v0), to_px(ub, v1)
    return a, b, c, d, long_mm, chord


@rp.tool("bidirectional")
def bidirectional(volume, ctx):
    if not ctx.segments:
        raise ValueError("No segments: open MPR on the series and make a segment first")
    sx, sy = volume.spacing[0], volume.spacing[1]
    rows, rois = [["Segment", "Slice", "Long axis (mm)", "Short axis (mm)"]], []
    for s in ctx.segments:
        m = s.mask()
        areas = m.reshape(m.shape[0], -1).sum(axis=1)
        if areas.max() == 0:
            rows.append([s.name, None, None, None])
            continue
        z = int(areas.argmax())
        a, b, c, d, lmm, smm = bidirectional_axes(m[z], sx, sy)
        rois.append(rp.Roi("bidimensional", z, [(float(p[0]), float(p[1])) for p in (a, b, c, d)]))
        rows.append([s.name, z, round(float(lmm), 1), round(float(smm), 1)])
    return rp.Result(table=rows, rois=rois, message="%d measurement(s) added" % len(rois))

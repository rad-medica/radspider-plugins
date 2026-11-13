"""SAM-Med3D (Wang et al., ECCV 2024; Apache-2.0) as a radspider segmentation plugin.

Prompts are the series' measurements: a Probe is a positive click, a Text measurement reading "-" a negative one.
The model sees a 128^3 window at 1.5 mm, RAS axes, z-normalised over voxels > 0 (the preprocessing of the upstream
repository: utils/infer_utils.py). The mask is mapped back onto the volume's own grid.
"""

import math
import os

import numpy as np

import radspider_plugin as rp

SIZE = 128  # model input edge, voxels
SPACING = 1.5  # model input voxel size, mm
REPO, FILE = "blueyo0/SAM-Med3D", "sam_med3d_turbo.pth"
NEGATIVE = ("-", "neg", "negative")


# ---- geometry (numpy only) --------------------------------------------------------------------------------------


class Window:
    """The 128^3 model window around a set of points: where it sits in the volume and how coordinates map.

    Axes are (x, y, z) of the volume. ``lo``/``n`` give the volume block (original voxels, may leave the volume),
    ``r`` its size at 1.5 mm, ``off`` where the window starts inside that resampled block."""

    def __init__(self, dims, spacing, centre):
        self.dims, self.spacing = tuple(dims), tuple(spacing)
        self.n = tuple(int(math.ceil(SIZE * SPACING / s)) + 2 for s in spacing)
        self.lo = tuple(int(round(c)) - n // 2 for c, n in zip(centre, self.n))
        self.r = tuple(max(SIZE, int(round(n * s / SPACING))) for n, s in zip(self.n, spacing))
        self.off = tuple((r - SIZE) // 2 for r in self.r)

    def to_window(self, p):
        """Volume voxel (x, y, z) -> model window coordinates, float (x and y flipped to RAS)."""
        out = []
        for i, (v, lo, n, r, off) in enumerate(zip(p, self.lo, self.n, self.r, self.off)):
            b = v - lo
            if i < 2:
                b = n - 1 - b
            out.append((b + 0.5) * r / n - 0.5 - off)
        return out

    def inside(self, w):
        return all(0 <= c <= SIZE - 1 for c in w)


def block(a, win):
    """Cut the window's block out of ``a`` (z, y, x), zero outside the volume; returns an (x, y, z) array."""
    out = np.zeros(win.n, dtype=np.float32)  # (x, y, z)
    src, dst = [], []
    for lo, n, d in zip(win.lo, win.n, win.dims):
        s0, s1 = max(lo, 0), min(lo + n, d)
        if s1 <= s0:
            return out
        src.append(slice(s0, s1))
        dst.append(slice(s0 - lo, s1 - lo))
    out[dst[0], dst[1], dst[2]] = np.transpose(a[src[2], src[1], src[0]], (2, 1, 0))
    return out


def unblock(prob, win, shape_zyx):
    """Paste a block-sized (x, y, z) boolean array back into a (z, y, x) uint8 array of the volume's size."""
    out = np.zeros(shape_zyx, dtype=np.uint8)
    src, dst = [], []
    for lo, n, d in zip(win.lo, win.n, win.dims):
        s0, s1 = max(lo, 0), min(lo + n, d)
        if s1 <= s0:
            return out
        dst.append(slice(s0, s1))
        src.append(slice(s0 - lo, s1 - lo))
    out[dst[2], dst[1], dst[0]] = np.transpose(prob[src[0], src[1], src[2]], (2, 1, 0))
    return out


def group_prompts(rois, dims, separate):
    """[(positives, negatives)] of voxel (x, y, z) points, one entry per object."""
    pos, neg = [], []
    for r in rois:
        if r.kind == "probe":
            pos.append((r.points[0][0], r.points[0][1], r.slice))
        elif r.kind == "text" and r.text.strip().lower() in NEGATIVE:
            neg.append((r.points[0][0], r.points[0][1], r.slice))
    if not pos:
        raise ValueError("No prompt: place a Probe measurement on the object (Text '-' marks background), then run again")
    for p in pos + neg:
        if not all(0 <= c <= d - 1 for c, d in zip(p, dims)):
            raise ValueError("A prompt lies outside the volume")
    return [([p], neg) for p in pos] if separate else [(pos, neg)]


# ---- model ------------------------------------------------------------------------------------------------------


def load_model(device):
    import torch
    import medim

    path = os.environ.get("RADSPIDER_SAMMED3D_CKPT")
    if not path:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(repo_id=REPO, filename=FILE)
    model = medim.create_model("SAM-Med3D", pretrained=False)
    state = torch.load(path, map_location="cpu", weights_only=True)  # plain tensors only; never unpickle code
    model.load_state_dict(state.get("model_state_dict", state), strict=False)
    return model.to(device).eval()


def run_window(model, device, image, points, labels, iterations):
    """One object: ``image`` (x, y, z) 128^3 float32 normalised, points in window coords -> probability (128^3)."""
    import torch
    import torch.nn.functional as F

    with torch.no_grad():
        x = torch.from_numpy(image)[None, None].to(device)
        emb = model.image_encoder(x)
        pts = torch.tensor([points], dtype=torch.float32, device=device)
        lab = torch.tensor([labels], dtype=torch.int64, device=device)
        prev = torch.zeros(1, 1, SIZE // 4, SIZE // 4, SIZE // 4, device=device)
        for _ in range(iterations):
            sparse, dense = model.prompt_encoder(points=[pts, lab], boxes=None, masks=prev)
            low, _ = model.mask_decoder(
                image_embeddings=emb,
                image_pe=model.prompt_encoder.get_dense_pe(),
                sparse_prompt_embeddings=sparse,
                dense_prompt_embeddings=dense,
            )
            prev = low.detach()
        full = F.interpolate(low, size=(SIZE,) * 3, mode="trilinear", align_corners=False)
        return torch.sigmoid(full)[0, 0].cpu().numpy()


def prepare(a, win):
    """Block -> 128^3 model input: flip to RAS, resample to 1.5 mm, centre window, z-normalise over voxels > 0."""
    import torch
    import torch.nn.functional as F

    b = np.ascontiguousarray(block(a, win)[::-1, ::-1, :])
    t = torch.from_numpy(b)[None, None]
    t = F.interpolate(t, size=win.r, mode="trilinear", align_corners=False)[0, 0].numpy()
    o = win.off
    w = t[o[0]:o[0] + SIZE, o[1]:o[1] + SIZE, o[2]:o[2] + SIZE]
    pos = w[w > 0]
    sd = float(pos.std()) if pos.size else 0.0
    return ((w - (pos.mean() if pos.size else 0.0)) / (sd if sd > 0 else 1.0)).astype(np.float32)


def restore(prob, win, thr, shape_zyx):
    """128^3 probability -> uint8 mask (z, y, x) on the volume's grid."""
    import torch
    import torch.nn.functional as F

    full = np.zeros(win.r, dtype=np.float32)
    o = win.off
    full[o[0]:o[0] + SIZE, o[1]:o[1] + SIZE, o[2]:o[2] + SIZE] = prob
    t = F.interpolate(torch.from_numpy(full)[None, None], size=win.n, mode="trilinear", align_corners=False)[0, 0]
    m = np.ascontiguousarray((t.numpy() > thr)[::-1, ::-1, :])
    return unblock(m, win, shape_zyx)


# ---- entry ------------------------------------------------------------------------------------------------------


@rp.segmentation("segment")
def segment(volume, ctx):
    import torch

    a = volume.numpy()
    if np.isnan(a).any():
        a = np.where(np.isnan(a), np.nanmin(a) if not np.isnan(a).all() else 0.0, a).astype(np.float32)
    dims, spacing = volume.dims, volume.spacing
    groups = group_prompts(ctx.rois, dims, ctx.params["separate"] >= 0.5)
    if len(groups) > 255:
        raise ValueError("More than 255 objects")
    iterations = int(round(ctx.params["iterations"]))
    thr = float(ctx.params["threshold"])

    ctx.progress(0.02, "Loading SAM-Med3D (first run downloads ~400 MB)")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_model(device)

    labels = np.zeros(a.shape, dtype=np.uint8)
    names = []
    for i, (pos, neg) in enumerate(groups):
        ctx.progress(0.1 + 0.85 * i / len(groups), "Object %d of %d on %s" % (i + 1, len(groups), device.type))
        centre = [sum(p[k] for p in pos) / len(pos) for k in range(3)]
        win = Window(dims, spacing, centre)
        points = [win.to_window(p) for p in pos]
        if not all(win.inside(w) for w in points):
            raise ValueError("Clicks are more than ~%d mm apart: one object must fit in a %d mm window" % (SIZE * SPACING, SIZE * SPACING))
        far = [w for w in map(win.to_window, neg) if win.inside(w)]  # background clicks outside the window do not matter
        points += far
        pos_n = len(pos)
        mask = restore(
            run_window(model, device, prepare(a, win), points, [1] * pos_n + [0] * len(far), iterations),
            win, thr, a.shape,
        )
        labels[(mask > 0) & (labels == 0)] = i + 1
        names.append("SAM-Med3D" if len(groups) == 1 else "SAM-Med3D %d" % (i + 1))
    return labels, names

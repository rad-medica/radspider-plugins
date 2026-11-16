"""MONAI model zoo bundle ``wholeBody_ct_segmentation`` (SegResNet, 104 structures) as a radspider segmentation.

Follows the bundle's ``configs/inference.json``: RAS, resample to 1.5 / 3 mm, NormalizeIntensity(nonzero), ScaleIntensity
[-1, 1], 96^3 Gaussian sliding window, softmax + argmax, nearest back to the volume grid. The sliding window keeps only
a band of 96 slices of logits in memory (MONAI's inferer keeps all 105 channels of the whole volume).
"""

import math
import os

import numpy as np

import radspider_plugin as rp

REPO = "MONAI/wholeBody_ct_segmentation"
ROI = 96
CLASSES = 105
NAMES = (
    "spleen kidney_right kidney_left gallbladder liver stomach aorta inferior_vena_cava portal_vein_and_splenic_vein "
    "pancreas adrenal_gland_right adrenal_gland_left lung_upper_lobe_left lung_lower_lobe_left lung_upper_lobe_right "
    "lung_middle_lobe_right lung_lower_lobe_right "
    + " ".join("vertebrae_" + v for v in "L5 L4 L3 L2 L1 T12 T11 T10 T9 T8 T7 T6 T5 T4 T3 T2 T1 C7 C6 C5 C4 C3 C2 C1".split())
    + " esophagus trachea heart_myocardium heart_atrium_left heart_ventricle_left heart_atrium_right "
    "heart_ventricle_right pulmonary_artery brain iliac_artery_left iliac_artery_right iliac_vena_left iliac_vena_right "
    "small_bowel duodenum colon "
    + " ".join("rib_left_%d" % i for i in range(1, 13))
    + " "
    + " ".join("rib_right_%d" % i for i in range(1, 13))
    + " humerus_left humerus_right scapula_left scapula_right clavicula_left clavicula_right femur_left femur_right "
    "hip_left hip_right sacrum face gluteus_maximus_left gluteus_maximus_right gluteus_medius_left gluteus_medius_right "
    "gluteus_minimus_left gluteus_minimus_right autochthon_left autochthon_right iliopsoas_left iliopsoas_right "
    "urinary_bladder"
).split()
assert len(NAMES) == CLASSES - 1


# ---- numpy / torch helpers -------------------------------------------------------------------------------------


def scan_starts(size, interval):
    """MONAI's window start positions along one axis (size >= ROI)."""
    n = int(math.ceil((size - ROI) / interval)) + 1 if size > ROI else 1
    return sorted({min(i * interval, size - ROI) for i in range(n)})


def gaussian_importance():
    import torch

    sigma = 0.125 * ROI
    c = torch.arange(ROI, dtype=torch.float32) - (ROI - 1) / 2
    g = torch.exp(-0.5 * (c / sigma) ** 2)
    w = g[:, None, None] * g[None, :, None] * g[None, None, :]
    w = w / w.max()
    return w.clamp_min(w[w > 0].min())


def normalise(t):
    """NormalizeIntensity(nonzero=True) then ScaleIntensity(-1, 1)."""
    nz = t != 0
    if nz.any():
        v = t[nz]
        sd = v.std()
        t[nz] = (v - v.mean()) / (sd if sd > 0 else 1.0)
    lo, hi = t.min(), t.max()
    return (t - lo) / (hi - lo) * 2 - 1 if hi > lo else t - lo


def sliding_window(net, x, overlap, device, progress):
    """x: (1, 1, X, Y, Z) tensor on CPU -> uint8 label array (X, Y, Z). Gaussian-weighted, band-wise argmax."""
    import torch
    import torch.nn.functional as F

    shape = x.shape[2:]
    pad = [max(0, ROI - s) for s in shape]
    if any(pad):  # replicate padding, like the bundle's padding_mode
        x = F.pad(x, (0, pad[2], 0, pad[1], 0, pad[0]), mode="replicate")
    X, Y, Z = x.shape[2:]
    interval = max(1, int(ROI * (1 - overlap)))
    sx, sy, sz = scan_starts(X, interval), scan_starts(Y, interval), scan_starts(Z, interval)
    w = gaussian_importance().to(device)
    band_bytes = CLASSES * X * Y * ROI * 4
    dtype = torch.float32 if band_bytes < 3 * 2**30 else torch.float16
    buf = torch.zeros(CLASSES, X, Y, ROI, dtype=dtype)
    out = np.zeros((X, Y, Z), dtype=np.uint8)
    total, done = len(sx) * len(sy) * len(sz), 0
    for k, z0 in enumerate(sz):
        for x0 in sx:
            for y0 in sy:
                tile = x[:, :, x0:x0 + ROI, y0:y0 + ROI, z0:z0 + ROI].to(device)
                with torch.no_grad():
                    logits = net(tile)[0] * w
                buf[:, x0:x0 + ROI, y0:y0 + ROI, :] += logits.to(dtype=dtype, device="cpu")
                done += 1
            progress(done / total)
        last = k == len(sz) - 1
        d = ROI if last else sz[k + 1] - z0
        out[:, :, z0:z0 + d] = buf[:, :, :, :d].argmax(0).numpy().astype(np.uint8)
        if not last:
            buf[:, :, :, :ROI - d] = buf[:, :, :, d:].clone()
            buf[:, :, :, ROI - d:] = 0
    return out[:shape[0], :shape[1], :shape[2]]


def load_net(device, highres):
    import torch
    from monai.networks.nets import SegResNet

    path = os.environ.get("RADSPIDER_MONAI_WHOLEBODY_WEIGHTS")
    if not path:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(repo_id=REPO, filename="models/model.pt" if highres else "models/model_lowres.pt")
    net = SegResNet(spatial_dims=3, in_channels=1, out_channels=CLASSES, init_filters=32, blocks_down=[1, 2, 2, 4],
                    blocks_up=[1, 1, 1], dropout_prob=0.2)
    net.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))  # a plain state dict, no pickled code
    return net.to(device).eval()


# ---- entry ------------------------------------------------------------------------------------------------------


@rp.segmentation("wholebody")
def wholebody(volume, ctx):
    import torch
    import torch.nn.functional as F

    if volume.unit not in (None, "HU"):
        raise ValueError("This model needs a CT in Hounsfield units (the series is in %s)" % volume.unit)
    highres = ctx.params["resolution"] == "1.5 mm"
    pix = 1.5 if highres else 3.0
    a = volume.numpy()
    if np.isnan(a).any():
        a = np.where(np.isnan(a), np.nanmin(a) if not np.isnan(a).all() else 0.0, a).astype(np.float32)
    dims = volume.dims  # x, y, z
    size = tuple(max(1, int(round(n * s / pix))) for n, s in zip(dims, volume.spacing))

    ctx.progress(0.02, rp.tr("Preparing the volume at {mm} mm", mm="%.1f" % pix))
    t = torch.from_numpy(np.ascontiguousarray(np.transpose(a, (2, 1, 0))[::-1, ::-1, :].copy()))  # (x, y, z) in RAS
    del a
    t = F.interpolate(t[None, None], size=size, mode="trilinear", align_corners=False)
    t[0, 0] = normalise(t[0, 0])

    ctx.progress(0.05, rp.tr("Loading the model (first run downloads 71 MB)"))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = load_net(device, highres)
    segmenting = rp.tr("Segmenting on {device}", device=device.type)
    ctx.progress(0.08, segmenting)
    lab = sliding_window(net, t, float(ctx.params["overlap"]), device, lambda f: ctx.progress(0.08 + 0.85 * f, segmenting))

    ctx.progress(0.95, rp.tr("Back to the series grid"))
    full = F.interpolate(torch.from_numpy(lab)[None, None].float(), size=dims, mode="nearest")[0, 0].to(torch.uint8).numpy()
    out = np.ascontiguousarray(np.transpose(full[::-1, ::-1, :], (2, 1, 0)))
    return out, NAMES

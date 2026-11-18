"""TotalSegmentator (v2, task 297 "total", 3 mm), run with ONNX Runtime. One of the models of ``plugin.py``.

Weights: the official nnU-Net release zip, checked against a pinned SHA-256, converted once to ONNX (PyTorch is needed
only for that). Inference follows nnU-Net v2 (``nnUNetPredictor``) for this trainer, which has no mirroring: CT
normalisation (clip to the 0.5 / 99.5 percentiles of the training foreground, z-score), resample to 3 mm, 112x112x128
sliding window with step 0.5 and Gaussian weights, argmax of the summed logits. Arrays are (z, y, x) of a RAS file, so
x and y are flipped from DICOM's LPS. Deviation: the label map goes back to the series grid by nearest neighbour
(nnU-Net resamples the logits first).
"""

import hashlib
import os
import tempfile
import urllib.request
import zipfile

import numpy as np

import radspider_plugin as rp

URL = "https://github.com/wasserth/TotalSegmentator/releases/download/v2.0.0-weights/Dataset297_TotalSegmentator_total_3mm_1559subj.zip"
SHA256 = "0baa2c8de2975600eb31801dd5c1825cd2b356f794498659cf3348714c073394"
FOLDER = "Dataset297_TotalSegmentator_total_3mm_1559subj/nnUNetTrainer_4000epochs_NoMirroring__nnUNetPlans__3d_fullres/"
PATCH = (112, 112, 128)  # (z, y, x) of the plans' patch_size
SPACING = 3.0
CLIP = (-1004.0, 1588.0)  # percentile_00_5, percentile_99_5 of the training foreground
MEAN, STD = -50.38697721419439, 503.39235619144
CLASSES = 118
NAMES = (
    "spleen kidney_right kidney_left gallbladder liver stomach pancreas adrenal_gland_right "
    "adrenal_gland_left lung_upper_lobe_left lung_lower_lobe_left lung_upper_lobe_right "
    "lung_middle_lobe_right lung_lower_lobe_right esophagus trachea thyroid_gland small_bowel duodenum "
    "colon urinary_bladder prostate kidney_cyst_left kidney_cyst_right sacrum vertebrae_S1 vertebrae_L5 "
    "vertebrae_L4 vertebrae_L3 vertebrae_L2 vertebrae_L1 vertebrae_T12 vertebrae_T11 vertebrae_T10 "
    "vertebrae_T9 vertebrae_T8 vertebrae_T7 vertebrae_T6 vertebrae_T5 vertebrae_T4 vertebrae_T3 "
    "vertebrae_T2 vertebrae_T1 vertebrae_C7 vertebrae_C6 vertebrae_C5 vertebrae_C4 vertebrae_C3 "
    "vertebrae_C2 vertebrae_C1 heart aorta pulmonary_vein brachiocephalic_trunk subclavian_artery_right "
    "subclavian_artery_left common_carotid_artery_right common_carotid_artery_left "
    "brachiocephalic_vein_left brachiocephalic_vein_right atrial_appendage_left superior_vena_cava "
    "inferior_vena_cava portal_vein_and_splenic_vein iliac_artery_left iliac_artery_right iliac_vena_left "
    "iliac_vena_right humerus_left humerus_right scapula_left scapula_right clavicula_left "
    "clavicula_right femur_left femur_right hip_left hip_right spinal_cord gluteus_maximus_left "
    "gluteus_maximus_right gluteus_medius_left gluteus_medius_right gluteus_minimus_left "
    "gluteus_minimus_right autochthon_left autochthon_right iliopsoas_left iliopsoas_right brain skull "
    "rib_left_1 rib_left_2 rib_left_3 rib_left_4 rib_left_5 rib_left_6 rib_left_7 rib_left_8 rib_left_9 "
    "rib_left_10 rib_left_11 rib_left_12 rib_right_1 rib_right_2 rib_right_3 rib_right_4 rib_right_5 "
    "rib_right_6 rib_right_7 rib_right_8 rib_right_9 rib_right_10 rib_right_11 rib_right_12 sternum "
    "costal_cartilages "
).split()
assert len(NAMES) == CLASSES - 1


# ---- weights: download, verify, convert ---------------------------------------------------------------------------


def cache_dir():
    d = os.environ.get("RADSPIDER_TOTALSEG_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "radspider", "totalsegmentator")
    os.makedirs(d, exist_ok=True)
    return d


def download_checked(dest, progress=lambda f: None):
    h = hashlib.sha256()
    with urllib.request.urlopen(URL, timeout=60) as r, open(dest, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            f.write(chunk)
            done += len(chunk)
            if total:
                progress(done / total)
    if h.hexdigest() != SHA256:
        os.remove(dest)
        raise ValueError("The downloaded weights do not match the pinned SHA-256 (got %s); nothing was loaded" % h.hexdigest())


def convert(zip_path, onnx_path):
    """Official checkpoint -> ONNX. Only runs on a zip whose SHA-256 matched ``SHA256``."""
    import torch
    import torch.nn as nn
    from dynamic_network_architectures.architectures.unet import PlainConvUNet

    with zipfile.ZipFile(zip_path) as z:
        ck = z.open(FOLDER + "fold_0/checkpoint_final.pth")
        # nnU-Net checkpoints hold numpy objects, so weights_only=True cannot read them. The pickle comes from the
        # release whose hash was just verified; it is never loaded from anywhere else.
        state = torch.load(ck, map_location="cpu", weights_only=False)["network_weights"]
    net = PlainConvUNet(1, 5, [32, 64, 128, 256, 320], nn.Conv3d, [[3, 3, 3]] * 5,
                        [[1, 1, 1], [2, 2, 2], [2, 2, 2], [2, 2, 2], [2, 2, 2]], [2] * 5, CLASSES, [2] * 4, True,
                        nn.InstanceNorm3d, {"eps": 1e-5, "affine": True}, None, None, nn.LeakyReLU, {"inplace": True},
                        deep_supervision=False)
    net.load_state_dict(state)
    net.eval()
    tmp = onnx_path + ".part"
    with torch.no_grad():
        torch.onnx.export(net, torch.zeros(1, 1, *PATCH), tmp, input_names=["x"], output_names=["logits"], opset_version=17,
                          dynamo=False)
    os.replace(tmp, onnx_path)


def onnx_file():
    """Where the converted model lives in the cache (it may not exist yet)."""
    return os.path.join(cache_dir(), "total_3mm_v2.0.0.onnx")


def model_path(progress):
    p = os.environ.get("RADSPIDER_TOTALSEG_ONNX")
    if p:
        return p
    onnx_path = onnx_file()
    if not os.path.exists(onnx_path):
        message = rp.tr("Downloading the TotalSegmentator weights (135 MB)")
        progress(0.01, message)
        with tempfile.TemporaryDirectory(dir=cache_dir()) as tmp:
            z = os.path.join(tmp, "weights.zip")
            download_checked(z, lambda f: progress(0.01 + 0.03 * f, message))
            progress(0.04, rp.tr("Converting to ONNX (once)"))
            convert(z, onnx_path)
    return onnx_path


# ---- inference -----------------------------------------------------------------------------------------------------


def steps(size, patch, step):
    """nnU-Net's ``compute_steps_for_sliding_window`` for one axis."""
    target = patch * step
    n = int(np.ceil((size - patch) / target)) + 1 if size > patch else 1
    if n == 1:
        return [0]
    actual = (size - patch) / (n - 1)
    return [int(np.round(actual * i)) for i in range(n)]


def gaussian():
    """nnU-Net's importance map: Gaussian, sigma = patch / 8, scaled to max 1, zeros lifted to the smallest value."""
    from scipy.ndimage import gaussian_filter

    tmp = np.zeros(PATCH)
    tmp[tuple(i // 2 for i in PATCH)] = 1
    g = gaussian_filter(tmp, [i / 8 for i in PATCH], 0, mode="constant", cval=0)
    g = (g / g.max()).astype(np.float32)
    g[g == 0] = g[g > 0].min()
    return g


def segment_array(session, x, step, progress):
    """x: normalised (z, y, x) float32 -> uint8 labels, same shape. Banded along z: only 112 slices of logits are kept."""
    shape = x.shape
    pad = [max(0, p - s) for p, s in zip(PATCH, shape)]
    if any(pad):
        x = np.pad(x, [(0, p) for p in pad], mode="constant")  # nnU-Net pads with 0 after normalising
    Z, Y, X = x.shape
    sz, sy, sx = steps(Z, PATCH[0], step), steps(Y, PATCH[1], step), steps(X, PATCH[2], step)
    w = gaussian()
    dtype = np.float32 if CLASSES * Y * X * PATCH[0] * 4 < 3 * 2**30 else np.float16
    buf = np.zeros((PATCH[0], CLASSES, Y, X), dtype=dtype)  # z first so the band shifts by a view
    out = np.zeros((Z, Y, X), dtype=np.uint8)
    total, done = len(sz) * len(sy) * len(sx), 0
    for k, z0 in enumerate(sz):
        for y0 in sy:
            for x0 in sx:
                tile = x[z0:z0 + PATCH[0], y0:y0 + PATCH[1], x0:x0 + PATCH[2]][None, None]
                logits = session.run(None, {"x": tile})[0][0]  # (C, z, y, x)
                buf[:, :, y0:y0 + PATCH[1], x0:x0 + PATCH[2]] += (logits * w).transpose(1, 0, 2, 3).astype(dtype)
                done += 1
            progress(done / total)
        last = k == len(sz) - 1
        d = PATCH[0] if last else sz[k + 1] - z0
        out[z0:z0 + d] = buf[:d].argmax(axis=1).astype(np.uint8)
        if not last:
            buf[:PATCH[0] - d] = buf[d:]
            buf[PATCH[0] - d:] = 0
    return out[:shape[0], :shape[1], :shape[2]]


def segment(volume, ctx, step):
    """``step``: window step as a fraction of the window (nnU-Net default 0.5)."""
    import onnxruntime as ort
    from scipy.ndimage import zoom

    if volume.unit not in (None, "HU"):
        raise ValueError("This model needs a CT in Hounsfield units (the series is in %s)" % volume.unit)
    a = volume.numpy()  # (z, y, x), DICOM LPS
    if np.isnan(a).any():
        a = np.where(np.isnan(a), np.nanmin(a) if not np.isnan(a).all() else 0.0, a).astype(np.float32)
    nx, ny, nz = volume.dims
    sx, sy, sz = volume.spacing
    target = (max(1, round(nz * sz / SPACING)), max(1, round(ny * sy / SPACING)), max(1, round(nx * sx / SPACING)))

    path = model_path(ctx.progress)
    ctx.progress(0.06, rp.tr("Preparing the volume at 3 mm"))
    ras = np.ascontiguousarray(a[:, ::-1, ::-1])  # RAS file order: x and y run the other way
    r = zoom(ras, [t / s for t, s in zip(target, ras.shape)], order=1, mode="nearest", grid_mode=True).astype(np.float32)
    del a, ras
    r = ((np.clip(r, *CLIP) - MEAN) / STD).astype(np.float32)

    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
    session = ort.InferenceSession(path, opts, providers=providers)
    segmenting = rp.tr("Segmenting")
    ctx.progress(0.08, segmenting)
    lab = segment_array(session, r, step, lambda f: ctx.progress(0.08 + 0.87 * f, segmenting))

    ctx.progress(0.96, rp.tr("Back to the series grid"))
    full = zoom(lab, [s / t for s, t in zip((nz, ny, nx), lab.shape)], order=0, mode="nearest", grid_mode=True)
    return np.ascontiguousarray(full[:, ::-1, ::-1]).astype(np.uint8), NAMES

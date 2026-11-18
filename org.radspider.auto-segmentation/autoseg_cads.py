"""CADS whole-body CT segmentation (167 structures in nine task groups, 551-559) as one of the models of ``plugin.py``.

Equivalent of the 3D Slicer extension CADSWholeBodyCTSeg, which calls the ``cads`` package (murong-xu/CADS). That
package drives ``nnunetv2``; here its pipeline is rebuilt on numpy, scipy and PyTorch:

* CADS preprocessing (``cads/dataset_utils/preprocessing.py``): reorient to RAS, cubic resampling to 1.5 mm with
  ``scipy.ndimage.zoom``, values truncated to integers;
* nnU-Net v2 inference as ``nnUNetPredictor(tile_step_size=0.5, use_gaussian=True, use_mirroring=False)`` on the
  ``fold_all`` model: crop to the non-zero box, CT normalisation with the numbers of each task's ``plans.json``,
  centred zero padding to the window, sliding window with Gaussian weights, argmax of the summed logits;
* CADS post-processing (``cads/dataset_utils/postprocessing.py``, ``TPTBox.py``): connected-component filter for tasks
  551, 553, 554, 556, 559 and the head box for 557 / 558, which needs the brain of task 553 (and, without a brain, the
  upper vertebrae of task 552);
* labels back to the series grid by nearest neighbour, as CADS does.

Weights: the upstream zip of each task (GitHub release, about 760 MB) is checked against a SHA-256 pinned below, its
nnU-Net checkpoint (a pickle) is unpickled once, and the network weights are stored as a plain state dict that later
runs read with ``weights_only=True``. Arrays are (z, y, x) = (S, A, R), the order nnU-Net gets from a RAS file.
"""

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
import zipfile

import numpy as np

import radspider_plugin as rp

SPACING = 1.5  # mm, every task (plans.json "spacing")
RELEASES = "https://github.com/murong-xu/CADS/releases/download/"
# Licence-stratified weight variants of cads/LICENSE_MODEL. The third one ("reference", CADS customized model
# licence) is left out on purpose: its terms are not in the repository.
VARIANTS = {
    "open": ("cads-model-open_v1.0.0", "CC BY-SA 4.0"),
    "research": ("cads-model-research_v1.0.0", "CC BY-NC-SA 4.0"),
}
FOLDERS = {
    551: "Dataset551_Totalseg251", 552: "Dataset552_Totalseg252", 553: "Dataset553_Totalseg253",
    554: "Dataset554_Totalseg254", 555: "Dataset555_Totalseg255", 556: "Dataset556_GC256",
    557: "Dataset557_Brain257", 558: "Dataset558_OAR258", 559: "Dataset559_Saros259",
}
TRAINER = "nnUNetTrainerNoMirroring__nnUNetResEncUNetLPlans__3d_fullres/"
# SHA-256 of <release>/<folder>.zip, computed on the files downloaded from the releases above on 2026-11-13.
# Upstream publishes no checksums, so these pin the files as they were that day.
SHA256 = {
    ("open", 551): "99b33943d202d794249e85c6e42bb30c7b72c7afc36d044fe57103b675e85656",
    ("open", 552): "de132d4104627401852f2a7c426056462423df30bee7ffed7e07aebe32d32736",
    ("open", 553): "927dbe88f9873fc9598702884c11cf3adc4535749146cd3e6424ac40579b3e45",
    ("open", 554): "cbee9dda40dd946c70c238f9e580f64ab4367c27d5472c9fc77853d16509e54f",
    ("open", 555): "a7fdf1ca915746551f322168623def871462e6b56bf1a59e0cc253f2baf41e54",
    ("open", 556): "a2110a2501de85c3dfc63298fcda1d19fb3b935e6d012692c0d749b97b2c8d1e",
    ("open", 557): "18b563d7bd20b1a2bce0632b98064a0279280d0f3e56e91f2e6328eb1a7e740c",
    ("open", 558): "8fa72c933bd33d5a30b1bc9f2f0bee18f8a3e6c445589255e58327a80447b831",
    ("open", 559): "1b1b546f27e7c548dbaf49951cd1974c376719e6714a1f4c3def40a1c4c0dca9",
    ("research", 551): "6941b2c536a0737c1f7c151ce8884f943022a4d1b271238c5a834168bc15ec0d",
    ("research", 552): "546b8f0c177a4e4992d7da9ce0a18add6772fc40b0e164aab2ae23568f09a69e",
    ("research", 553): "46a45beaadf99e7777b2064f966b7ef98e1a9c1dee3ac783e65e8063a9ded5ca",
    ("research", 554): "2c7972f9446de950c2f48288ccec8383acafb4e07aea8fbe7507a1fa44c019a9",
    ("research", 555): "6ec5bc46a43a3e4c6d77e071ae179277fd1715dfa1debec96d225ab2f2ea30b4",
    ("research", 556): "94ecf5456e16dd212a0b8aee85be499f3fdafd1b4d7adc4b199802cb32aef5db",
    ("research", 557): "3b257b5e9a84abc51552812c3c08f13577ce87113c7bc495ad30c875b4da1bb8",
    ("research", 558): "1365677ce4498238e1630f1a06d6307b791fc06676f1421a1ecd0a1f7e4e4a8c",
    ("research", 559): "f8191a62b7351dfbc46ddc4f26945bc399981b7f66574d46c348b475757e4bbb",
}

# Names of label 1, 2, ... per task: resources/info/labelmap.md of murong-xu/CADS, same order as the dataset.json
# inside each weight zip (whose label count is checked at conversion).
NAMES = {
    551: "Spleen|Kidney R|Kidney L|Gallbladder|Liver|Stomach|Aorta|Inferior vena cava|Portal vein and splenic vein|"
         "Pancreas|Adrenal gland R|Adrenal gland L|Upper lobe of lung L|Lower lobe of lung L|Upper lobe of lung R|"
         "Middle lobe of lung R|Lower lobe of lung R",
    552: "Vertebra L5|Vertebra L4|Vertebra L3|Vertebra L2|Vertebra L1|Vertebra T12|Vertebra T11|Vertebra T10|"
         "Vertebra T9|Vertebra T8|Vertebra T7|Vertebra T6|Vertebra T5|Vertebra T4|Vertebra T3|Vertebra T2|"
         "Vertebra T1|Vertebra C7|Vertebra C6|Vertebra C5|Vertebra C4|Vertebra C3|Vertebra C2|Vertebra C1",
    553: "Esophagus|Trachea|Myocardium|Heart atrium L|Heart ventricle L|Heart atrium R|Heart ventricle R|"
         "Pulmonary artery|Brain|Common iliac artery L|Common iliac artery R|Common iliac vein L|"
         "Common iliac vein R|Small intestine|Duodenum|Colon|Urinary bladder|Face",
    554: "Humerus L|Humerus R|Scapula L|Scapula R|Clavicle L|Clavicle R|Femur L|Femur R|Hip L|Hip R|Sacrum|"
         "Gluteus maximus muscle L|Gluteus maximus muscle R|Gluteus medius muscle L|Gluteus medius muscle R|"
         "Gluteus minimus muscle L|Gluteus minimus muscle R|Deep muscle of back L|Deep muscle of back R|"
         "Iliopsoas muscle L|Iliopsoas muscle R",
    555: "Rib-1 L|Rib-2 L|Rib-3 L|Rib-4 L|Rib-5 L|Rib-6 L|Rib-7 L|Rib-8 L|Rib-9 L|Rib-10 L|Rib-11 L|Rib-12 L|"
         "Rib-1 R|Rib-2 R|Rib-3 R|Rib-4 R|Rib-5 R|Rib-6 R|Rib-7 R|Rib-8 R|Rib-9 R|Rib-10 R|Rib-11 R|Rib-12 R",
    556: "Spinal canal|Larynx|Heart|Bowel space|Sigmoid colon|Rectum|Prostate|Seminal vesicle|Mammary gland L|"
         "Mammary gland R|Sternum|Psoas major muscle R|Psoas major muscle L|Rectus abdominis muscle R|"
         "Rectus abdominis muscle L",
    557: "White matter|Gray matter|Cerebrospinal fluid|Scalp|Eyeballs|Compact bone|Spongy bone|"
         "Vascular structure of head|Rectus eye muscle structure",
    558: "Carotid artery L|Carotid artery R|Arytenoid cartilage|Mandible|Brain stem|Buccal mucosa|Oral cavity|"
         "Cochlea L|Cochlea R|Cricopharyngeus|Cervical esophagus|Anterior eyeball segment L|"
         "Anterior eyeball segment R|Posterior eyeball segment L|Posterior eyeball segment R|Lacrimal gland L|"
         "Lacrimal gland R|Submandibular gland L|Submandibular gland R|Thyroid|Glottis|Supraglottis|Lip|"
         "Optic chiasm|Optic nerve L|Optic nerve R|Parotid gland L|Parotid gland R|Pituitary gland",
    559: "Subcutaneous tissue|Muscle|Abdominopelvic cavity|Thoracic cavity|Bone structure|Gland structure|"
         "Pericardium|Breast implant|Mediastinum|Spinal cord",
}
NAMES = {task: names.split("|") for task, names in NAMES.items()}
assert sum(len(n) for n in NAMES.values()) == 167

# Connected-component rules of cads/dataset_utils/postprocessing.py ``labels_info``, by task and label value: the
# smallest volume kept ("autofix"), in voxels of the 1.5 mm grid. Labels that upstream leaves alone (commented out
# there, or absent) are absent here; tasks 552, 555, 557 and 558 have no such filter upstream.
MIN_VOLUME = {
    551: {1: 1000, 2: 1000, 3: 1000, 4: 20, 5: 2200, 6: 1000, 7: 1000, 8: 500, 10: 1000, 13: 300, 14: 300, 15: 300,
          16: 300, 17: 300},
    553: {1: 1000, 2: 100, 3: 100, 4: 100, 5: 100, 6: 100, 7: 100, 9: 100, 10: 10, 11: 10, 12: 500, 13: 500, 14: 150,
          16: 100, 17: 1500, 18: 100},
    554: {1: 500, 2: 500, 3: 500, 4: 500, 5: 1000, 6: 1000, 7: 1000, 8: 1000, 9: 1000, 10: 1000, 11: 1000, 12: 1000,
          13: 1000, 14: 1000, 15: 1000, 16: 1000, 17: 1000, 18: 1000, 19: 1000, 20: 1000, 21: 1000},
    556: {1: 1000, 2: 1000, 3: 1000, 4: 1000, 5: 1000, 6: 1000, 9: 0, 10: 0, 11: 1500, 12: 1000, 13: 1000, 14: 1000,
          15: 1000},
    559: {1: 4000, 2: 4000, 3: 200, 5: 200, 7: 1000, 10: 500},
}
ONE_COMPONENT = {(556, 9), (556, 10), (556, 11), (559, 3), (559, 7)}  # "max_cc": 1
FILL_HOLES = {(556, 9), (556, 10)}  # "fill": True (mammary glands)
BRAIN, BRAIN_VOXELS = 9, 2000  # task 553 label and the volume below which upstream says "no head"
HEAD_BOX = {557: (133, 100, 100), 558: (200, 100, 100)}  # half sizes (z, y, x) in voxels around the brain centroid
UPPER_VERTEBRAE = (14, 24)  # task 552 labels T4 ... C1: upstream's "cervical vertebrae (classes 14-24)"


# ---- weights: download, verify, convert ---------------------------------------------------------------------------


def cache_dir():
    d = os.environ.get("RADSPIDER_CADS_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "radspider", "cads")
    os.makedirs(d, exist_ok=True)
    return d


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_zip(variant, task, dest, progress):
    """The upstream zip of one task in ``dest``, from ``RADSPIDER_CADS_ZIPS`` or the release; SHA-256 checked."""
    name = FOLDERS[task] + ".zip"
    local = os.environ.get("RADSPIDER_CADS_ZIPS")
    if local:
        src = os.path.join(local, variant, name)
        if not os.path.isfile(src):
            raise ValueError("RADSPIDER_CADS_ZIPS is set but %s does not exist: put the upstream zip there" % src)
        got = sha256_of(src)
        if got != SHA256[variant, task]:
            raise ValueError("%s does not match the pinned SHA-256 (got %s); nothing was loaded" % (src, got))
        return src
    url = RELEASES + VARIANTS[variant][0] + "/" + name
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:
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
    except urllib.error.URLError as e:
        raise ValueError(
            "Could not download %s (%s). Offline: download it elsewhere into <folder>/%s/ and set "
            "RADSPIDER_CADS_ZIPS=<folder>" % (url, e, variant)
        ) from e
    if h.hexdigest() != SHA256[variant, task]:
        os.remove(dest)
        raise ValueError(
            "The downloaded weights do not match the pinned SHA-256 (got %s); nothing was loaded" % h.hexdigest()
        )
    return dest


def convert(zip_path, task, out_path, tmp):
    """Verified upstream zip -> one plain file (state dict + the numbers of plans.json) that ``weights_only=True``
    can read. Only called on a zip whose SHA-256 matched ``SHA256``."""
    import torch

    base = FOLDERS[task] + "/" + TRAINER
    with zipfile.ZipFile(zip_path) as z:
        plans = json.loads(z.read(base + "plans.json"))
        labels = json.loads(z.read(base + "dataset.json"))["labels"]
        ck = z.extract(base + "fold_all/checkpoint_final.pth", tmp)  # a seekable file: torch reads a zip stream slowly
    conf = plans["configurations"]["3d_fullres"]
    arch = conf["architecture"]
    kw = arch["arch_kwargs"]
    # The network is built by this module, never imported by a name found in the file: refuse anything else.
    expected = (
        arch["network_class_name"] == "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet"
        and kw["conv_op"] == "torch.nn.modules.conv.Conv3d"
        and kw["norm_op"] == "torch.nn.modules.instancenorm.InstanceNorm3d"
        and kw["nonlin"] == "torch.nn.LeakyReLU"
        and kw["dropout_op"] is None
        and conf["normalization_schemes"] == ["CTNormalization"]
        and list(conf["spacing"]) == [SPACING] * 3
        and plans["transpose_forward"] == [0, 1, 2]
        and len(labels) == len(NAMES[task]) + 1
    )
    if not expected:
        raise ValueError("The plans of task %d are not the ones this plugin was written for; nothing was loaded" % task)
    # nnU-Net checkpoints hold numpy objects and the trainer's arguments, so weights_only=True cannot read them. The
    # pickle comes from the zip whose hash was just verified; it is never loaded from anywhere else.
    state = torch.load(ck, map_location="cpu", weights_only=False)["network_weights"]
    os.remove(ck)
    intensity = plans["foreground_intensity_properties_per_channel"]["0"]
    model = {
        "state": dict(state),
        "patch": [int(p) for p in conf["patch_size"]],
        "classes": len(labels),
        "clip": [float(intensity["percentile_00_5"]), float(intensity["percentile_99_5"])],
        "mean": float(intensity["mean"]),
        "std": float(intensity["std"]),
        "features": [int(f) for f in kw["features_per_stage"]],
        "kernels": [[int(k) for k in ks] for ks in kw["kernel_sizes"]],
        "strides": [[int(s) for s in st] for st in kw["strides"]],
        "blocks": [int(b) for b in kw["n_blocks_per_stage"]],
        "decoder_convs": [int(c) for c in kw["n_conv_per_stage_decoder"]],
        "conv_bias": bool(kw["conv_bias"]),
        "norm_eps": float(kw["norm_op_kwargs"]["eps"]),
    }
    part = out_path + ".part"
    torch.save(model, part)
    os.replace(part, out_path)


def ensure_task(variant, task, progress):
    """The converted weights of one task in the cache: downloaded, verified and converted on first use."""
    folder = os.path.join(cache_dir(), variant)
    os.makedirs(folder, exist_ok=True)
    path = task_file(variant, task)
    if not os.path.exists(path):
        release, licence = VARIANTS[variant]
        with tempfile.TemporaryDirectory(dir=folder) as tmp:
            message = rp.tr("Downloading CADS task {task} weights ({release}, {licence}, 760 MB)", task=task,
                            release=release, licence=licence)
            z = fetch_zip(variant, task, os.path.join(tmp, "weights.zip"), lambda f: progress(0.8 * f, message))
            progress(0.8, rp.tr("Converting the weights of task {task} (once)", task=task))
            convert(z, task, path, tmp)
    return path


def load_model(variant, task, progress):
    """The network of one task, in eval mode, and its numbers. Downloads and converts on first use."""
    import torch
    import torch.nn as nn
    from dynamic_network_architectures.architectures.unet import ResidualEncoderUNet

    path = ensure_task(variant, task, progress)
    progress(0.9, rp.tr("Loading the model of task {task}", task=task))
    m = torch.load(path, map_location="cpu", weights_only=True)
    net = ResidualEncoderUNet(1, len(m["features"]), m["features"], nn.Conv3d, m["kernels"], m["strides"], m["blocks"],
                              m["classes"], m["decoder_convs"], m["conv_bias"], nn.InstanceNorm3d,
                              {"eps": m["norm_eps"], "affine": True}, None, None, nn.LeakyReLU, {"inplace": True},
                              deep_supervision=False)
    net.load_state_dict(m.pop("state"))
    net.eval()
    return net, m


# ---- geometry: series grid <-> RAS at 1.5 mm ----------------------------------------------------------------------


def ras_axes(volume):
    """For the output axes (S, A, R): which axis of ``volume.numpy()`` runs along it, and whether it runs backwards.

    The closest patient axis of each array axis, as nibabel's ``io_orientation`` does for CADS; a tilt is ignored, as
    CADS ignores it. Without a place in the patient the series is taken as axial, slices inferior to superior.
    """
    row, col, normal = volume.row or (1, 0, 0), volume.col or (0, 1, 0), volume.normal or (0, 0, 1)
    # Rows: array axes (z, y, x). Columns: components along (S, A, R); DICOM is L, P, S, so R = -L and A = -P.
    m = np.array([[v[2], -v[1], -v[0]] for v in (normal, col, row)], dtype=np.float64)
    order, flip, a = [0, 0, 0], [False, False, False], np.abs(m)
    for _ in range(3):
        i, j = np.unravel_index(np.argmax(a), a.shape)
        order[j], flip[j] = int(i), bool(m[i, j] < 0)
        a[i, :] = -1
        a[:, j] = -1
    return order, flip


def to_ras(a, order, flip):
    a = a.transpose(order)
    return a[tuple(slice(None, None, -1) if f else slice(None) for f in flip)]


def from_ras(a, order, flip):
    a = a[tuple(slice(None, None, -1) if f else slice(None) for f in flip)]
    return a.transpose(np.argsort(order))


def resample_in(a, spacing):
    """CADS ``change_spacing(order=3, dtype=np.int32)``: cubic ``zoom`` by spacing / 1.5, values truncated."""
    from scipy.ndimage import zoom

    r = zoom(a, [s / SPACING for s in spacing], order=3)
    return np.trunc(r, out=r)


def resample_out(lab, shape):
    """CADS ``change_spacing(target_shape=..., order=0)``."""
    from scipy.ndimage import zoom

    if lab.shape == tuple(shape):
        return lab
    return zoom(lab, [t / s for t, s in zip(shape, lab.shape)], order=0)


# ---- nnU-Net inference --------------------------------------------------------------------------------------------


def nonzero_box(a):
    """nnU-Net's ``crop_to_nonzero``: the box around the voxels that are not 0 (filling holes does not change it)."""
    box = []
    for axis in range(3):
        hit = np.flatnonzero((a != 0).any(axis=tuple(i for i in range(3) if i != axis)))
        box.append(slice(int(hit[0]), int(hit[-1]) + 1) if hit.size else slice(0, a.shape[axis]))
    return tuple(box)


def steps(size, patch, step):
    """nnU-Net's ``compute_steps_for_sliding_window`` for one axis."""
    target = patch * step
    n = int(np.ceil((size - patch) / target)) + 1 if size > patch else 1
    if n == 1:
        return [0]
    actual = (size - patch) / (n - 1)
    return [int(np.round(actual * i)) for i in range(n)]


def gaussian(patch):
    """nnU-Net's importance map: Gaussian, sigma = patch / 8, zeros lifted to the smallest value. nnU-Net also scales
    it and divides the sum by the summed weights: neither changes the argmax."""
    from scipy.ndimage import gaussian_filter

    tmp = np.zeros(patch)
    tmp[tuple(i // 2 for i in patch)] = 1
    g = gaussian_filter(tmp, [i / 8 for i in patch], 0, mode="constant", cval=0)
    g = (g / g.max()).astype(np.float32)
    g[g == 0] = g[g > 0].min()
    return g


def segment_array(predict, x, patch, classes, step, progress):
    """x: normalised (z, y, x) float32 -> uint8 labels, same shape. ``predict(tile)`` returns logits (C, z, y, x).

    Banded along z: only one window depth of logits is kept, so memory does not grow with the number of slices.
    """
    shape = x.shape
    pad = [max(0, p - s) for p, s in zip(patch, shape)]
    if any(pad):
        x = np.pad(x, [(p // 2, p - p // 2) for p in pad], mode="constant")  # nnU-Net: centred, 0 after normalising
    Z, Y, X = x.shape
    sz, sy, sx = steps(Z, patch[0], step), steps(Y, patch[1], step), steps(X, patch[2], step)
    w = gaussian(patch)
    dtype = np.float32 if classes * Y * X * patch[0] * 4 < 3 * 2**30 else np.float16
    buf = np.zeros((patch[0], classes, Y, X), dtype=dtype)  # z first so the band shifts by a view
    out = np.zeros((Z, Y, X), dtype=np.uint8)
    total, done = len(sz) * len(sy) * len(sx), 0
    for k, z0 in enumerate(sz):
        for y0 in sy:
            for x0 in sx:
                tile = np.ascontiguousarray(x[z0:z0 + patch[0], y0:y0 + patch[1], x0:x0 + patch[2]])
                logits = predict(tile)
                buf[:, :, y0:y0 + patch[1], x0:x0 + patch[2]] += (logits * w).transpose(1, 0, 2, 3).astype(dtype)
                done += 1
                progress(done / total)
        last = k == len(sz) - 1
        d = patch[0] if last else sz[k + 1] - z0
        out[z0:z0 + d] = buf[:d].argmax(axis=1).astype(np.uint8)
        if not last:
            buf[:patch[0] - d] = buf[d:]
            buf[patch[0] - d:] = 0
    return out[tuple(slice(p // 2, p // 2 + s) for p, s in zip(pad, shape))]


def run_task(hu, variant, task, step, progress):
    """hu: (z, y, x) = (S, A, R) at 1.5 mm, in HU -> uint8 labels of ``task`` on the same grid, not post-processed."""
    import torch

    net, m = load_model(variant, task, lambda f, msg: progress(0.1 * f, msg))
    cuda = torch.cuda.is_available()
    device = torch.device("cuda" if cuda else "cpu")
    net.to(device)

    def predict(tile):
        with torch.inference_mode(), torch.autocast("cuda", enabled=cuda):  # nnU-Net: mixed precision on CUDA only
            t = torch.from_numpy(tile)[None, None].to(device)
            return net(t)[0].float().cpu().numpy()

    box = nonzero_box(hu)
    lo, hi = m["clip"]
    x = ((np.clip(hu[box], lo, hi) - m["mean"]) / max(m["std"], 1e-8)).astype(np.float32)
    if cuda:
        message = rp.tr("Segmenting (CADS task {task}, GPU)", task=task)
    else:
        message = rp.tr("Segmenting (CADS task {task}, CPU, slow)", task=task)
    progress(0.1, message)
    out = np.zeros(hu.shape, dtype=np.uint8)
    out[box] = segment_array(predict, x, m["patch"], m["classes"], step, lambda f: progress(0.1 + 0.9 * f, message))
    return out


# ---- CADS post-processing -----------------------------------------------------------------------------------------


def fill_holes(lab, value):
    """TPTBox ``fill_holes_`` as CADS chains it: 3D, then slice by slice along S, R and A, then 3D again. Only
    background voxels change."""
    from scipy.ndimage import binary_fill_holes

    for axis in (None, 0, 2, 1, None):
        mask = lab == value
        if not mask.any():
            return
        if axis is None:
            filled = binary_fill_holes(mask)
        else:
            moved = np.moveaxis(mask, axis, 0)
            filled = np.moveaxis(np.stack([binary_fill_holes(s) for s in moved]), 0, axis)
        lab[filled & (lab == 0)] = value


def filter_components(lab, task):
    """CADS ``postprocess_seg_TPTBox``: per label, components (26-connected) by falling volume; the first one that is
    too small or beyond the allowed count goes, with every smaller one. In place."""
    from scipy.ndimage import find_objects, label

    for value, min_volume in MIN_VOLUME[task].items():
        if (task, value) in FILL_HOLES:
            fill_holes(lab, value)
        mask = lab == value
        if not mask.any():
            continue
        box = find_objects(mask.astype(np.uint8))[0]
        cc, n = label(mask[box], structure=np.ones((3, 3, 3)))
        volumes = np.bincount(cc.ravel(), minlength=n + 1)[1:]
        keep = []
        for rank, i in enumerate(np.argsort(-volumes, kind="stable")):
            if ((task, value) in ONE_COMPONENT and rank >= 1) or volumes[i] < min_volume:
                break
            keep.append(int(i) + 1)
        gone = (cc > 0) & ~np.isin(cc, keep)
        lab[box][gone] = 0
    return lab


def head_region(hu, variant, task, step, progress):
    """What upstream keeps of a head task (557, 558), as slices of the (z, y, x) grid, or None for nothing.

    ``postprocess_head`` / ``postprocess_head_and_neck``: a box around the centroid of the brain found by task 553;
    for 558 without a brain, everything from the lowest of the upper vertebrae of task 552 upwards. Upstream runs the
    head model first and blanks afterwards; the helper tasks run first here, so that "nothing" costs no head model.
    """
    from scipy.ndimage import center_of_mass

    brain = run_task(hu, variant, 553, step, lambda f, msg: progress(0.6 * f, msg)) == BRAIN
    if np.count_nonzero(brain) >= BRAIN_VOXELS:
        centre = [int(c) for c in center_of_mass(brain)]
        return tuple(slice(max(c - h, 0), min(c + h, n)) for c, h, n in zip(centre, HEAD_BOX[task], hu.shape))
    del brain
    if task != 558:
        return None
    spine = run_task(hu, variant, 552, step, lambda f, msg: progress(0.6 + 0.4 * f, msg))
    upper = ((spine >= UPPER_VERTEBRAE[0]) & (spine <= UPPER_VERTEBRAE[1])).any(axis=(1, 2))
    if not upper.any():
        return None
    return (slice(int(np.flatnonzero(upper)[0]), None), slice(None), slice(None))


# ---- entries ------------------------------------------------------------------------------------------------------


def task_file(variant, task):
    """Where the converted weights of one task live in the cache (they may not be there yet)."""
    return os.path.join(cache_dir(), variant, "task%d.pt" % task)


def segment(volume, ctx, task, variant, post, step):
    """``task``: 551-559. ``variant``: "open" or "research". ``post``: CADS post-processing. ``step``: window step as
    a fraction of the window (nnU-Net default 0.5)."""
    if volume.unit not in (None, "HU"):
        raise ValueError("This model needs a CT in Hounsfield units (the series is in %s)" % volume.unit)

    a = volume.numpy()  # (z, y, x) of the series
    if np.isnan(a).any():
        a = np.where(np.isnan(a), np.nanmin(a) if not np.isnan(a).all() else 0.0, a).astype(np.float32)
    ctx.progress(0.01, rp.tr("Preparing the volume at 1.5 mm"))
    order, flip = ras_axes(volume)
    ras = np.ascontiguousarray(to_ras(a, order, flip))
    spacing = [(volume.spacing[2], volume.spacing[1], volume.spacing[0])[i] for i in order]
    hu = resample_in(ras, spacing)
    grid = ras.shape
    del a, ras

    region, start, span = (slice(None),) * 3, 0.03, 0.94
    if post and task in HEAD_BOX:
        # The helper models take the first half of the bar; a third one (552) is rare.
        region = head_region(hu, variant, task, step, lambda f, msg: ctx.progress(0.03 + 0.47 * f, msg))
        start, span = 0.5, 0.47
    lab = np.zeros(hu.shape, dtype=np.uint8)
    if region is not None:
        full = run_task(hu, variant, task, step, lambda f, msg: ctx.progress(start + span * f, msg))
        lab[region] = full[region]
        del full
    del hu
    if post and task in MIN_VOLUME:
        ctx.progress(0.97, rp.tr("Post-processing"))
        filter_components(lab, task)

    ctx.progress(0.98, rp.tr("Back to the series grid"))
    out = from_ras(resample_out(lab, grid), order, flip)
    return np.ascontiguousarray(out).astype(np.uint8), NAMES[task]

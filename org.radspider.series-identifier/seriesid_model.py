"""The dcm-classifier MR model for org.radspider.series-identifier: numpy + onnxruntime, no radspider_plugin.

dcm-classifier (BRAINSia, Apache-2.0, copyright 2024 Michal Brzus and Hans J. Johnson) ships a one-vs-rest random
forest exported with skl2onnx: input `float_input` float [N, 28] (the columns of `seriesid_rules.FEATURES`), outputs
`output_label` and `output_probability` (one map class index -> probability per row). The file is the one of commit
5dcb37384572416da806db69c90bbabcec9819c9, checked against a pinned SHA-256 before it is loaded.

numpy and onnxruntime are imported when the model is first used, so this module imports without them.
"""

import hashlib
import os
import threading
import urllib.error
import urllib.request

URL = (
    "https://raw.githubusercontent.com/BRAINSia/dcm-classifier/5dcb37384572416da806db69c90bbabcec9819c9/"
    "src/dcm_classifier/models/ova_rf_classifier.onnx"
)
SHA256 = "808fcd58e237ecc3fa657942d325c12ddbbaaf496cc1f849913e99248cba13e0"
FILE = "ova_rf_classifier.onnx"
ENV_MODEL, ENV_DIR = "RADSPIDER_SERIES_ID_MODEL", "RADSPIDER_SERIES_ID_DIR"

# image_type_inference.py:37-48 imagetype_to_integer_mapping, by class index.
CLASSES = ("t1w", "gret2star", "t2w", "flair", "b0", "tracew", "adc", "fa", "eadc", "dwig")
# image_type_inference.py:180 min_probability_threshold: a top probability below it is LOW_PROBABILITY (:428-429).
LOW_PROBABILITY = 0.4
N_FEATURES = 28

_lock = threading.Lock()
_session = None


class Unavailable(ValueError):
    """The model cannot run; the message says why, for the user."""


def cache_dir():
    d = os.environ.get(ENV_DIR) or os.path.join(os.path.expanduser("~"), ".cache", "radspider", "series-identifier")
    os.makedirs(d, exist_ok=True)
    return d


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _offline_hint():
    return "Offline: download %s elsewhere and set %s=<that file>" % (URL, ENV_MODEL)


def model_path(progress):
    """Path of the verified model file: `RADSPIDER_SERIES_ID_MODEL`, else the cache, else a download to the cache.

    `progress(fraction)` is called while downloading (it may be None). Raises `Unavailable`.
    """
    local = os.environ.get(ENV_MODEL)
    if local:
        if not os.path.isfile(local):
            raise Unavailable("%s is set but %s does not exist" % (ENV_MODEL, local))
        got = sha256_of(local)
        if got != SHA256:
            # The user's own file is never deleted.
            raise Unavailable("%s (from %s) does not match the pinned SHA-256: expected %s, got %s; it was not loaded"
                              % (local, ENV_MODEL, SHA256, got))
        return local
    try:
        d = cache_dir()
    except OSError as e:
        raise Unavailable("Cannot create the model folder (%s). Set %s to a writable folder" % (e, ENV_DIR)) from e
    path = os.path.join(d, FILE)
    if os.path.isfile(path):
        if sha256_of(path) == SHA256:
            return path
        _remove(path)  # damaged or stale: fetched again below
    part = path + ".part"
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(URL, timeout=60) as r, open(part, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or 0), 0
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                h.update(chunk)
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(1.0, done / total))
    except (OSError, ValueError) as e:  # URLError, timeouts and disk errors are OSError
        _remove(part)
        raise Unavailable("Could not download the dcm-classifier model (%s). %s" % (e, _offline_hint())) from e
    got = h.hexdigest()
    if got != SHA256:
        _remove(part)
        raise Unavailable("The downloaded dcm-classifier model does not match the pinned SHA-256: expected %s, got %s;"
                          " it was deleted. %s" % (SHA256, got, _offline_hint()))
    os.replace(part, path)
    return path


def _load(progress):
    global _session
    with _lock:
        if _session is None:
            try:
                import onnxruntime
            except ImportError as e:
                raise Unavailable("onnxruntime is not installed (%s)" % e) from e
            path = model_path(progress)
            try:
                _session = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
            except Exception as e:
                raise Unavailable("onnxruntime could not load %s (%s)" % (path, e)) from e
        return _session


def predict(vector, progress=None):
    """(class, probability) for the 10 classes, highest first, from one 28-value `seriesid_rules.features` vector.

    As image_type_inference.py:400-421: float32 [1, 28] input, probabilities from `output_probability[0]`.
    """
    if len(vector) != N_FEATURES:
        raise ValueError("expected %d features, got %d" % (N_FEATURES, len(vector)))
    try:
        import numpy as np
    except ImportError as e:
        raise Unavailable("numpy is not installed (%s)" % e) from e
    session = _load(progress)
    x = np.asarray([vector], dtype=np.float32)
    outputs = [o.name for o in session.get_outputs()]
    _, probabilities = session.run(outputs[:2], {session.get_inputs()[0].name: x})
    pairs = [(CLASSES[int(k)], float(p)) for k, p in probabilities[0].items()]
    pairs.sort(key=lambda kv: (-kv[1], CLASSES.index(kv[0])))
    return pairs

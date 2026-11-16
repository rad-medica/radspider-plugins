"""Series identifier: what the image on screen is, its plane or projection, and what both mean.

The rules (seriesid_rules, every modality) answer first; on MR the dcm-classifier model (seriesid_model) adds a second
opinion that never replaces them and never fails the run. This module is the radspider_plugin layer only: it turns
the host's volume and context into plain values, and the findings into one window.
"""

import os

import radspider_plugin as rp
import seriesid_model as M
import seriesid_rules as R
import seriesid_tables as T

# Result and explanation ids come from the tables of seriesid_tables, not from literal calls, so the template
# generator cannot list them (this alias keeps it from warning about them). `python tools/series_identifier_template.py`
# runs the generator and appends them to lang/template.toml; tools/test_series_identifier.py checks that it did.
_tr_id = rp.tr

_NONE = "—"
_ND_PREFIX = "not determined:"  # the prefix of every "not determined" result id of seriesid_tables
_MAX_ARG = 1000  # the SDK's limit for a text argument


def _series_dict(series):
    """ctx.series (rp.SeriesFacts or None) as the dict seriesid_rules expects."""
    if series is None:
        return None
    return {
        "modality": series.modality, "images": series.images, "frames": series.frames, "phases": series.phases,
        "phase_axis": series.phase_axis, "b_values": list(series.b_values),
        "gradient_directions": series.gradient_directions, "image_types": list(series.image_types),
    }


def _first(vectors):
    return vectors[0] if vectors else None


def _show(v):
    """A tag value as data for a cell: numbers as written, lists backslash-joined, absent as a dash."""
    if v is None:
        return _NONE
    if isinstance(v, (list, tuple)):
        return "\\".join(_show(x) for x in v) if v else _NONE
    if isinstance(v, float):
        return "%g" % v
    s = str(v).strip()
    return s or _NONE


def _item_label(item):
    return {
        "series": rp.tr("Series"), "plane": rp.tr("Plane"), "projection": rp.tr("Projection"),
        "region": rp.tr("Region"), "laterality": rp.tr("Laterality"), "contrast": rp.tr("Contrast"),
        "model": rp.tr("Model (MR)"),
    }[item]


def _result(f):
    # Arguments are tag text (agent, kernel, units, code, body part): up to 1024 characters, more than the SDK takes.
    return _tr_id(f.result, **{k: v[:_MAX_ARG] for k, v in f.args})


_SAMPLE_PIXELS = 200_000  # pure-Python path: at most this many pixels, evenly strided


def _chroma_fraction(rgb):
    """Fraction of pixels whose chroma (max - min of R, G, B) is above T.US_CHROMA_MIN.

    `rgb` is what volume.rgb() returns: a uint8 (rows, columns, 3) array, or the raw R G B bytes without numpy.
    """
    if isinstance(rgb, (bytes, bytearray, memoryview)):
        data = bytes(rgb)
        n = len(data) // 3
        if n == 0:
            return 0.0
        step = max(1, n // _SAMPLE_PIXELS)
        stride = 3 * step
        r, g, b = data[0::stride], data[1::stride], data[2::stride]
        count = min(len(r), len(g), len(b))
        coloured = sum(1 for i in range(count)
                       if max(r[i], g[i], b[i]) - min(r[i], g[i], b[i]) > T.US_CHROMA_MIN)
        return coloured / count if count else 0.0
    import numpy as np

    a = np.asarray(rgb).reshape(-1, 3)
    if a.shape[0] == 0:
        return 0.0
    chroma = a.max(axis=1).astype(np.int16) - a.min(axis=1).astype(np.int16)
    return float(np.count_nonzero(chroma > T.US_CHROMA_MIN)) / a.shape[0]


def _colour(volume):
    """(image is colour, evidence). Greyscale stored as RGB / YBR is greyscale; unreadable colour data never fails
    the run."""
    try:
        rgb = volume.rgb()
        if rgb is None:
            return False, "image is greyscale"
        fraction = _chroma_fraction(rgb)
    except Exception as e:
        return False, "colour data unreadable (%s: %s); read as greyscale" % (type(e).__name__, e)
    share = "%.2f %% of pixels with chroma above %d" % (100 * fraction, T.US_CHROMA_MIN)
    if fraction > T.US_COLOUR_FRACTION:
        return True, "image stored as colour; " + share
    return False, "image stored as colour, pixels grey; " + share


def _will_download():
    """The model file is neither given (RADSPIDER_SERIES_ID_MODEL) nor cached: running it downloads it first."""
    if os.environ.get(M.ENV_MODEL):
        return False
    try:
        return not os.path.isfile(os.path.join(M.cache_dir(), M.FILE))
    except OSError:
        return False  # seriesid_model reports the unusable folder itself


def _not_run(reason):
    """The model row when the model did not run, for a free-text reason (seriesid_model.Unavailable, an error)."""
    return rp.tr("model not run: {reason}", reason=reason[:_MAX_ARG])


def _refused(reason):
    """The model row for a refusal of seriesid_rules.features: "<field> missing" or "<field> not a number"."""
    if reason.endswith(" missing"):
        return rp.tr("model not run: {field} missing", field=reason[:-len(" missing")])
    if reason.endswith(" not a number"):
        return rp.tr("model not run: {field} is not a number", field=reason[:-len(" not a number")])
    return _not_run(reason)


def _verdict_text(verdict, label, p):
    if verdict == "unreliable":
        return rp.tr("{label} · unreliable: no standard b-value", label=label)
    if verdict == "no_class":
        return rp.tr("{label} {p} · no model class for this series type", label=label, p=p)
    if verdict == "low":
        return rp.tr("{label} {p} · low probability", label=label, p=p)
    if verdict == "agrees":
        return rp.tr("{label} {p} · agrees", label=label, p=p)
    if verdict == "differs":
        return rp.tr("{label} {p} · differs from the rules", label=label, p=p)
    return rp.tr("{label} {p}", label=label, p=p)


def _model(volume, ctx, findings, series, has_geometry, b_value):
    """(model row text, Model detail blocks). Never raises: a failure becomes the row text."""
    detail = []
    try:
        vector, refusal = R.features(volume.tags, has_geometry, volume.spacing_source == "pixel")
        if vector is None:
            return _refused(refusal), detail
        rows = [[rp.tr("Feature"), rp.tr("Value"), rp.tr("Tag"), rp.tr("Source")]]
        for name, value in zip(R.FEATURES, vector):
            tag = R.FEATURE_TAGS[name]
            source = volume.tag_source(tag.lower()) if tag else None
            rows.append([name, "%g" % value, tag or _NONE, source or _NONE])
        features_table = rp.Table(rows)
        progress = None
        if _will_download():
            message = rp.tr("Downloading the MR model (305 KB)…")
            ctx.progress(0.2, message)

            def progress(fraction):
                ctx.progress(0.2 + 0.7 * fraction, message)

        try:
            pairs = M.predict(vector, progress)
        except M.Unavailable as e:
            detail.append(features_table)
            return _not_run(str(e)), detail
        raw, p = pairs[0]
        label = R.series_class(raw, series)
        kind = R.mr_kind(findings)
        verdict = R.model_verdict(kind, b_value, label, p, M.LOW_PROBABILITY)
        if verdict == "unreliable":  # spec call 5: no probability when four features are blind
            detail.append(rp.Label(rp.tr("Probabilities not shown: without the standard b-value (0018,9087), four of "
                                         "the 28 features are blind."), weak=True))
        else:
            top = [[rp.tr("Class"), rp.tr("Probability")]] + [[c, "%.2f" % q] for c, q in pairs[:3]]
            detail.append(rp.Table(top))
        if label != raw:
            detail.append(rp.Label(rp.tr("The series has a b-value above 0, so {before} becomes {after}, as the "
                                         "reference does.", before=raw, after=label), weak=True))
        detail.append(features_table)
        return _verdict_text(verdict, label, "%.2f" % p), detail
    except Exception as e:  # the model is a second opinion: whatever breaks it, the rules still answer
        return _not_run("%s: %s" % (type(e).__name__, e)), detail


@rp.tool("identify")
def identify(volume, ctx):
    series = _series_dict(ctx.series)
    tags = {str(k).lower(): v for k, v in volume.tags.items()}
    row, col = _first(volume.slice_rows), _first(volume.slice_cols)
    # Chroma is read for ultrasound only (colour Doppler); every other modality skips the pixel read.
    is_us = R.text((series or {}).get("modality")) == "US"
    findings = R.identify(tags, series, row, col, *(_colour(volume) if is_us else (False, None)))

    modality = (series or {}).get("modality")
    for f in findings:
        if f.result == T.MODALITY_INFERRED:
            modality = dict(f.args).get("modality")
    header = [rp.Label(modality or _NONE)]
    header += [rp.Label(_result(f)) for f in findings if f.item == "region" and not f.result.startswith(_ND_PREFIX)]
    header.append(rp.Button("refresh", rp.tr("Refresh"), icon="arrow-clockwise"))

    rows = [[rp.tr("Item"), rp.tr("Result"), rp.tr("Evidence")]]
    rows += [[_item_label(f.item), _result(f), f.evidence] for f in findings]
    explain = [rp.Label(_tr_id(R.EXPLAIN[eid])) for eid in dict.fromkeys(e for f in findings for e in f.explain)]
    model = None
    if R.is_mr(findings, series):
        # After the rules: an offline user still sees them, whatever the model does.
        text, detail = _model(volume, ctx, findings, series, row is not None and col is not None,
                              tags.get(R.B_VALUE.lower()))
        rows.append([_item_label("model"), text, "dcm-classifier (Apache-2.0), 28 header values"])
        explain.append(rp.Label(rp.tr("Model (MR): dcm-classifier, a random forest over 28 header values trained "
                                      "on brain MR, gives a second opinion on the sequence class. It is not ground "
                                      "truth: when it differs from the rules, either may be wrong.")))
        model = rp.Section(rp.tr("Model detail"), detail or [rp.Label(text, weak=True)], open=False)

    read = [[rp.tr("Tag"), rp.tr("Name"), rp.tr("Value"), rp.tr("Source")]]
    for tag, name in R.TAGS.items():
        key = tag.lower()
        read.append([tag, name, _show(tags.get(key)), volume.tag_source(key) or _NONE])
    blocks = [
        rp.Row(header),
        rp.Table(rows),
        rp.Section(rp.tr("What this means"), explain, open=True),
        model,
        rp.Section(rp.tr("Tags read"), [rp.Table(read)], open=False),
        rp.Label(rp.tr("Educational aid; not for diagnosis."), weak=True),
    ]
    return rp.Result(windows=[rp.Window("main", None, [b for b in blocks if b is not None])])

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
# generator cannot list them; lang/es.toml carries them and tools/test_series_identifier.py checks that it does.
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
    return _tr_id(f.result, **dict(f.args))


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
    return rp.tr("Model not run: {reason}", reason=reason[:_MAX_ARG])


def _refused(reason):
    """The model row for a refusal of seriesid_rules.features: "<field> missing" or "<field> not a number"."""
    if reason.endswith(" missing"):
        return rp.tr("Model not run: {field} missing", field=reason[:-len(" missing")])
    if reason.endswith(" not a number"):
        return rp.tr("Model not run: {field} is not a number", field=reason[:-len(" not a number")])
    return _not_run(reason)


def _verdict_text(verdict, label, p):
    if verdict == "unreliable":
        return rp.tr("{label} · unreliable: no standard b-value", label=label)
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
    findings = R.identify(tags, series, row, col, volume.rgb() is not None)

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

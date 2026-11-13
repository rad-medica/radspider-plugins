"""pyradiomics feature extraction per segment, with the options of 3D Slicer's SlicerRadiomics extension.

The tool is interactive: the first run only draws the controls, a control change redraws them, and the features
are computed on the run the *Extract* button asks for (a wavelet run takes minutes: it must not start on every
checkbox click). Each run is a new process, so nothing is kept between runs: the table belongs to the Extract
run that made it.
"""

import numpy as np

import radspider_plugin as rp

# The classes SlicerRadiomics lists, in pyradiomics' output order; shape2D is left out (it needs force2D).
CLASSES = ["shape", "firstorder", "glcm", "gldm", "glrlm", "glszm", "ngtdm"]
CLASS_LABELS = {
    "firstorder": "First order",
    "shape": "Shape (3D)",
    "glcm": "GLCM",
    "glrlm": "GLRLM",
    "glszm": "GLSZM",
    "gldm": "GLDM",
    "ngtdm": "NGTDM",
}
ALL_SEGMENTS = "All segments"
LOG_FIELDS = ("log_sigma_1", "log_sigma_2", "log_sigma_3")


def _options(ctx, segment_names):
    """The window's values, with the defaults of SlicerRadiomics (only firstorder ticked, bin width 25, symmetric
    GLCM, no resampling, no filter). The All / None buttons overwrite the class boxes."""
    c = ctx.controls
    classes = {k: bool(c.get("class_" + k, k == "firstorder")) for k in CLASSES}
    if ctx.event == "all_classes":
        classes = dict.fromkeys(CLASSES, True)
    elif ctx.event == "no_classes":
        classes = dict.fromkeys(CLASSES, False)
    segment = c.get("segment", ALL_SEGMENTS)
    if segment not in segment_names:
        segment = ALL_SEGMENTS  # the segment was renamed or deleted since the window was drawn
    return {
        "segment": segment,
        "classes": classes,
        "bin_width": float(c.get("bin_width", 25.0)),
        "resample_mm": float(c.get("resample_mm", 0.0)),
        "symmetric_glcm": bool(c.get("symmetric_glcm", True)),
        "log_sigmas": [float(c.get(k, 0.0)) for k in LOG_FIELDS],
        "wavelet": bool(c.get("wavelet", False)),
    }


def _controls(o, segment_names):
    out = [rp.Choice("segment", "Segment", [ALL_SEGMENTS] + segment_names, o["segment"])]
    out += [rp.Checkbox("class_" + k, CLASS_LABELS[k], o["classes"][k]) for k in sorted(CLASSES)]
    out += [
        rp.Button("all_classes", "All classes"),
        rp.Button("no_classes", "No classes"),
        rp.Number("bin_width", "Bin width", o["bin_width"], min=0.01, max=10000.0, step=1.0,
                  help="Width of the grey-level bins, in the unit of the series (25 suits HU)"),
        rp.Number("resample_mm", "Resampled voxel size (mm, 0 = none)", o["resample_mm"], min=0.0, max=50.0, step=0.5,
                  help="Isotropic voxel size the image and the mask are resampled to before extraction"),
        rp.Checkbox("symmetric_glcm", "Symmetrical GLCM", o["symmetric_glcm"]),
    ]
    out += [
        rp.Number(k, "LoG kernel size %d (mm, 0 = off)" % (i + 1), o["log_sigmas"][i], min=0.0, max=50.0, step=0.5,
                  help="Sigma of a Laplacian of Gaussian filter; features are also computed on the filtered image")
        for i, k in enumerate(LOG_FIELDS)
    ]
    out += [
        rp.Checkbox("wavelet", "Wavelet features (8 decompositions, slow)", o["wavelet"]),
        rp.Button("extract", "Extract"),
    ]
    return out


def _unique_names(segments):
    """Column titles and choice texts: the segment names, numbered where two segments share one."""
    names, seen = [], {}
    for s in segments:
        base = (s.name or "Segment %d" % s.id)[:180]
        seen[base] = seen.get(base, 0) + 1
        names.append(base if seen[base] == 1 else "%s (%d)" % (base, seen[base]))
    return names


def _direction(volume):
    """ITK direction matrix (row-major, columns = axis directions) from the DICOM unit vectors. DICOM patient
    coordinates and ITK physical space are both LPS, so no flip is needed."""
    if volume.row is None or volume.col is None or volume.normal is None:
        return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    r, c, n = volume.row, volume.col, volume.normal
    return (r[0], c[0], n[0], r[1], c[1], n[1], r[2], c[2], n[2])


def _to_sitk(array, volume):
    """A SimpleITK image on the volume's grid. ``array`` is (slices, rows, columns), which is the (z, y, x) order
    ``GetImageFromArray`` expects, so x = columns runs along ``row`` and y = rows along ``col``."""
    import SimpleITK as sitk

    image = sitk.GetImageFromArray(array)
    image.SetSpacing(volume.spacing)
    image.SetOrigin(volume.origin if volume.origin is not None else (0.0, 0.0, 0.0))
    image.SetDirection(_direction(volume))
    return image


def _extractor(o):
    from radiomics import featureextractor

    settings = {
        "binWidth": o["bin_width"],
        "symmetricalGLCM": o["symmetric_glcm"],
        "correctMask": True,  # SlicerRadiomicsCLI sets it; image and mask share a grid here, so it never acts
        "label": 1,
    }
    if o["resample_mm"] > 0:
        settings["resampledPixelSpacing"] = [o["resample_mm"]] * 3
    extractor = featureextractor.RadiomicsFeatureExtractor(**settings)
    image_types = {"Original": {}}
    sigmas = [s for s in o["log_sigmas"] if s > 0]
    if sigmas:
        image_types["LoG"] = {"sigma": sigmas}
    if o["wavelet"]:
        image_types["Wavelet"] = {}
    extractor.enableImageTypes(**image_types)
    extractor.disableAllFeatures()
    for k in CLASSES:
        if o["classes"][k]:
            extractor.enableFeatureClassByName(k)
    return extractor


def _cell(value):
    """A table cell: numbers as float, everything else (versions, settings, tuples) as text."""
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    if isinstance(value, np.ndarray) and value.size == 1:
        return _cell(value.reshape(-1)[0])
    if isinstance(value, (complex, np.complexfloating)) and value.imag == 0:
        # The shape axis lengths come from numpy's general eigenvalue solver, which this pyradiomics returns as
        # complex with a zero imaginary part ("(67.99+0j)"); the number is the real part.
        return float(value.real)
    return str(value)


def _table(columns, results):
    """Feature rows × segment columns. Rows keep pyradiomics' order (diagnostics first); a feature a segment
    lacks (its extraction failed) is an empty cell."""
    keys = []
    seen = set()
    for r in results:
        for k in r:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return [["Feature"] + columns] + [[k] + [_cell(r[k]) if k in r else "" for r in results] for k in keys]


@rp.tool("radiomics")
def radiomics(volume, ctx):
    segments = ctx.segments or []
    if not segments:
        raise ValueError("No segments: segment a structure first")
    # The host allows 256 options per choice; "All segments" takes one.
    names = _unique_names(segments)
    choice_names = names[:255]
    o = _options(ctx, choice_names)
    controls = _controls(o, choice_names)
    enabled = [k for k in CLASSES if o["classes"][k]]

    if ctx.event != "extract":
        return rp.Result(
            controls=controls,
            message="%d segment(s). Choose the feature classes and options, then press Extract." % len(segments),
        )
    if not enabled:
        raise ValueError("No feature class selected: tick at least one, then press Extract")

    import logging

    import radiomics as pyradiomics

    pyradiomics.setVerbosity(logging.WARNING)  # warnings go to the plugin log (stderr)
    picked = [(n, s) for n, s in zip(names, segments) if o["segment"] in (ALL_SEGMENTS, n)]
    values = volume.numpy().astype(np.float64)
    has_data = np.isfinite(values)
    if not has_data.any():
        raise ValueError("The series has no voxel with data")
    if not has_data.all():
        # NaN = no data. Filters (LoG, wavelet) read the whole crop, so NaN gets the lowest value (air on CT)
        # and those voxels leave every mask below.
        values[~has_data] = values[has_data].min()
    image = _to_sitk(values, volume)
    extractor = _extractor(o)

    results, failed = [], []
    for i, (name, segment) in enumerate(picked):
        ctx.progress(i / len(picked), "%s (%d of %d)" % (name, i + 1, len(picked)))
        mask = segment.mask() & has_data
        try:
            if not mask.any():
                raise ValueError("the segment is empty")
            results.append(extractor.execute(image, _to_sitk(mask.astype(np.uint8), volume)))
        except ValueError as e:
            # pyradiomics refuses masks it cannot use (one voxel, flat in one direction, too small after
            # resampling) with a ValueError. One unusable segment should not cost the others their columns.
            results.append({"extraction_Error": str(e)})
            failed.append("%s: %s" % (name, e))
    ctx.progress(1.0, "Done")
    if len(failed) == len(picked):
        raise ValueError("No features extracted. " + "; ".join(failed))

    table = _table([n for n, _ in picked], results)
    n_features = sum(1 for row in table[1:] if not row[0].startswith(("diagnostics_", "extraction_")))
    message = "pyradiomics %s: %d features × %d segment(s), classes %s." % (
        pyradiomics.__version__, n_features, len(picked) - len(failed), ", ".join(enabled),
    )
    if failed:
        message += " Failed: " + "; ".join(failed)
    return rp.Result(table=table, controls=controls, message=message)

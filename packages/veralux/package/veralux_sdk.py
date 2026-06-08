# SPDX-License-Identifier: GPL-3.0-or-later
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz

"""Shared AfterNight SDK helpers for the VeraLux suite adapters."""

from __future__ import annotations

import math

import numpy as np

import afternight


def read_image(image_handle):
    """Return an SDK image handle as a NumPy array without changing layout."""

    if not hasattr(image_handle, "to_numpy"):
        raise TypeError("VeraLux expected an AfterNight ImageHandle with to_numpy()")
    return np.asarray(image_handle.to_numpy())


def write_image(image_handle, array):
    """Write a float32 NumPy result into an SDK image handle."""

    if not hasattr(image_handle, "from_numpy"):
        raise TypeError("VeraLux expected an AfterNight ImageHandle with from_numpy()")

    data = np.asarray(array)
    destination_dtype = None
    if hasattr(image_handle, "to_numpy"):
        try:
            destination_dtype = np.asarray(image_handle.to_numpy()).dtype
        except Exception:
            destination_dtype = None

    if destination_dtype is not None and np.issubdtype(destination_dtype, np.integer):
        info = np.iinfo(destination_dtype)
        data_float = np.nan_to_num(data.astype(np.float32, copy=False), nan=0.0, posinf=1.0, neginf=0.0)
        if np.issubdtype(destination_dtype, np.unsignedinteger):
            # Match AfterNight's native float-to-integer converters and the
            # original VeraLux preview display path, both of which truncate.
            data = (np.clip(data_float, 0.0, 1.0) * float(info.max)).astype(destination_dtype)
        else:
            data = np.rint(np.clip(data_float, float(info.min), float(info.max))).astype(destination_dtype)
    else:
        data = np.asarray(data, dtype=np.float32)

    image_handle.from_numpy(data)


def first_mask_array(masks):
    """Return the first optional mask as float32, accepting handles or arrays."""

    if not masks:
        return None
    if isinstance(masks, dict):
        first_mask = next(iter(masks.values()), None)
    else:
        first_mask = masks[0]
    if first_mask is None:
        return None
    if hasattr(first_mask, "to_numpy"):
        return np.asarray(first_mask.to_numpy(), dtype=np.float32)
    return np.asarray(first_mask, dtype=np.float32)


def stamp_result(
    image_handle,
    *,
    extension_id,
    tool_name,
    upstream_version,
    attribution,
    extra_metadata=None,
):
    """Apply common VeraLux result metadata to an SDK image handle."""

    image_handle.set_metadata("afternight.extension", extension_id)
    image_handle.set_metadata("veralux.tool", tool_name)
    image_handle.set_metadata("veralux.upstream_version", upstream_version)
    image_handle.set_metadata("veralux.attribution", attribution)
    for key, value in dict(extra_metadata or {}).items():
        image_handle.set_metadata(str(key), str(value))


def _metadata_dict(image_handle):
    try:
        return dict(getattr(image_handle, "metadata", {}) or {})
    except Exception:
        return {}


def _channel_count(image_handle):
    try:
        properties = dict(getattr(image_handle, "properties", {}) or {})
        if "channels" in properties:
            return int(properties["channels"])
    except Exception:
        pass

    try:
        data = np.asarray(image_handle.to_numpy())
    except Exception:
        return 0

    if data.ndim < 3:
        return 1
    if data.shape[0] in (1, 3, 4) and data.shape[-1] not in (1, 3, 4):
        return int(data.shape[0])
    return int(data.shape[-1])


def _nonlinear_channel_basis(image_handle):
    metadata_basis = str(_metadata_dict(image_handle).get("ANBASIS", "")).strip().lower()
    channels = _channel_count(image_handle)

    if channels == 1:
        return "monochrome"
    if channels >= 3:
        return "display-rgb"
    if metadata_basis in {"raw-cfa", "linear-rgb", "camera-rgb", "display-rgb", "monochrome"}:
        return "display-rgb" if metadata_basis in {"linear-rgb", "camera-rgb"} else metadata_basis
    return "unknown"


def mark_result_nonlinear(image_handle, operation):
    """Mark an applied VeraLux result as display/non-linear AfterNight image data."""

    image_handle.set_metadata("ANSTVER", "1")
    image_handle.set_metadata("ANLIN", "nonlinear")
    image_handle.set_metadata("ANBASIS", _nonlinear_channel_basis(image_handle))
    image_handle.set_metadata("ANASRC", "process")
    image_handle.set_metadata("ANOP", str(operation))


def log_info(message, *, component):
    afternight.log_info(str(message), component=str(component))


def log_warning(message, *, component):
    afternight.log_warning(str(message), component=str(component))


def log_launch_banner(tool_name, subtitle, *, version=None, component, include_contact=True):
    title = f"# VeraLux - {tool_name}"
    if version:
        title = f"{title} v{version}"
    lines = [
        "",
        "##############################################",
        title,
        f"# {subtitle}",
        "# Author: Riccardo Paterniti (2025)",
    ]
    if include_contact:
        lines.append("# Contact: info@veralux.space")
    lines.append("##############################################")
    log_info("\n".join(lines), component=component)


def warn_quality_fallbacks_once(owner, messages, *, component):
    """Log each quality-fallback warning once for a process instance."""

    warnings = tuple(str(message) for message in (messages or ()) if str(message).strip())
    if not warnings:
        return

    seen = getattr(owner, "_veralux_quality_fallback_warnings", None)
    if seen is None:
        seen = set()
        setattr(owner, "_veralux_quality_fallback_warnings", seen)

    for message in warnings:
        if message in seen:
            continue
        log_warning(message, component=component)
        seen.add(message)


def migrate_settings(params, *, defaults, aliases=None):
    """Merge params with defaults and simple old-name aliases."""

    source = dict(params or {})
    migrated = {}
    for key, default in dict(defaults or {}).items():
        if key in source:
            migrated[key] = source[key]
            continue
        value = default
        for alias in tuple(dict(aliases or {}).get(key, ())):
            if alias in source:
                value = source[alias]
                break
        migrated[key] = value
    return migrated


def downsample_for_preview(array, *, max_dimension=512):
    """Return a deterministic nearest-neighbor preview array."""

    data = np.asarray(array)
    if data.ndim < 2:
        return np.asarray(data, dtype=np.float32)
    max_dimension = int(max(1, max_dimension))
    largest = max(int(data.shape[0]), int(data.shape[1]))
    if largest <= max_dimension:
        return np.asarray(data, dtype=np.float32)
    step = int(math.ceil(largest / float(max_dimension)))
    return np.asarray(data[::step, ::step, ...], dtype=np.float32)


def autostretch_preview(array, *, low_percentile=0.5, high_percentile=99.5):
    """Apply a lightweight linked stretch for preview-only display arrays."""

    data = np.nan_to_num(np.asarray(array, dtype=np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    if data.size == 0:
        return data
    low = float(np.percentile(data, float(low_percentile)))
    high = float(np.percentile(data, float(high_percentile)))
    if high <= low + 1e-8:
        return np.clip(data, 0.0, 1.0).astype(np.float32, copy=False)
    return np.clip((data - low) / (high - low), 0.0, 1.0).astype(np.float32, copy=False)


def _star_value(star, key, default):
    if isinstance(star, dict):
        return star.get(key, default)
    return getattr(star, key, default)


def _star_value_any(star, keys, default):
    for key in tuple(keys):
        value = _star_value(star, key, None)
        if value is not None:
            return value
    return default


def _image_plane_shape(image_handle):
    data = read_image(image_handle)
    if data.ndim < 2:
        raise ValueError("VeraLux star-mask construction requires at least a 2D image")
    if data.ndim == 3 and data.shape[0] in (1, 3) and data.shape[-1] not in (1, 3):
        return int(data.shape[1]), int(data.shape[2])
    return int(data.shape[0]), int(data.shape[1])


def star_mask_from_find_stars(
    image_handle,
    *,
    finder=None,
    max_stars=512,
    radius_scale=2.5,
    min_radius=2.0,
    max_radius=12.0,
    params=None,
):
    """Build a soft star mask from ``afternight.registration.find_stars()`` output."""

    if finder is None:
        from afternight import registration

        finder = registration.find_stars

    height, width = _image_plane_shape(image_handle)
    mask = np.zeros((height, width), dtype=np.float32)
    stars = finder(image_handle, max_stars=int(max_stars), params=dict(params or {}))
    if not stars:
        return mask

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    radius_scale = float(radius_scale)
    min_radius = float(min_radius)
    max_radius = float(max_radius)
    for star in stars:
        x = float(_star_value(star, "x", -1.0))
        y = float(_star_value(star, "y", -1.0))
        if x < 0.0 or y < 0.0 or x >= width or y >= height:
            continue
        fwhm = float(_star_value(star, "fwhm", min_radius))
        radius = float(np.clip(max(fwhm, min_radius) * radius_scale, min_radius, max_radius))
        sigma = max(radius / 2.0, 1e-3)
        star_mask = np.exp(-(((xx - x) ** 2) + ((yy - y) ** 2)) / (2.0 * sigma * sigma))
        mask = np.maximum(mask, star_mask.astype(np.float32, copy=False))
    return np.clip(mask, 0.0, 1.0).astype(np.float32, copy=False)


def star_mask_and_median_fwhm_from_find_stars(
    image_handle,
    *,
    finder=None,
    max_stars=512,
    radius_scale=1.8,
    min_radius=3.0,
    max_radius=24.0,
    params=None,
):
    """Build Nox's PSF-style star veto mask plus a median FWHM estimate."""

    if finder is None:
        from afternight import registration

        finder = registration.find_stars

    height, width = _image_plane_shape(image_handle)
    mask = np.zeros((height, width), dtype=np.float32)
    stars = finder(image_handle, max_stars=int(max_stars), params=dict(params or {}))
    if not stars:
        return mask, 4.0

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    fwhm_values = []
    radius_scale = float(radius_scale)
    min_radius = float(min_radius)
    max_radius = float(max_radius)
    for star in stars:
        x = float(_star_value_any(star, ("x", "X"), -1.0))
        y = float(_star_value_any(star, ("y", "Y"), -1.0))
        if x < 0.0 or y < 0.0 or x >= width or y >= height:
            continue
        fwhm_x = float(_star_value_any(star, ("FWHMx", "fwhm_x", "fwhmx", "fwhm"), min_radius))
        fwhm_y = float(_star_value_any(star, ("FWHMy", "fwhm_y", "fwhmy", "fwhm"), fwhm_x))
        fwhm_x = max(fwhm_x, 1.0)
        fwhm_y = max(fwhm_y, 1.0)
        fwhm = (fwhm_x + fwhm_y) * 0.5
        fwhm_values.append(fwhm)
        radius = fwhm * radius_scale
        axis_a = float(_star_value_any(star, ("A", "a", "major_axis", "major"), fwhm))
        axis_b = float(_star_value_any(star, ("B", "b", "minor_axis", "minor"), fwhm))
        if max(axis_a, axis_b) > 0.0:
            ba_ratio = min(axis_a, axis_b) / max(axis_a, axis_b)
            if ba_ratio < 0.3:
                radius *= 1.3
        magnitude = float(_star_value_any(star, ("Mag", "mag", "magnitude"), 0.0))
        if magnitude < -3.0:
            radius *= 1.4
        radius = float(np.clip(max(radius, min_radius), min_radius, max_radius))

        cx = int(round(x))
        cy = int(round(y))
        rad = int(radius + 2.0)
        y0 = max(0, cy - rad)
        y1 = min(height, cy + rad + 1)
        x0 = max(0, cx - rad)
        x1 = min(width, cx + rad + 1)
        if y0 >= y1 or x0 >= x1:
            continue
        local_y = yy[y0:y1, x0:x1]
        local_x = xx[y0:y1, x0:x1]
        theta = math.radians(float(_star_value_any(star, ("Angle", "angle"), 0.0)))
        c = math.cos(theta)
        sn = math.sin(theta)
        xx_rot = (local_x - x) * c - (local_y - y) * sn
        yy_rot = (local_x - x) * sn + (local_y - y) * c
        sx = max(fwhm_x / 2.355, 1e-3)
        sy = max(fwhm_y / 2.355, 1e-3)
        star_mask = np.exp(-0.5 * ((xx_rot / sx) ** 2 + (yy_rot / sy) ** 2))
        mask[y0:y1, x0:x1] = np.maximum(mask[y0:y1, x0:x1], star_mask.astype(np.float32, copy=False))

    if np.max(mask) > 0.0:
        mask /= np.max(mask)
    median_fwhm = float(np.median(fwhm_values)) if fwhm_values else 4.0
    return np.clip(mask, 0.0, 1.0).astype(np.float32, copy=False), max(median_fwhm, 1.0)


def star_mask_and_fwhm_map_from_find_stars(
    image_handle,
    *,
    finder=None,
    max_stars=512,
    radius_scale=1.8,
    min_radius=3.0,
    max_radius=24.0,
    params=None,
):
    """Build Silentium's PSF-style star mask plus local FWHM modulation map."""

    if finder is None:
        from afternight import registration

        finder = registration.find_stars

    height, width = _image_plane_shape(image_handle)
    mask = np.zeros((height, width), dtype=np.float32)
    fwhm_map = np.ones((height, width), dtype=np.float32) * 4.0
    stars = finder(image_handle, max_stars=int(max_stars), params=dict(params or {}))
    if not stars:
        return mask, fwhm_map

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    radius_scale = float(radius_scale)
    min_radius = float(min_radius)
    max_radius = float(max_radius)
    for star in stars:
        x = float(_star_value(star, "x", -1.0))
        y = float(_star_value(star, "y", -1.0))
        if x < 0.0 or y < 0.0 or x >= width or y >= height:
            continue
        fwhm = float(_star_value(star, "fwhm", min_radius))
        mask_fwhm = float(np.clip(fwhm * (radius_scale / 1.8), min_radius, max_radius))
        sigma = max(mask_fwhm / 2.355, 1e-3)
        star_mask = np.exp(-(((xx - x) ** 2) + ((yy - y) ** 2)) / (2.0 * sigma * sigma))
        mask = np.maximum(mask, star_mask.astype(np.float32, copy=False))

        influence_radius = max(1.5 * fwhm, 1e-3)
        distance = np.sqrt(((xx - x) ** 2) + ((yy - y) ** 2))
        weight = np.exp(-0.5 * (distance / influence_radius) ** 2)
        fwhm_map = np.minimum(fwhm_map, (fwhm * weight) + (0.1 * (1.0 - weight)))

    if np.max(mask) > 0.0:
        mask /= np.max(mask)
    return (
        np.clip(mask, 0.0, 1.0).astype(np.float32, copy=False),
        np.clip(fwhm_map, 0.1, 64.0).astype(np.float32, copy=False),
    )

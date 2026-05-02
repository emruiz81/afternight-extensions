# SPDX-License-Identifier: GPL-3.0-or-later
# AfterNight port Copyright (c) 2026 AfterNight contributors

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
    image_handle.from_numpy(np.asarray(array, dtype=np.float32))


def first_mask_array(masks):
    """Return the first optional mask as float32, accepting handles or arrays."""

    if not masks:
        return None
    first_mask = masks[0]
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


def log_info(message, *, component):
    afternight.log_info(str(message), component=str(component))


def log_warning(message, *, component):
    afternight.log_warning(str(message), component=str(component))


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

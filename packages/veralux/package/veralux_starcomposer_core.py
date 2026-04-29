# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux StarComposer by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_StarComposer.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux StarComposer star-mask shaping core."""

from __future__ import annotations

import math

import numpy as np

try:
    from veralux_hypermetric_stretch_core import DEFAULT_PROFILE, SENSOR_PROFILES
except Exception:  # pragma: no cover - defensive for direct extraction.
    DEFAULT_PROFILE = "Rec.709 (Recommended)"
    SENSOR_PROFILES = {DEFAULT_PROFILE: {"weights": (0.2126, 0.7152, 0.0722)}}


UPSTREAM_VERSION = "2.1.0"


def normalize_input(image):
    img = np.asarray(image)
    input_dtype = img.dtype
    img_float = np.nan_to_num(img.astype(np.float32, copy=False), nan=0.0, posinf=1.0, neginf=0.0)
    if np.issubdtype(input_dtype, np.integer):
        if input_dtype == np.uint8:
            return img_float / 255.0
        if input_dtype == np.uint16:
            return img_float / 65535.0
        return img_float / float(np.iinfo(input_dtype).max)
    if np.issubdtype(input_dtype, np.floating):
        if img_float.size == 0:
            return img_float
        current_max = float(np.max(img_float))
        if current_max > 1.0 + 1e-5:
            if current_max <= 65535.0:
                return img_float / 65535.0
            return img_float / current_max
    return np.clip(img_float, 0.0, 1.0)


def _profile_weights(working_space):
    profile = SENSOR_PROFILES.get(str(working_space), SENSOR_PROFILES[DEFAULT_PROFILE])
    if isinstance(profile, dict):
        return tuple(profile["weights"])
    return tuple(profile)


def _to_chw_rgb(image):
    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim == 2:
        return np.stack([img, img, img]), "hw", None
    if img.ndim != 3:
        raise ValueError("VeraLux StarComposer expects a 2D mono or 3D RGB star mask")

    if img.shape[0] == 3 and img.shape[-1] not in (3, 4):
        return img[:3], "chw", None
    if img.shape[0] == 1 and img.shape[-1] not in (3, 4):
        mono = img[0]
        return np.stack([mono, mono, mono]), "chw_mono", None
    if img.shape[-1] >= 3:
        extras = img[..., 3:] if img.shape[-1] > 3 else None
        return np.moveaxis(img[..., :3], -1, 0), "hwc", extras
    if img.shape[-1] == 1:
        mono = img[..., 0]
        return np.stack([mono, mono, mono]), "hwc_mono", None
    raise ValueError("VeraLux StarComposer expects RGB images to have at least 3 channels")


def _from_chw_rgb(chw, layout, extras):
    out = np.clip(np.asarray(chw, dtype=np.float32), 0.0, 1.0)
    if layout == "chw":
        return out.astype(np.float32, copy=False)
    if layout == "chw_mono":
        return out[:1].astype(np.float32, copy=False)
    if layout == "hw":
        return out[0].astype(np.float32, copy=False)

    hwc = np.moveaxis(out, 0, -1)
    if layout == "hwc_mono":
        return hwc[..., :1].astype(np.float32, copy=False)
    if extras is not None:
        hwc = np.concatenate([hwc, np.asarray(extras, dtype=np.float32)], axis=-1)
    return hwc.astype(np.float32, copy=False)


def _gaussian_kernel_1d(sigma, radius=None):
    sigma = float(sigma)
    if sigma <= 0.0:
        return np.asarray([1.0], dtype=np.float32)
    if radius is None:
        radius = max(1, int(math.ceil(sigma * 3.0)))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(x**2) / (2.0 * sigma * sigma))
    kernel /= float(np.sum(kernel))
    return kernel.astype(np.float32)


def _convolve_axis_reflect(image, kernel, axis):
    radius = len(kernel) // 2
    if radius == 0:
        return image.astype(np.float32, copy=True)
    pad_width = [(0, 0)] * image.ndim
    pad_width[axis] = (radius, radius)
    padded = np.pad(image, pad_width, mode="reflect")
    return np.apply_along_axis(
        lambda values: np.convolve(values, kernel, mode="valid"),
        axis,
        padded,
    ).astype(np.float32, copy=False)


def _gaussian_blur_chw(chw, sigma):
    kernel = _gaussian_kernel_1d(sigma)
    out = np.asarray(chw, dtype=np.float32)
    if out.ndim == 2:
        out = _convolve_axis_reflect(out, kernel, axis=1)
        return _convolve_axis_reflect(out, kernel, axis=0)
    blurred = []
    for channel in out:
        temp = _convolve_axis_reflect(channel, kernel, axis=1)
        blurred.append(_convolve_axis_reflect(temp, kernel, axis=0))
    return np.stack(blurred).astype(np.float32, copy=False)


def _min_filter_2d(image, size):
    radius = int(size) // 2
    if radius <= 0:
        return image.astype(np.float32, copy=True)
    padded = np.pad(image, ((radius, radius), (radius, radius)), mode="edge")
    windows = []
    for y_offset in range(size):
        for x_offset in range(size):
            windows.append(padded[y_offset:y_offset + image.shape[0], x_offset:x_offset + image.shape[1]])
    return np.min(np.stack(windows), axis=0).astype(np.float32, copy=False)


def calculate_anchor_adaptive(data_norm, weights):
    data = np.asarray(data_norm, dtype=np.float32)
    stride = max(1, data.size // 1_000_000)
    if data.ndim == 3 and data.shape[0] == 3:
        r, g, b = weights
        luminance = (r * data[0]) + (g * data[1]) + (b * data[2])
        sample = luminance.reshape(-1)[::stride]
    else:
        sample = data.reshape(-1)[::stride]
    valid = sample[sample > 0.0]
    if valid.size == 0:
        return 0.0
    if valid.size / sample.size < 0.05:
        return 0.0
    return max(0.0, float(np.percentile(valid, 5.0)))


def extract_luminance(data_norm, anchor, weights):
    r_w, g_w, b_w = weights
    img_anchored = np.maximum(np.asarray(data_norm, dtype=np.float32) - float(anchor), 0.0)
    if img_anchored.ndim == 3 and img_anchored.shape[0] == 3:
        luminance = (r_w * img_anchored[0]) + (g_w * img_anchored[1]) + (b_w * img_anchored[2])
    else:
        luminance = img_anchored
    return luminance, img_anchored


def rational_tonemap(data, stretch_d, profile_hardness):
    x = np.clip(np.asarray(data, dtype=np.float32), 0.0, 1.0)
    stretch_d = float(max(stretch_d, 1e-12))
    profile_hardness = float(max(profile_hardness, 0.1))
    log_d = math.log10(stretch_d)
    stretch_factor = max(0.0, min((log_d - 1.0) / 2.0, 12.0))
    k = 3.0 ** stretch_factor

    u = max(-1.5, min((profile_hardness - 50.0) / 50.0, 1.5))
    toe_shape = 1.0 + 0.60 * (u * u * u)
    toe_shape = max(toe_shape, 1e-3)
    toe = x / np.maximum(x + toe_shape * (1.0 - x), 1e-9)

    denominator = ((k - 1.0) * toe) + 1.0
    return np.clip((k * toe) / denominator, 0.0, 1.0).astype(np.float32, copy=False)


def apply_optical_healing(chw, strength, weights):
    if float(strength) <= 0.0:
        return chw
    strength = float(np.clip(strength, 0.0, 20.0))
    sigma = max(0.4, strength * 0.25)
    r_w, g_w, b_w = weights
    luminance = (r_w * chw[0]) + (g_w * chw[1]) + (b_w * chw[2])
    chroma = chw - luminance[np.newaxis, ...]
    healed_chroma = _gaussian_blur_chw(chroma, sigma=sigma)
    return np.clip(luminance[np.newaxis, ...] + healed_chroma, 0.0, 1.0).astype(np.float32, copy=False)


def apply_star_reduction(chw, intensity):
    intensity = float(np.clip(intensity, 0.0, 1.0))
    if intensity <= 0.0:
        return chw
    size = 3 if intensity < 0.5 else 5
    eroded = np.stack([_min_filter_2d(channel, size) for channel in chw])
    return (chw * (1.0 - intensity) + eroded * intensity).astype(np.float32, copy=False)


def apply_large_structure_rejection(chw, intensity):
    intensity = float(np.clip(intensity, 0.0, 1.0))
    if intensity <= 0.0:
        return chw
    h, w = chw.shape[1], chw.shape[2]
    sigma = max(1.0, min(h, w) / 30.0)
    low_pass = _gaussian_blur_chw(chw, sigma=sigma)
    high_pass = np.maximum(chw - low_pass, 0.0)
    return (chw * (1.0 - intensity) + high_pass * intensity).astype(np.float32, copy=False)


def process_star_mask(
    starmask,
    log_d=1.0,
    profile_hardness=50.0,
    color_grip=0.5,
    shadow_convergence=0.0,
    star_reduction=0.0,
    optical_healing=0.0,
    large_structure_rejection=0.0,
    working_space=DEFAULT_PROFILE,
    use_adaptive_anchor=True,
):
    """Shape a linear star mask with VeraLux StarComposer's rational stretch core."""

    img, layout, extras = _to_chw_rgb(starmask)
    img = np.clip(img, 0.0, 1.0).astype(np.float32, copy=False)
    img = _gaussian_blur_chw(img, sigma=0.5)

    weights = _profile_weights(working_space)
    anchor = calculate_anchor_adaptive(img, weights) if use_adaptive_anchor else 0.0
    img_anchored = np.maximum(img - anchor, 0.0)
    stretch_d = 10.0 ** float(log_d)
    profile_hardness = float(profile_hardness)

    scalar = np.stack(
        [
            rational_tonemap(img_anchored[0], stretch_d, profile_hardness),
            rational_tonemap(img_anchored[1], stretch_d, profile_hardness),
            rational_tonemap(img_anchored[2], stretch_d, profile_hardness),
        ]
    )

    color_grip = float(np.clip(color_grip, 0.0, 1.0))
    if color_grip > 0.001:
        luminance, _anchored = extract_luminance(img, anchor, weights)
        luminance_stretched = np.clip(rational_tonemap(luminance, stretch_d, profile_hardness), 0.0, 1.0)
        luminance_safe = luminance + 1e-9
        vector = np.stack(
            [
                luminance_stretched * (img_anchored[0] / luminance_safe),
                luminance_stretched * (img_anchored[1] / luminance_safe),
                luminance_stretched * (img_anchored[2] / luminance_safe),
            ]
        )
        vector = np.clip(vector, 0.0, 1.0)
    else:
        vector = scalar

    if color_grip > 0.001:
        grip_map = np.full_like(scalar[0], color_grip)
        shadow_convergence = float(np.clip(shadow_convergence, 0.0, 3.0))
        if shadow_convergence > 0.01:
            r_w, g_w, b_w = weights
            luminance_ref = (r_w * scalar[0]) + (g_w * scalar[1]) + (b_w * scalar[2])
            grip_map *= np.power(luminance_ref, shadow_convergence)
        final = (vector * grip_map) + (scalar * (1.0 - grip_map))
    else:
        final = scalar

    final = np.clip(final, 0.0, 1.0).astype(np.float32, copy=False)
    final = apply_large_structure_rejection(final, large_structure_rejection)
    final = apply_optical_healing(final, optical_healing, weights)
    final = apply_star_reduction(final, star_reduction)
    return _from_chw_rgb(np.clip(final, 0.0, 1.0), layout, extras)


def compose_with_starless(starless, stars, blend_mode="screen"):
    """Composite shaped stars onto a starless base using StarComposer blend modes."""

    base_chw, base_layout, base_extras = _to_chw_rgb(starless)
    stars_chw, _stars_layout, _stars_extras = _to_chw_rgb(stars)
    min_h = min(base_chw.shape[1], stars_chw.shape[1])
    min_w = min(base_chw.shape[2], stars_chw.shape[2])
    base = base_chw[:, :min_h, :min_w]
    star = stars_chw[:, :min_h, :min_w]
    if str(blend_mode).lower() == "add":
        combined = np.clip(base + star, 0.0, 1.0)
    else:
        combined = 1.0 - (1.0 - base) * (1.0 - star)

    if base_chw.shape[1:] != (min_h, min_w):
        full = base_chw.copy()
        full[:, :min_h, :min_w] = combined
        combined = full
    return _from_chw_rgb(np.clip(combined, 0.0, 1.0), base_layout, base_extras)

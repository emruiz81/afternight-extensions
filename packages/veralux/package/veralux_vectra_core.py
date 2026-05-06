# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Vectra) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Vectra.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux Vectra LCH vector color-grading core."""

from __future__ import annotations

import numpy as np

try:
    from scipy.ndimage import convolve as _nd_convolve
except Exception:  # pragma: no cover - minimal diagnostic environments only.
    _nd_convolve = None


UPSTREAM_VERSION = "1.0.3"
VECTOR_KEYS = ("R", "Y", "G", "C", "B", "M")
TARGET_HUES = {
    "R": 0.0,
    "Y": 60.0,
    "G": 120.0,
    "C": 180.0,
    "B": 240.0,
    "M": 300.0,
}


def default_vectors():
    return {key: (0.0, 0.0) for key in VECTOR_KEYS}


def normalize_input(image):
    """Normalize common integer/float image arrays to float32 in the 0..1 range."""

    img = np.asarray(image)
    input_dtype = img.dtype
    img_float = img.astype(np.float32, copy=False)
    if np.issubdtype(input_dtype, np.integer):
        if input_dtype == np.uint8:
            return img_float / 255.0
        if input_dtype == np.uint16:
            return img_float / 65535.0
        return img_float / float(np.iinfo(input_dtype).max)
    if np.issubdtype(input_dtype, np.floating):
        if img_float.size == 0:
            return img_float
        current_max = float(np.nanmax(img_float))
        if current_max <= 1.0 + 1e-5:
            return img_float
        if current_max > 256.0:
            return img_float / 65535.0
        return img_float / (current_max + 1e-12)
    return img_float


def _to_hwc_rgb(image):
    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim != 3:
        raise ValueError("VeraLux Vectra expects a 3-channel RGB image")

    if img.shape[0] == 3 and img.shape[-1] not in (3, 4):
        return np.moveaxis(img[:3], 0, -1), "chw", None

    if img.shape[-1] >= 3:
        extras = img[..., 3:] if img.shape[-1] > 3 else None
        return img[..., :3], "hwc", extras

    raise ValueError("VeraLux Vectra expects a 3-channel RGB image")


def _from_hwc_rgb(rgb, layout, extras):
    out = np.clip(np.asarray(rgb, dtype=np.float32), 0.0, 1.0)
    if layout == "chw":
        return np.moveaxis(out, -1, 0).astype(np.float32, copy=False)
    if extras is not None:
        out = np.concatenate([out, np.asarray(extras, dtype=np.float32)], axis=-1)
    return out.astype(np.float32, copy=False)


def rgb_luminance(rgb):
    img = np.asarray(rgb, dtype=np.float32)
    if img.ndim == 3 and img.shape[-1] >= 3:
        return (0.2126 * img[..., 0]) + (0.7152 * img[..., 1]) + (0.0722 * img[..., 2])
    if img.ndim == 3 and img.shape[0] == 3:
        return (0.2126 * img[0]) + (0.7152 * img[1]) + (0.0722 * img[2])
    raise ValueError("rgb_luminance expects an RGB image")


def rgb_to_lab(rgb):
    """Convert linearized RGB-like values to CIE Lab using the upstream matrix path."""

    matrix = np.asarray(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ],
        dtype=np.float32,
    )
    clipped = np.clip(np.asarray(rgb, dtype=np.float32), 0.0, 1.0)
    xyz = clipped.reshape(-1, 3) @ matrix.T
    xyz = xyz.reshape(clipped.shape)
    xyz[..., 0] /= 0.95047
    xyz[..., 2] /= 1.08883

    delta = 6.0 / 29.0

    def lab_f(values):
        return np.where(values > delta**3, np.cbrt(values), (values / (3.0 * delta**2)) + (4.0 / 29.0))

    fx = lab_f(xyz[..., 0])
    fy = lab_f(xyz[..., 1])
    fz = lab_f(xyz[..., 2])
    lightness = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.stack([lightness, a, b], axis=-1).astype(np.float32, copy=False)


def lab_to_rgb(lab):
    matrix_inv = np.asarray(
        [
            [3.2404542, -1.5371385, -0.4985314],
            [-0.9692660, 1.8760108, 0.0415560],
            [0.0556434, -0.2040259, 1.0572252],
        ],
        dtype=np.float32,
    )
    values = np.asarray(lab, dtype=np.float32)
    delta = 6.0 / 29.0
    fy = (values[..., 0] + 16.0) / 116.0
    fx = fy + values[..., 1] / 500.0
    fz = fy - values[..., 2] / 200.0

    def lab_f_inv(t):
        return np.where(t > delta, t**3, 3.0 * delta**2 * (t - 4.0 / 29.0))

    x = 0.95047 * lab_f_inv(fx)
    y = lab_f_inv(fy)
    z = 1.08883 * lab_f_inv(fz)
    xyz = np.stack([x, y, z], axis=-1)
    rgb = xyz.reshape(-1, 3) @ matrix_inv.T
    return np.clip(rgb.reshape(xyz.shape), 0.0, 1.0).astype(np.float32, copy=False)


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


def _separable_filter_reflect(image, kernel):
    horizontal = _convolve_axis_reflect(np.asarray(image, dtype=np.float32), kernel, axis=1)
    return _convolve_axis_reflect(horizontal, kernel, axis=0)


def _box_blur_reflect(image, size):
    if _nd_convolve is not None:
        kernel = np.ones((int(size), int(size)), dtype=np.float32) / float(size * size)
        return _nd_convolve(np.asarray(image, dtype=np.float32), kernel, mode="reflect").astype(
            np.float32,
            copy=False,
        )
    kernel = np.ones((size,), dtype=np.float32) / float(size)
    return _separable_filter_reflect(image, kernel)


def _atrous_smooth_reflect(image, kernel):
    if _nd_convolve is not None:
        current = np.asarray(image, dtype=np.float32)
        horizontal = _nd_convolve(current, kernel.reshape(1, -1), mode="reflect")
        return _nd_convolve(horizontal, kernel.reshape(-1, 1), mode="reflect").astype(
            np.float32,
            copy=False,
        )
    return _separable_filter_reflect(image, kernel)


def atrous_decomposition(image2d, n_scales=3):
    """Simple ATWT for stellar-energy protection."""

    current = np.asarray(image2d, dtype=np.float32)
    planes = []
    kernel = np.asarray([1, 4, 6, 4, 1], dtype=np.float32) / 16.0
    for scale in range(int(n_scales)):
        step = 2**scale
        kernel_size = len(kernel) + (len(kernel) - 1) * (step - 1)
        dilated = np.zeros((kernel_size,), dtype=np.float32)
        dilated[0::step] = kernel
        smooth = _atrous_smooth_reflect(current, dilated)
        planes.append(current - smooth)
        current = smooth
    return planes


def compute_signal_mask(lightness, threshold_sigma):
    """Shadow Authority: return 0 for protected background and 1 for signal."""

    lightness_norm = np.asarray(lightness, dtype=np.float32) / 100.0
    median = float(np.median(lightness_norm))
    mad = float(np.median(np.abs(lightness_norm - median)))
    sigma = max(1.4826 * mad, 1e-6)
    background = float(np.percentile(lightness_norm, 25.0))
    noise_floor = background + (float(threshold_sigma) * sigma)
    mask = (lightness_norm - noise_floor) / (2.0 * sigma + 1e-9)
    return _box_blur_reflect(np.clip(mask, 0.0, 1.0), 3)


def compute_star_protection(lightness):
    planes = atrous_decomposition(lightness, n_scales=2)
    energy = np.abs(planes[0]) + np.abs(planes[1])
    star_map = np.clip((energy - 1.5) * 0.5, 0.0, 1.0)
    return np.clip(1.0 - star_map, 0.0, 1.0).astype(np.float32, copy=False)


def _normalized_vectors(vectors):
    merged = default_vectors()
    for key, value in dict(vectors or {}).items():
        normalized_key = str(key).upper()
        if normalized_key not in TARGET_HUES:
            continue
        try:
            hue_shift, saturation_boost = value
        except Exception:
            continue
        merged[normalized_key] = (
            float(np.clip(hue_shift, -60.0, 60.0)),
            float(np.clip(saturation_boost, -1.0, 1.0)),
        )
    return merged


def process_vectors(image, vectors, shadow_auth=0.0, protect_stars=True):
    """Apply LCH hue/saturation vector edits and preserve the source layout."""

    rgb_hwc, layout, extras = _to_hwc_rgb(image)
    vectors = _normalized_vectors(vectors)

    lab = rgb_to_lab(rgb_hwc)
    lightness = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]

    chroma = np.sqrt(a**2 + b**2)
    hue_deg = np.degrees(np.arctan2(b, a)) % 360.0

    sigma_threshold = float(np.clip(shadow_auth, 0.0, 100.0)) / 20.0
    signal_mask = compute_signal_mask(lightness, sigma_threshold)
    star_mask = compute_star_protection(lightness) if protect_stars else np.float32(1.0)

    chroma_relative = chroma / (lightness + 1.0)
    chroma_stability = np.clip((chroma_relative - 0.015) / 0.07, 0.0, 1.0)
    assist = 0.25 * np.clip((signal_mask - 0.10) / 0.30, 0.0, 1.0)
    chroma_stability = np.maximum(chroma_stability, assist)
    global_mask = star_mask * chroma_stability * (0.15 + 0.85 * signal_mask)

    total_hue_shift = np.zeros_like(hue_deg, dtype=np.float32)
    total_saturation_gain = np.zeros_like(chroma, dtype=np.float32)
    sigma_angle = 30.0

    for key, (hue_shift, saturation_boost) in vectors.items():
        if hue_shift == 0.0 and saturation_boost == 0.0:
            continue
        target = TARGET_HUES[key]
        hue_distance = np.abs(hue_deg - target)
        hue_distance = np.minimum(hue_distance, 360.0 - hue_distance)
        weight = np.exp(-(hue_distance**2) / (2.0 * sigma_angle**2))
        total_hue_shift += hue_shift * weight
        total_saturation_gain += saturation_boost * weight

    final_hue_deg = hue_deg + (total_hue_shift * global_mask)
    final_chroma = np.maximum(0.0, chroma * (1.0 + total_saturation_gain * global_mask))

    final_hue_rad = np.radians(final_hue_deg)
    a_new = final_chroma * np.cos(final_hue_rad)
    b_new = final_chroma * np.sin(final_hue_rad)
    lab_new = np.stack([lightness, a_new, b_new], axis=-1)
    rgb_out = lab_to_rgb(lab_new)
    return _from_hwc_rgb(rgb_out, layout, extras)

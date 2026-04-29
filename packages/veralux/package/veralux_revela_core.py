# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Revela by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Revela.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux Revela local-contrast core.

This module keeps the derived image-processing algorithm separate from
AfterNight SDK host integration so future upstream refreshes are easier to
review.
"""

from __future__ import annotations

import numpy as np

try:  # OpenCV remains the preferred runtime path.
    import cv2 as _cv2
except Exception:  # pragma: no cover - exercised when OpenCV is absent.
    _cv2 = None


UPSTREAM_VERSION = "1.0.2"


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
        if img.size == 0:
            return img_float
        current_max = float(np.nanmax(img_float))
        if current_max <= 1.0 + 1e-5:
            return img_float
        if current_max <= 65535.0:
            return img_float / 65535.0
    return img_float


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
    if _cv2 is not None:
        return _cv2.sepFilter2D(
            image.astype(np.float32, copy=False),
            -1,
            kernel,
            kernel,
            borderType=_cv2.BORDER_REFLECT,
        )

    horizontal = _convolve_axis_reflect(image.astype(np.float32, copy=False), kernel, axis=1)
    return _convolve_axis_reflect(horizontal, kernel, axis=0)


def _box_blur_reflect(image, size):
    if _cv2 is not None:
        return _cv2.blur(
            image.astype(np.float32, copy=False),
            (size, size),
            borderType=_cv2.BORDER_REFLECT,
        )

    kernel = np.ones((size,), dtype=np.float32) / float(size)
    return _separable_filter_reflect(image, kernel)


def _rgb_to_lab(rgb_float32):
    if _cv2 is None:
        raise RuntimeError("OpenCV is required for Lab color conversion")
    return _cv2.cvtColor(rgb_float32.astype(np.float32, copy=False), _cv2.COLOR_RGB2Lab)


def _lab_to_rgb(lab_float32):
    if _cv2 is None:
        raise RuntimeError("OpenCV is required for Lab color conversion")
    return _cv2.cvtColor(lab_float32.astype(np.float32, copy=False), _cv2.COLOR_Lab2RGB)


def _rgb_luminance(rgb_float32):
    weights = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return np.tensordot(rgb_float32[..., :3], weights, axes=([-1], [0])).astype(np.float32)


def atrous_decomposition(image2d, n_scales=6):
    current = np.asarray(image2d, dtype=np.float32)
    planes = []
    kernel_1d = np.asarray([1, 4, 6, 4, 1], dtype=np.float32) / 16.0

    for scale in range(int(n_scales)):
        step = 2**scale
        kernel_size = 5 + (4 * (step - 1))
        dilated_kernel = np.zeros((kernel_size,), dtype=np.float32)
        dilated_kernel[0::step] = kernel_1d

        smooth = _separable_filter_reflect(current, dilated_kernel)
        detail = current - smooth
        planes.append(detail)
        current = smooth

    return planes, current


def compute_signal_mask(luminance_100, threshold_sigma):
    """VeraLux Shadow Authority gate."""

    luminance = np.asarray(luminance_100, dtype=np.float32) / 100.0
    median = float(np.median(luminance))
    mad = float(np.median(np.abs(luminance - median)))
    sigma = (max)(1.4826 * mad, 1e-6)

    noise_floor = median + (float(threshold_sigma) * sigma)
    mask = (luminance - noise_floor) / ((2.0 * sigma) + 1e-9)
    mask = np.clip(mask, 0.0, 1.0)
    return _box_blur_reflect(mask.astype(np.float32, copy=False), 3)


def compute_star_protection(planes, strength=1.0):
    """Heuristic high-energy stellar-profile protection."""

    strength = float(strength)
    if strength <= 0:
        return np.ones_like(planes[0], dtype=np.float32)

    e_fine = np.abs(planes[0]) + np.abs(planes[1])
    e_mid = np.abs(planes[2]) + np.abs(planes[3])
    energy = e_fine + (0.5 * e_mid)

    median = float(np.median(energy))
    mad = float(np.median(np.abs(energy - median)))
    sigma = (max)(1.4826 * mad, 1e-6)

    threshold = median + (4.0 * sigma)
    star_map = np.clip((energy - threshold) / ((2.0 * sigma) + 1e-9), 0.0, 1.0)
    star_map = _box_blur_reflect(star_map, 5)
    star_map = np.clip(star_map * 1.5, 0.0, 1.0)
    star_map = _box_blur_reflect(star_map, 5)

    protection = 1.0 - (star_map * strength)
    return np.clip(protection, 0.0, 1.0)


def process_structure(
    image,
    texture_amt=0.0,
    structure_amt=0.0,
    shadow_auth=33.0,
    protect_stars=True,
    return_mask=False,
):
    """Apply the VeraLux Revela texture/structure enhancement."""

    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim not in (2, 3):
        raise ValueError("VeraLux Revela expects a 2D mono or 3D RGB image")

    texture_amt = float(np.clip(texture_amt, 0.0, 1.0))
    structure_amt = float(np.clip(structure_amt, 0.0, 1.0))
    shadow_auth = float(np.clip(shadow_auth, 0.0, 100.0))

    is_mono = img.ndim == 2 or (img.ndim == 3 and img.shape[-1] == 1)
    if is_mono:
        source_mono = img[..., 0] if img.ndim == 3 else img
        luminance = source_mono * 100.0
        lab = None
    elif _cv2 is not None:
        lab = _rgb_to_lab(img[..., :3])
        luminance = lab[..., 0]
    else:
        lab = None
        luminance = _rgb_luminance(img[..., :3]) * 100.0

    planes, residual = atrous_decomposition(luminance, n_scales=6)
    sigma_threshold = (shadow_auth * 0.12) - 3.0
    signal_mask = compute_signal_mask(luminance, sigma_threshold)

    star_mask = np.float32(1.0)
    star_mask_structure = np.float32(1.0)
    if protect_stars:
        star_mask = compute_star_protection(planes, strength=1.0)
        star_mask_structure = np.clip(star_mask**2.0, 0.0, 1.0)

    active_mask_texture = signal_mask * star_mask
    active_mask_structure = signal_mask * star_mask_structure

    if return_mask:
        return active_mask_structure.astype(np.float32, copy=False)

    texture_gain = 1.0 + (texture_amt * 1.5)
    planes[0] *= 1.0 + ((texture_gain - 1.0) * active_mask_texture)
    planes[1] *= 1.0 + ((texture_gain - 1.0) * active_mask_texture)

    structure_gain = 1.0 + structure_amt
    for index in (2, 3, 4):
        planes[index] *= 1.0 + ((structure_gain - 1.0) * active_mask_structure)

    new_luminance = residual + sum(planes)
    new_luminance = np.clip(new_luminance, 0.0, 100.0).astype(np.float32, copy=False)

    if is_mono:
        output = new_luminance / 100.0
        if img.ndim == 3:
            return output[..., np.newaxis].astype(np.float32, copy=False)
        return output.astype(np.float32, copy=False)

    if lab is not None:
        lab[..., 0] = new_luminance
        return np.clip(_lab_to_rgb(lab), 0.0, 1.0).astype(np.float32, copy=False)

    old_luminance = np.clip(luminance / 100.0, 1e-6, None)
    ratio = (new_luminance / 100.0) / old_luminance
    output = img[..., :3] * ratio[..., np.newaxis]
    if img.shape[-1] > 3:
        output = np.concatenate([output, img[..., 3:]], axis=-1)
    return np.clip(output, 0.0, 1.0).astype(np.float32, copy=False)

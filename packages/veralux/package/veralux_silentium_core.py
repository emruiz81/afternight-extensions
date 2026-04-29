# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Silentium by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Silentium.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux Silentium linear multiscale noise-suppression core."""

from __future__ import annotations

import numpy as np


UPSTREAM_VERSION = "1.0.3"


def normalize_input(image):
    """Normalize common integer/float image arrays to float32 in the 0..1 range."""

    img = np.asarray(image)
    safe = np.nan_to_num(img, nan=0.0, posinf=1.0, neginf=0.0)
    input_dtype = safe.dtype
    img_float = safe.astype(np.float32, copy=False)

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
        if current_max <= 1.0 + 1e-5:
            return np.clip(img_float, 0.0, 1.0)
        if current_max <= 65535.0:
            return np.clip(img_float / 65535.0, 0.0, 1.0)
        return np.clip(img_float / max(current_max, 1e-6), 0.0, 1.0)

    return np.clip(img_float, 0.0, 1.0)


def _to_work_image(image):
    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim == 2:
        return img, "hw", None
    if img.ndim != 3:
        raise ValueError("VeraLux Silentium expects a 2D mono or 3D RGB image")

    if img.shape[-1] >= 3:
        extras = img[..., 3:] if img.shape[-1] > 3 else None
        return img[..., :3], "hwc", extras
    if img.shape[-1] == 1:
        return img[..., 0], "hwc_mono", None

    if img.shape[0] == 3:
        return np.moveaxis(img[:3], 0, -1), "chw", None
    if img.shape[0] == 1:
        return img[0], "chw_mono", None

    raise ValueError("VeraLux Silentium expects RGB images to have at least 3 channels")


def _from_work_image(data, layout, extras):
    out = np.clip(np.asarray(data, dtype=np.float32), 0.0, 1.0)
    if layout == "hw":
        return out.astype(np.float32, copy=False)
    if layout == "hwc_mono":
        return out[..., np.newaxis].astype(np.float32, copy=False)
    if layout == "chw_mono":
        return out[np.newaxis, ...].astype(np.float32, copy=False)
    if layout == "chw":
        return np.moveaxis(out, -1, 0).astype(np.float32, copy=False)
    if extras is not None:
        out = np.concatenate([out, np.asarray(extras, dtype=np.float32)], axis=-1)
    return out.astype(np.float32, copy=False)


def robust_sigma(values):
    sample = np.asarray(values, dtype=np.float32).reshape(-1)
    if sample.size == 0:
        return 1e-6
    median = float(np.median(sample))
    mad = float(np.median(np.abs(sample - median)))
    if mad <= 0.0:
        std = float(np.std(sample))
        return max(std, 1e-6)
    return max(1.4826 * mad, 1e-6)


def estimate_noise_map(channel, block_size=48):
    values = np.asarray(channel, dtype=np.float32)
    h, w = values.shape
    sigma_map = np.zeros_like(values, dtype=np.float32)

    for y in range(0, h, block_size):
        for x in range(0, w, block_size):
            patch = values[y : min(y + block_size, h), x : min(x + block_size, w)]
            cutoff = float(np.quantile(patch, 0.55))
            background = patch[patch <= cutoff]
            if background.size < 16:
                background = patch
            sigma_map[y : min(y + block_size, h), x : min(x + block_size, w)] = robust_sigma(background)

    fill = robust_sigma(values)
    sigma_map[sigma_map <= 0.0] = fill
    return sigma_map.astype(np.float32, copy=False)


def compute_signal_probability(channel):
    """Return 0 for background, 1 for protected signal, using linear statistics."""

    values = np.asarray(channel, dtype=np.float32)
    median = float(np.median(values))
    sigma = robust_sigma(values)
    low = median + sigma
    high = median + 3.5 * sigma
    return np.clip((values - low) / max(high - low, 1e-9), 0.0, 1.0).astype(np.float32)


def _mtf(values, midtones, lo, hi):
    m = float(midtones)
    lo = float(lo)
    hi = float(hi)
    dist = hi - lo
    if dist < 1e-9:
        return np.where(values > lo, 1.0, 0.0).astype(np.float32)

    xp = np.clip((values - lo) / dist, 0.0, 1.0)
    numerator = (m - 1.0) * xp
    denominator = (2.0 * m - 1.0) * xp - m
    with np.errstate(divide="ignore", invalid="ignore"):
        out = numerator / denominator
    return np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)


def _auto_stretch_proxy(channel):
    values = np.asarray(channel, dtype=np.float32)
    median = float(np.median(values))
    sigma = robust_sigma(values)
    shadows = max(0.0, median - 2.8 * sigma)
    x = np.clip((median - shadows) / max(1.0 - shadows, 1e-9), 0.0, 1.0)
    target_bg = 0.25
    denominator = (2.0 * x * target_bg) - x - target_bg
    midtones = 0.5 if abs(denominator) < 1e-9 else (x * (target_bg - 1.0)) / denominator
    return _mtf(values, np.clip(midtones, 0.01, 0.99), shadows, 1.0)


def _convolve_axis_reflect(image, kernel, axis):
    radius = len(kernel) // 2
    if radius == 0:
        return np.asarray(image, dtype=np.float32).copy()

    values = np.asarray(image, dtype=np.float32)
    pad_width = [(0, 0), (0, 0)]
    pad_width[axis] = (radius, radius)
    padded = np.pad(values, pad_width, mode="reflect")
    out = np.zeros_like(values, dtype=np.float32)
    h, w = values.shape
    for offset, weight in enumerate(kernel):
        if axis == 0:
            out += weight * padded[offset : offset + h, 0:w]
        else:
            out += weight * padded[0:h, offset : offset + w]
    return out.astype(np.float32, copy=False)


def _separable_filter_reflect(image, kernel):
    horizontal = _convolve_axis_reflect(image, kernel, axis=1)
    return _convolve_axis_reflect(horizontal, kernel, axis=0)


def _atrous_kernel(scale):
    base = np.asarray([1, 4, 6, 4, 1], dtype=np.float32) / 16.0
    if scale <= 1:
        return base
    size = len(base) + (len(base) - 1) * (scale - 1)
    kernel = np.zeros((size,), dtype=np.float32)
    kernel[0::scale] = base
    return kernel


def _convolve2d_reflect(image, kernel):
    values = np.asarray(image, dtype=np.float32)
    kh, kw = kernel.shape
    py = kh // 2
    px = kw // 2
    padded = np.pad(values, ((py, py), (px, px)), mode="reflect")
    out = np.zeros_like(values, dtype=np.float32)
    h, w = values.shape
    for y in range(kh):
        for x in range(kw):
            out += float(kernel[y, x]) * padded[y : y + h, x : x + w]
    return out.astype(np.float32, copy=False)


def _maximum_filter_3x3(image):
    values = np.asarray(image, dtype=np.float32)
    padded = np.pad(values, ((1, 1), (1, 1)), mode="edge")
    windows = [
        padded[y : y + values.shape[0], x : x + values.shape[1]]
        for y in range(3)
        for x in range(3)
    ]
    return np.maximum.reduce(windows).astype(np.float32, copy=False)


def compute_edge_map(channel):
    stretched = _auto_stretch_proxy(channel)
    kx = np.asarray([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    ky = np.asarray([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
    gx = _convolve2d_reflect(stretched, kx)
    gy = _convolve2d_reflect(stretched, ky)
    magnitude = np.sqrt(gx * gx + gy * gy)
    scale = float(np.percentile(magnitude, 98.0))
    if scale <= 1e-9:
        scale = 1e-9
    return _maximum_filter_3x3(np.clip(magnitude / scale, 0.0, 1.0))


def _soft_threshold(detail, threshold):
    return np.sign(detail) * np.maximum(np.abs(detail) - threshold, 0.0)


def _multiscale_denoise_channel(
    channel,
    *,
    sigma_map,
    edge_map,
    signal_map,
    intensity,
    detail_guard,
    shadow_smoothness,
    chroma=False,
):
    current = np.asarray(channel, dtype=np.float32)
    details = []
    scales = (1, 2, 4, 8)
    layer_weights = (0.60, 0.80, 1.0, 1.0)
    strength = float(np.clip(intensity, 0.0, 1.0))
    guard_amount = float(np.clip(detail_guard, 0.0, 1.0))
    shadow_amount = float(np.clip(shadow_smoothness, 0.0, 1.0))

    for scale in scales:
        smooth = _separable_filter_reflect(current, _atrous_kernel(scale))
        details.append(current - smooth)
        current = smooth

    reconstructed = current
    for index, detail in reversed(list(enumerate(details))):
        scale = scales[index]
        weight = layer_weights[index]
        guard_map = 1.0 + (7.0 * guard_amount * (edge_map * signal_map))
        shadow_gate = 1.0 - np.clip(signal_map * 4.0, 0.0, 1.0)
        boost_map = 1.0 + (2.5 * shadow_amount * shadow_gate)
        threshold = sigma_map * (3.6 * strength) * weight / np.sqrt(float(scale))
        if chroma:
            threshold *= 1.25
        threshold = (threshold / guard_map) * boost_map
        reconstructed = reconstructed + _soft_threshold(detail, threshold)

    return reconstructed.astype(np.float32, copy=False)


def _luminance(rgb):
    values = np.asarray(rgb, dtype=np.float32)
    return ((0.2126 * values[..., 0]) + (0.7152 * values[..., 1]) + (0.0722 * values[..., 2])).astype(np.float32)


def _denoise_luminance(luminance, intensity, detail_guard, adaptive_noise, shadow_smoothness):
    signal_map = compute_signal_probability(luminance)
    edge_map = compute_edge_map(luminance)
    if adaptive_noise:
        sigma_map = estimate_noise_map(luminance)
    else:
        sigma_map = np.full_like(luminance, robust_sigma(luminance), dtype=np.float32)
    return _multiscale_denoise_channel(
        luminance,
        sigma_map=sigma_map,
        edge_map=edge_map,
        signal_map=signal_map,
        intensity=intensity,
        detail_guard=detail_guard,
        shadow_smoothness=shadow_smoothness,
    )


def process_noise_reduction(
    image,
    *,
    intensity=25.0,
    detail_guard=50.0,
    adaptive_noise=True,
    enable_chroma=True,
    chroma_strength=30.0,
    shadow_smoothness=10.0,
    protect_highlights=True,
):
    """Apply Silentium's first native linear multiscale denoise slice."""

    data, layout, extras = _to_work_image(image)
    intensity_norm = float(np.clip(intensity, 0.0, 100.0)) / 100.0
    guard_norm = float(np.clip(detail_guard, 0.0, 100.0)) / 100.0
    chroma_norm = float(np.clip(chroma_strength, 0.0, 100.0)) / 100.0
    shadow_norm = float(np.clip(shadow_smoothness, 0.0, 100.0)) / 100.0

    if data.ndim == 2:
        luminance = np.asarray(data, dtype=np.float32)
        signal_map = compute_signal_probability(luminance)
        edge_map = compute_edge_map(luminance)
        sigma_map = estimate_noise_map(luminance) if adaptive_noise else np.full_like(luminance, robust_sigma(luminance))
        result = _multiscale_denoise_channel(
            luminance,
            sigma_map=sigma_map,
            edge_map=edge_map,
            signal_map=signal_map,
            intensity=intensity_norm,
            detail_guard=guard_norm,
            shadow_smoothness=shadow_norm,
        )
        if protect_highlights:
            highlight_alpha = np.clip(signal_map * 1.25, 0.0, 1.0)
            result = result * (1.0 - highlight_alpha) + luminance * highlight_alpha
        return _from_work_image(result, layout, extras)

    rgb = np.asarray(data, dtype=np.float32)
    luminance = _luminance(rgb)
    signal_map = compute_signal_probability(luminance)
    edge_map = compute_edge_map(luminance)
    luminance_dn = _denoise_luminance(luminance, intensity_norm, guard_norm, bool(adaptive_noise), shadow_norm)
    delta_l = luminance_dn - luminance
    result = rgb + delta_l[..., np.newaxis]

    if enable_chroma and chroma_norm > 0.01:
        neutral = np.mean(result, axis=2, keepdims=True)
        chroma_delta = result - neutral
        sigma_base = estimate_noise_map(luminance) if adaptive_noise else np.full_like(luminance, robust_sigma(luminance))
        denoised_chroma = []
        for channel in range(3):
            denoised = _multiscale_denoise_channel(
                chroma_delta[..., channel],
                sigma_map=sigma_base * 0.75,
                edge_map=edge_map,
                signal_map=signal_map,
                intensity=chroma_norm,
                detail_guard=guard_norm * 0.5,
                shadow_smoothness=shadow_norm * 0.5,
                chroma=True,
            )
            denoised_chroma.append(denoised)
        chroma_out = np.stack(denoised_chroma, axis=-1)
        result = neutral + chroma_out

    if protect_highlights:
        highlight_alpha = np.clip(signal_map[..., np.newaxis] * 1.25, 0.0, 1.0)
        result = result * (1.0 - highlight_alpha) + rgb * highlight_alpha

    return _from_work_image(result, layout, extras)


def calculate_shadow_report(image_original, image_denoised):
    orig, _layout, _extras = _to_work_image(image_original)
    den, _layout_den, _extras_den = _to_work_image(image_denoised)
    orig_l = _luminance(orig) if orig.ndim == 3 else orig
    den_l = _luminance(den) if den.ndim == 3 else den

    sigma_orig = robust_sigma(orig_l)
    sigma_den = robust_sigma(den_l)
    median_orig = float(np.median(orig_l))
    median_den = float(np.median(den_l))
    reduction_pct = (1.0 - (sigma_den / max(sigma_orig, 1e-9))) * 100.0
    snr_gain = sigma_orig / max(sigma_den, 1e-9)
    pedestal_shift = median_den - median_orig

    return (
        "\n------------------------------------------------------------\n"
        " VERALUX SILENTIUM - SHADOW REPORT\n"
        "------------------------------------------------------------\n"
        f" > Background Noise (Sigma): {sigma_orig:.5f} -> {sigma_den:.5f}\n"
        f" > Noise Reduction: -{reduction_pct:.1f}%\n"
        f" > SNR Improvement: {snr_gain:.2f}x\n"
        f" > Pedestal Shift (Blacks): {pedestal_shift:+.6f} (Flux conservation)\n"
        "------------------------------------------------------------\n"
    )

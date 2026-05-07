# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Silentium) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Silentium.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux Silentium linear multiscale noise-suppression core."""

from __future__ import annotations

import numpy as np

try:
    import pywt as _pywt
except Exception:  # pragma: no cover - exercised only in minimal dependency test environments.
    _pywt = None

try:
    from scipy.ndimage import maximum_filter as _scipy_maximum_filter
    from scipy.signal import convolve2d as _scipy_convolve2d
except Exception:  # pragma: no cover - fallback keeps local tests light.
    _scipy_convolve2d = None
    _scipy_maximum_filter = None


UPSTREAM_VERSION = "1.0.3"
_SWT_LEVELS = 4
_SWT_WAVELET = "db2"


def quality_fallback_messages():
    messages = []
    if _pywt is None:
        messages.append(
            "VeraLux Silentium is using a lower-quality multiscale denoise "
            "fallback because PyWavelets is unavailable; install or repair "
            "PyWavelets to match the original Siril SWT/db2 engine."
        )
    if _scipy_convolve2d is None or _scipy_maximum_filter is None:
        messages.append(
            "VeraLux Silentium is using lower-quality NumPy edge-morphology "
            "fallbacks because SciPy signal/ndimage helpers are unavailable; "
            "edge protection may not match the original Siril output."
        )
    return tuple(messages)


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

    if img.shape[0] == 3 and img.shape[-1] != 3:
        return np.moveaxis(img[:3], 0, -1), "chw", None
    if img.shape[0] == 1 and img.shape[-1] != 1:
        return img[0], "chw_mono", None
    if img.shape[-1] >= 3:
        extras = img[..., 3:] if img.shape[-1] > 3 else None
        return img[..., :3], "hwc", extras
    if img.shape[-1] == 1:
        return img[..., 0], "hwc_mono", None

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


def _rgb_to_lab(rgb):
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

    epsilon = 0.008856
    kappa = 903.3

    def lab_f(values):
        return np.where(values > epsilon, np.cbrt(values), ((kappa * values) + 16.0) / 116.0)

    fx = lab_f(xyz[..., 0])
    fy = lab_f(xyz[..., 1])
    fz = lab_f(xyz[..., 2])
    lightness = (116.0 * fy) - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.stack([lightness, a, b], axis=-1).astype(np.float32, copy=False)


def _lab_to_rgb(lab):
    matrix_inv = np.asarray(
        [
            [3.2404542, -1.5371385, -0.4985314],
            [-0.9692660, 1.8760108, 0.0415560],
            [0.0556434, -0.2040259, 1.0572252],
        ],
        dtype=np.float32,
    )
    values = np.asarray(lab, dtype=np.float32)
    lightness = values[..., 0]
    fy = (lightness + 16.0) / 116.0
    fx = (values[..., 1] / 500.0) + fy
    fz = fy - (values[..., 2] / 200.0)

    epsilon = 0.008856
    kappa = 903.3

    def lab_f_inv(t):
        t3 = t**3
        return np.where(t3 > epsilon, t3, ((116.0 * t) - 16.0) / kappa)

    x = 0.95047 * lab_f_inv(fx)
    y = lab_f_inv(fy)
    z = 1.08883 * lab_f_inv(fz)
    xyz = np.stack([x, y, z], axis=-1)
    rgb = xyz.reshape(-1, 3) @ matrix_inv.T
    return np.clip(rgb.reshape(xyz.shape), 0.0, 1.0).astype(np.float32, copy=False)


def _coerce_star_mask(star_mask, shape):
    if star_mask is None:
        return None
    mask = np.asarray(star_mask, dtype=np.float32)
    if mask.ndim == 3:
        if mask.shape[0] in (1, 3) and mask.shape[1:] == tuple(shape):
            mask = mask[0] if mask.shape[0] == 1 else np.mean(mask[:3], axis=0)
        elif mask.shape[-1] == 1:
            mask = mask[..., 0]
        else:
            mask = np.mean(mask[..., :3], axis=-1)
    if mask.shape != tuple(shape):
        return None
    return np.clip(mask, 0.0, 1.0).astype(np.float32, copy=False)


def _coerce_fwhm_map(fwhm_map, shape):
    if fwhm_map is None:
        return np.full(shape, 4.0, dtype=np.float32)
    values = np.asarray(fwhm_map, dtype=np.float32)
    if values.shape != tuple(shape):
        return np.full(shape, 4.0, dtype=np.float32)
    return np.clip(values, 0.1, 64.0).astype(np.float32, copy=False)


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


def estimate_noise_map(channel, block_size=64):
    values = np.asarray(channel, dtype=np.float32)
    h, w = values.shape
    sigma_map = np.zeros_like(values, dtype=np.float32)

    for y in range(0, h, block_size):
        for x in range(0, w, block_size):
            patch = values[y : min(y + block_size, h), x : min(x + block_size, w)]
            cutoff = float(np.quantile(patch, 0.5))
            background = patch[patch <= cutoff]
            if background.size < 16:
                background = patch
            sigma_map[y : min(y + block_size, h), x : min(x + block_size, w)] = robust_sigma(background)

    zero_mask = sigma_map <= 0.0
    if np.any(zero_mask):
        valid = sigma_map[~zero_mask]
        fill = float(np.median(valid)) if valid.size else 1e-6
        sigma_map[zero_mask] = max(fill, 1e-6)
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


def _maximum_filter_2x2(image):
    values = np.asarray(image, dtype=np.float32)
    padded = np.pad(values, ((1, 0), (1, 0)), mode="edge")
    windows = [
        padded[y : y + values.shape[0], x : x + values.shape[1]]
        for y in range(2)
        for x in range(2)
    ]
    return np.maximum.reduce(windows).astype(np.float32, copy=False)


def compute_edge_map(channel):
    stretched = _auto_stretch_proxy(channel)
    kx = np.asarray([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    ky = np.asarray([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)
    if _scipy_convolve2d is not None:
        gx = _scipy_convolve2d(stretched, kx, mode="same", boundary="symm")
        gy = _scipy_convolve2d(stretched, ky, mode="same", boundary="symm")
    else:
        gx = _convolve2d_reflect(stretched, kx)
        gy = _convolve2d_reflect(stretched, ky)
    magnitude = np.sqrt(gx * gx + gy * gy)
    scale = float(np.percentile(magnitude, 98.0))
    if scale <= 1e-9:
        scale = 1e-9
    normalized = np.clip(magnitude / scale, 0.0, 1.0)
    if _scipy_maximum_filter is not None:
        return _scipy_maximum_filter(normalized, size=2).astype(np.float32)
    return _maximum_filter_2x2(normalized)


def _soft_threshold(detail, threshold):
    return np.sign(detail) * np.maximum(np.abs(detail) - threshold, 0.0)


def _pad_for_swt(image, level=_SWT_LEVELS):
    values = np.asarray(image, dtype=np.float32)
    h, w = values.shape
    factor = 2**int(level)
    pad_h = (factor - (h % factor)) % factor
    pad_w = (factor - (w % factor)) % factor
    if pad_h == 0 and pad_w == 0:
        return values, (0, 0, 0, 0)
    return np.pad(values, ((0, pad_h), (0, pad_w)), mode="reflect"), (0, pad_h, 0, pad_w)


def _multiscale_denoise_channel_swt(
    channel,
    *,
    sigma_map,
    edge_map,
    signal_map,
    fwhm_map,
    intensity,
    detail_guard,
    shadow_smoothness,
    chroma=False,
):
    padded_channel, _padding = _pad_for_swt(channel)
    coeffs = _pywt.swt2(padded_channel, wavelet=_SWT_WAVELET, level=_SWT_LEVELS)
    pad_sigma, _ = _pad_for_swt(sigma_map)
    pad_edge, _ = _pad_for_swt(edge_map)
    pad_signal, _ = _pad_for_swt(signal_map)
    pad_fwhm, _ = _pad_for_swt(fwhm_map)
    pad_sigma = pad_sigma * pad_fwhm

    strength = float(np.clip(intensity, 0.0, 1.0))
    guard_amount = float(np.clip(detail_guard, 0.0, 1.0))
    shadow_amount = float(np.clip(shadow_smoothness, 0.0, 1.0))
    layer_weights = (0.60, 0.80, 1.0, 1.0)
    new_coeffs = []

    for index, (approx, (horizontal, vertical, diagonal)) in enumerate(coeffs):
        weight = layer_weights[index] if index < len(layer_weights) else 1.0
        level_index = _SWT_LEVELS - index
        scale = 2**level_index
        chroma_degrade = 1.0 / (2 ** (4 - level_index)) if chroma else 1.0
        robust_edge = pad_edge * pad_signal * pad_fwhm
        guard_map = 1.0 + (40.0 * guard_amount * robust_edge)
        shadow_gate_active = np.clip(pad_signal * 4.0, 0.0, 1.0)
        inv_signal = 1.0 - shadow_gate_active
        boost_map = 1.0
        if shadow_amount > 0.01:
            boost_map = 1.0 + (3.0 * shadow_amount * inv_signal)

        threshold = pad_sigma * (4.5 * strength)
        threshold /= scale**0.5
        threshold *= chroma_degrade
        threshold *= weight
        threshold = (threshold / guard_map) * boost_map

        horizontal = _soft_threshold(horizontal, threshold)
        vertical = _soft_threshold(vertical, threshold)
        diagonal = _soft_threshold(diagonal, threshold)
        new_coeffs.append((approx, (horizontal, vertical, diagonal)))

    denoised = _pywt.iswt2(new_coeffs, wavelet=_SWT_WAVELET)
    h, w = np.asarray(channel).shape
    return denoised[:h, :w].astype(np.float32, copy=False)


def _multiscale_denoise_channel_fallback(
    channel,
    *,
    sigma_map,
    edge_map,
    signal_map,
    fwhm_map,
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
        robust_edge = edge_map * signal_map * fwhm_map
        guard_map = 1.0 + (40.0 * guard_amount * robust_edge)
        shadow_gate = 1.0 - np.clip(signal_map * 4.0, 0.0, 1.0)
        boost_map = 1.0 + (3.0 * shadow_amount * shadow_gate)
        threshold = (sigma_map * fwhm_map) * (4.5 * strength) * weight / np.sqrt(float(scale))
        if chroma:
            threshold *= 1.0 / (2.0 ** max(0, 3 - index))
        threshold = (threshold / guard_map) * boost_map
        reconstructed = reconstructed + _soft_threshold(detail, threshold)

    return reconstructed.astype(np.float32, copy=False)


def _multiscale_denoise_channel(
    channel,
    *,
    sigma_map,
    edge_map,
    signal_map,
    fwhm_map=None,
    intensity,
    detail_guard,
    shadow_smoothness,
    chroma=False,
):
    effective_fwhm_map = _coerce_fwhm_map(fwhm_map, np.asarray(channel).shape)
    if _pywt is not None:
        return _multiscale_denoise_channel_swt(
            channel,
            sigma_map=sigma_map,
            edge_map=edge_map,
            signal_map=signal_map,
            fwhm_map=effective_fwhm_map,
            intensity=intensity,
            detail_guard=detail_guard,
            shadow_smoothness=shadow_smoothness,
            chroma=chroma,
        )
    return _multiscale_denoise_channel_fallback(
        channel,
        sigma_map=sigma_map,
        edge_map=edge_map,
        signal_map=signal_map,
        fwhm_map=effective_fwhm_map,
        intensity=intensity,
        detail_guard=detail_guard,
        shadow_smoothness=shadow_smoothness,
        chroma=chroma,
    )


def _luminance(rgb):
    values = np.asarray(rgb, dtype=np.float32)
    return ((0.2126 * values[..., 0]) + (0.7152 * values[..., 1]) + (0.0722 * values[..., 2])).astype(np.float32)


def _average_luminance(rgb):
    values = np.asarray(rgb, dtype=np.float32)
    return np.mean(values[..., :3], axis=-1).astype(np.float32, copy=False)


def _denoise_luminance(luminance, intensity, detail_guard, adaptive_noise, shadow_smoothness, fwhm_map=None):
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
        fwhm_map=fwhm_map,
        intensity=intensity,
        detail_guard=detail_guard,
        shadow_smoothness=shadow_smoothness,
    )


def process_noise_reduction(
    image,
    *,
    intensity=0.5,
    detail_guard=50.0,
    adaptive_noise=True,
    enable_chroma=True,
    chroma_strength=30.0,
    shadow_smoothness=10.0,
    use_stars=True,
    auto_starless=True,
    star_mask=None,
    fwhm_map=None,
    protect_highlights=None,
):
    """Apply Silentium's linear multiscale denoise flow using upstream parameter scales."""

    data, layout, extras = _to_work_image(image)
    del protect_highlights

    intensity_norm = float(np.clip(intensity, 0.0, 2.0)) / 2.0
    guard_norm = float(np.clip(detail_guard, 0.0, 100.0)) / 100.0
    chroma_norm = float(np.clip(chroma_strength, 0.0, 100.0)) / 100.0
    shadow_norm = float(np.clip(shadow_smoothness, 0.0, 100.0)) / 100.0
    star_alpha = _coerce_star_mask(star_mask, data.shape[:2]) if use_stars else None
    if star_alpha is not None and auto_starless and float(np.max(star_alpha)) < 0.1:
        star_alpha = None
    effective_fwhm_map = _coerce_fwhm_map(fwhm_map, data.shape[:2])

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
            fwhm_map=effective_fwhm_map,
            intensity=intensity_norm,
            detail_guard=guard_norm,
            shadow_smoothness=shadow_norm,
        )
        if star_alpha is not None:
            blend_strength = 1.5 if shadow_norm > 0.1 else 0.7
            alpha = np.clip(star_alpha * blend_strength, 0.0, 1.0)
            result = result * (1.0 - alpha) + luminance * alpha
        return _from_work_image(result, layout, extras)

    rgb = np.asarray(data, dtype=np.float32)
    signal_source = _average_luminance(rgb)
    signal_map = compute_signal_probability(signal_source)

    if enable_chroma:
        lab = _rgb_to_lab(rgb)
        lightness = np.clip(lab[..., 0] / 100.0, 0.0, 1.0)
        edge_map = compute_edge_map(lightness)
        if adaptive_noise:
            sigma_l = estimate_noise_map(lightness)
        else:
            sigma_l = np.full_like(lightness, robust_sigma(lightness), dtype=np.float32)
        lightness_dn = _multiscale_denoise_channel(
            lightness,
            sigma_map=sigma_l,
            edge_map=edge_map,
            signal_map=signal_map,
            fwhm_map=effective_fwhm_map,
            intensity=intensity_norm,
            detail_guard=guard_norm,
            shadow_smoothness=shadow_norm,
        )

        lab_out = lab.copy()
        lab_out[..., 0] = np.clip(lightness_dn, 0.0, 1.0) * 100.0
        if chroma_norm > 0.01:
            soft_guard = guard_norm * 0.5
            for channel in (1, 2):
                chroma_plane = lab[..., channel]
                if adaptive_noise:
                    sigma_chroma = estimate_noise_map(chroma_plane)
                else:
                    sigma_chroma = np.full_like(chroma_plane, max(float(np.std(chroma_plane)), 1e-6), dtype=np.float32)
                lab_out[..., channel] = _multiscale_denoise_channel(
                    chroma_plane,
                    sigma_map=sigma_chroma,
                    edge_map=edge_map,
                    signal_map=signal_map,
                    fwhm_map=effective_fwhm_map,
                    intensity=chroma_norm,
                    detail_guard=soft_guard,
                    shadow_smoothness=shadow_norm * 0.5,
                    chroma=True,
                )
        result = _lab_to_rgb(lab_out)
    else:
        luminance = signal_source
        if adaptive_noise:
            sigma_map = estimate_noise_map(luminance)
        else:
            sigma_map = np.full_like(luminance, robust_sigma(luminance), dtype=np.float32)
        edge_map = compute_edge_map(luminance)
        luminance_dn = _multiscale_denoise_channel(
            luminance,
            sigma_map=sigma_map,
            edge_map=edge_map,
            signal_map=signal_map,
            fwhm_map=effective_fwhm_map,
            intensity=intensity_norm,
            detail_guard=guard_norm,
            shadow_smoothness=shadow_norm,
        )
        ratio = rgb / np.maximum(luminance[..., np.newaxis], 1e-8)
        result = np.clip(luminance_dn[..., np.newaxis], 0.0, 1.0) * ratio

    if star_alpha is not None:
        blend_strength = 1.5 if shadow_norm > 0.1 else 0.7
        alpha = np.clip(star_alpha[..., np.newaxis] * blend_strength, 0.0, 1.0)
        result = result * (1.0 - alpha) + rgb * alpha

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
    integration_gain = snr_gain**2.0
    pedestal_shift = median_den - median_orig

    return (
        "\n------------------------------------------------------------\n"
        " VERALUX SILENTIUM - SHADOW REPORT\n"
        "------------------------------------------------------------\n"
        f" > Background Noise (Sigma): {sigma_orig:.5f} -> {sigma_den:.5f}\n"
        f" > Noise Reduction: -{reduction_pct:.1f}%\n"
        f" > SNR Improvement: {snr_gain:.2f}x\n"
        f" > Effective Integration: +{integration_gain:.1f}x equivalent time\n"
        f" > Pedestal Shift (Blacks): {pedestal_shift:+.6f} (Flux conservation)\n"
        "------------------------------------------------------------\n"
    )

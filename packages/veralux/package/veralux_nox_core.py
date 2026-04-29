# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Nox by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Nox.py
# Upstream baseline: a9fb2c7f505c488f5cfef5b7fa5022097551e06e; local port notes: see UPSTREAM.md.

"""VeraLux Nox gradient-reduction core."""

from __future__ import annotations

import numpy as np


UPSTREAM_VERSION = "1.0.1"


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
        raise ValueError("VeraLux Nox expects a 2D mono or 3D RGB image")

    if img.shape[-1] >= 3:
        extras = img[..., 3:] if img.shape[-1] > 3 else None
        return img[..., :3], "hwc", extras
    if img.shape[-1] == 1:
        return img[..., 0], "hwc_mono", None

    if img.shape[0] == 3:
        return np.moveaxis(img[:3], 0, -1), "chw", None
    if img.shape[0] == 1:
        return img[0], "chw_mono", None

    raise ValueError("VeraLux Nox expects RGB images to have at least 3 channels")


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


def luminance(image):
    """Return a Rec.709-style luminance plane from mono, HWC RGB, or CHW RGB input."""

    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim == 2:
        return img.astype(np.float32, copy=False)
    if img.ndim != 3:
        raise ValueError("VeraLux Nox luminance expects a 2D mono or 3D RGB image")
    if img.shape[-1] >= 3:
        return (
            0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
        ).astype(np.float32)
    if img.shape[0] >= 3:
        return (0.2126 * img[0] + 0.7152 * img[1] + 0.0722 * img[2]).astype(np.float32)
    return np.squeeze(img).astype(np.float32, copy=False)


def _resize_bilinear(image, out_h, out_w):
    values = np.asarray(image, dtype=np.float32)
    if values.ndim != 2:
        raise ValueError("VeraLux Nox resize expects a 2D plane")
    h, w = values.shape
    out_h = int(max(1, out_h))
    out_w = int(max(1, out_w))
    if h == out_h and w == out_w:
        return values.copy()
    if h == 1:
        ys = np.zeros((out_h,), dtype=np.float32)
    else:
        ys = np.linspace(0.0, float(h - 1), out_h, dtype=np.float32)
    if w == 1:
        xs = np.zeros((out_w,), dtype=np.float32)
    else:
        xs = np.linspace(0.0, float(w - 1), out_w, dtype=np.float32)

    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = np.minimum(y0 + 1, h - 1)
    x1 = np.minimum(x0 + 1, w - 1)
    wy = (ys - y0.astype(np.float32))[:, np.newaxis]
    wx = (xs - x0.astype(np.float32))[np.newaxis, :]

    top = values[y0[:, np.newaxis], x0[np.newaxis, :]] * (1.0 - wx) + values[
        y0[:, np.newaxis], x1[np.newaxis, :]
    ] * wx
    bottom = values[y1[:, np.newaxis], x0[np.newaxis, :]] * (1.0 - wx) + values[
        y1[:, np.newaxis], x1[np.newaxis, :]
    ] * wx
    return (top * (1.0 - wy) + bottom * wy).astype(np.float32, copy=False)


def _box_blur_reflect(image, radius):
    values = np.asarray(image, dtype=np.float32)
    radius = int(max(0, radius))
    if radius <= 0:
        return values.copy()

    kernel_size = radius * 2 + 1
    padded = np.pad(values, ((0, 0), (radius, radius)), mode="reflect")
    integral = np.cumsum(padded, axis=1, dtype=np.float32)
    integral = np.pad(integral, ((0, 0), (1, 0)), mode="constant")
    horizontal = (integral[:, kernel_size:] - integral[:, :-kernel_size]) / float(kernel_size)

    padded = np.pad(horizontal, ((radius, radius), (0, 0)), mode="reflect")
    integral = np.cumsum(padded, axis=0, dtype=np.float32)
    integral = np.pad(integral, ((1, 0), (0, 0)), mode="constant")
    return ((integral[kernel_size:, :] - integral[:-kernel_size, :]) / float(kernel_size)).astype(
        np.float32,
        copy=False,
    )


def compute_signal_mask(channel):
    """Return 0 for background and 1 for protected structure/bright signal."""

    values = np.asarray(normalize_input(channel), dtype=np.float32)
    median = float(np.median(values))
    sigma = robust_sigma(values)
    brightness = np.clip(
        (values - (median + 0.85 * sigma)) / max(3.0 * sigma, 1e-9),
        0.0,
        1.0,
    )

    smooth = _box_blur_reflect(values, radius=4)
    detail = np.abs(values - smooth)
    detail_sigma = robust_sigma(detail)
    texture = np.clip(
        (detail - np.median(detail)) / max(5.0 * detail_sigma, 1e-9),
        0.0,
        1.0,
    )

    signal = np.maximum(brightness, texture)
    signal = _box_blur_reflect(signal, radius=2)
    return np.clip(signal, 0.0, 1.0).astype(np.float32, copy=False)


def _edge_replicated_neighbors(model):
    up = np.vstack([model[:1, :], model[:-1, :]])
    down = np.vstack([model[1:, :], model[-1:, :]])
    left = np.hstack([model[:, :1], model[:, :-1]])
    right = np.hstack([model[:, 1:], model[:, -1:]])
    return (up + down + left + right) * 0.25


def _weighted_sky_value(values, weights):
    sample = np.asarray(values, dtype=np.float32).reshape(-1)
    sample_weights = np.asarray(weights, dtype=np.float32).reshape(-1)
    good = sample_weights > 0.15
    if np.any(good):
        return float(np.median(sample[good]))
    return float(np.median(sample))


def estimate_background_model(
    image,
    *,
    auto_mask=True,
    stiffness=2.0,
    model_grid=64,
    user_mask=None,
):
    """Estimate the broad additive background field for one channel."""

    values = np.asarray(normalize_input(image), dtype=np.float32)
    if values.ndim != 2:
        raise ValueError("VeraLux Nox background estimation expects a 2D channel")

    h, w = values.shape
    grid = int(np.clip(round(float(model_grid)), 16, 160))
    grid_h = int(np.clip(grid, 12, max(12, h)))
    grid_w = int(np.clip(round(grid * (w / max(h, 1))), 12, max(12, w)))

    if auto_mask:
        sky_weights = 1.0 - compute_signal_mask(values)
    else:
        sky_weights = np.ones_like(values, dtype=np.float32)
    if user_mask is not None:
        mask = np.asarray(user_mask, dtype=np.float32)
        if mask.shape != values.shape:
            mask = _resize_bilinear(mask, h, w)
        sky_weights *= 1.0 - np.clip(mask, 0.0, 1.0)
    sky_weights = np.clip(sky_weights, 0.02, 1.0).astype(np.float32, copy=False)

    y_grid = _resize_bilinear(values, grid_h, grid_w)
    w_grid = np.clip(_resize_bilinear(sky_weights, grid_h, grid_w), 0.02, 1.0)
    sky = _weighted_sky_value(y_grid, w_grid)
    model = y_grid * w_grid + sky * (1.0 - w_grid)

    stiffness = float(np.clip(stiffness, 1.0, 4.0))
    smooth_lambda = 0.55 + stiffness * 1.35
    high_rejection = 0.65 if auto_mask else 0.10
    iterations = int(80 + stiffness * 28)

    for _ in range(iterations):
        neighbors = _edge_replicated_neighbors(model)
        positive_residual = np.clip((y_grid - model) / max(robust_sigma(y_grid), 1e-6), 0.0, 6.0)
        dynamic_weights = w_grid * (1.0 - high_rejection * np.clip(positive_residual / 3.0, 0.0, 1.0))
        dynamic_weights = np.clip(dynamic_weights, 0.01, 1.0)
        model = (dynamic_weights * y_grid + smooth_lambda * neighbors) / (
            dynamic_weights + smooth_lambda
        )

    return _resize_bilinear(model, h, w).astype(np.float32, copy=False)


def calculate_heuristics(image, star_mask=None):
    """Return bounded Nox stiffness and rejection-power values from image statistics."""

    lum = luminance(image)
    signal = compute_signal_mask(lum)
    if star_mask is not None:
        stars = np.asarray(star_mask, dtype=np.float32)
        if stars.shape != lum.shape:
            stars = _resize_bilinear(stars, lum.shape[0], lum.shape[1])
        signal = np.maximum(signal, np.clip(stars, 0.0, 1.0))

    background = lum[signal < 0.45]
    if background.size < max(64, lum.size // 20):
        background = lum.reshape(-1)

    background_sigma = robust_sigma(background)
    full_sigma = robust_sigma(lum)
    signal_density = float(np.mean(signal > 0.35))
    gradient_span = float(np.percentile(background, 92.0) - np.percentile(background, 8.0))

    stiffness = np.clip(1.2 + 9.0 * gradient_span + 1.5 * background_sigma, 1.0, 4.0)
    rejection_power = np.clip(32.0 + signal_density * 75.0 + 120.0 * full_sigma, 25.0, 72.0)
    return float(stiffness), float(rejection_power)


def _target_sky(model, signal_mask):
    sky = np.asarray(model, dtype=np.float32)
    mask = np.asarray(signal_mask, dtype=np.float32)
    sample = sky[mask < 0.35]
    if sample.size < 16:
        sample = sky.reshape(-1)
    return float(np.percentile(sample, 20.0))


def _correct_channel(
    channel,
    *,
    stiffness,
    rejection_power,
    correction_strength,
    model_grid,
    auto_mask,
    user_mask=None,
):
    values = np.asarray(channel, dtype=np.float32)
    signal = compute_signal_mask(values) if auto_mask else np.zeros_like(values, dtype=np.float32)
    model = estimate_background_model(
        values,
        auto_mask=auto_mask,
        stiffness=stiffness,
        model_grid=model_grid,
        user_mask=user_mask,
    )
    target = _target_sky(model, signal)
    strength = float(np.clip(correction_strength, 0.0, 1.25))
    strength *= float(np.clip(0.50 + 0.50 * (float(rejection_power) / 72.0), 0.35, 1.0))
    corrected = values - strength * (model - target)

    # Nox is a background extractor; high-confidence signal belongs to the source image.
    restore = np.clip((signal - 0.35) / 0.50, 0.0, 1.0)
    corrected = corrected * (1.0 - restore * 0.92) + values * (restore * 0.92)
    return np.clip(corrected, 0.0, 1.0).astype(np.float32, copy=False), model


def process_gradient_reduction(
    image,
    *,
    stiffness=2.0,
    rejection_power=55.0,
    correction_strength=1.0,
    model_grid=64,
    auto_mask=True,
    user_mask=None,
    return_model=False,
):
    """Apply VeraLux Nox-style additive gradient reduction and preserve source layout."""

    work, layout, extras = _to_work_image(image)
    stiffness = float(np.clip(stiffness, 1.0, 4.0))
    rejection_power = float(np.clip(rejection_power, 25.0, 72.0))

    if work.ndim == 2:
        result, model = _correct_channel(
            work,
            stiffness=stiffness,
            rejection_power=rejection_power,
            correction_strength=correction_strength,
            model_grid=model_grid,
            auto_mask=auto_mask,
            user_mask=user_mask,
        )
        if return_model:
            return _from_work_image(result, layout, extras), model.astype(np.float32, copy=False)
        return _from_work_image(result, layout, extras)

    corrected_channels = []
    model_channels = []
    for channel_index in range(3):
        result, model = _correct_channel(
            work[..., channel_index],
            stiffness=stiffness,
            rejection_power=rejection_power,
            correction_strength=correction_strength,
            model_grid=model_grid,
            auto_mask=auto_mask,
            user_mask=user_mask,
        )
        corrected_channels.append(result)
        model_channels.append(model)

    corrected = np.stack(corrected_channels, axis=-1)
    models = np.stack(model_channels, axis=-1)
    if return_model:
        return _from_work_image(corrected, layout, extras), _from_work_image(models, layout, None)
    return _from_work_image(corrected, layout, extras)

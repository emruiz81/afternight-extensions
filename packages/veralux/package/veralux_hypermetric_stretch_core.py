# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Ported from VeraLux HyperMetric Stretch by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_HyperMetric_Stretch.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux HyperMetric Stretch core."""

from __future__ import annotations

import numpy as np


UPSTREAM_VERSION = "1.5.2"
DEFAULT_PROFILE = "Rec.709 (Recommended)"
RTU_PEDESTAL = 0.001
RTU_SOFT_CEIL_PERCENTILE = 99.0


SENSOR_PROFILES = {
    "Rec.709 (Recommended)": {
        "weights": (0.2126, 0.7152, 0.0722),
        "description": "ITU-R BT.709 standard for sRGB/HDTV",
        "category": "standard",
    },
    "Sony IMX571 (ASI2600/QHY268)": {
        "weights": (0.2944, 0.5021, 0.2035),
        "description": "Sony IMX571 26MP APS-C BSI",
        "category": "sensor-specific",
    },
    "Sony IMX455 (ASI6200/QHY600)": {
        "weights": (0.2987, 0.5001, 0.2013),
        "description": "Sony IMX455 61MP Full Frame BSI",
        "category": "sensor-specific",
    },
    "Sony IMX410 (ASI2400)": {
        "weights": (0.3015, 0.5050, 0.1935),
        "description": "Sony IMX410 24MP Full Frame",
        "category": "sensor-specific",
    },
    "Sony IMX269 (Altair/ToupTek)": {
        "weights": (0.3040, 0.5010, 0.1950),
        "description": "Sony IMX269 20MP 4/3 inch BSI",
        "category": "sensor-specific",
    },
    "Sony IMX294 (ASI294)": {
        "weights": (0.3068, 0.5008, 0.1925),
        "description": "Sony IMX294 11.7MP 4/3 inch BSI",
        "category": "sensor-specific",
    },
    "Sony IMX533 (ASI533)": {
        "weights": (0.2910, 0.5072, 0.2018),
        "description": "Sony IMX533 9MP square BSI",
        "category": "sensor-specific",
    },
    "Sony IMX676 (ASI676)": {
        "weights": (0.2880, 0.5100, 0.2020),
        "description": "Sony IMX676 12MP square BSI",
        "category": "sensor-specific",
    },
    "Sony IMX585 (ASI585) - STARVIS 2": {
        "weights": (0.3431, 0.4822, 0.1747),
        "description": "Sony IMX585 8.3MP STARVIS 2",
        "category": "sensor-specific",
    },
    "Sony IMX662 (ASI662) - STARVIS 2": {
        "weights": (0.3430, 0.4821, 0.1749),
        "description": "Sony IMX662 STARVIS 2",
        "category": "sensor-specific",
    },
    "Sony IMX678 (ASI678) - STARVIS 2": {
        "weights": (0.3426, 0.4825, 0.1750),
        "description": "Sony IMX678 STARVIS 2",
        "category": "sensor-specific",
    },
    "Sony IMX462 (ASI462)": {
        "weights": (0.3333, 0.4866, 0.1801),
        "description": "Sony IMX462 2MP high-NIR sensor",
        "category": "sensor-specific",
    },
    "Sony IMX715 (ASI715)": {
        "weights": (0.3410, 0.4840, 0.1750),
        "description": "Sony IMX715 STARVIS 2",
        "category": "sensor-specific",
    },
    "Sony IMX482 (ASI482)": {
        "weights": (0.3150, 0.4950, 0.1900),
        "description": "Sony IMX482 large-pixel sensor",
        "category": "sensor-specific",
    },
    "Sony IMX183 (ASI183)": {
        "weights": (0.2967, 0.4983, 0.2050),
        "description": "Sony IMX183 20MP 1 inch BSI",
        "category": "sensor-specific",
    },
    "Sony IMX178 (ASI178)": {
        "weights": (0.2346, 0.5206, 0.2448),
        "description": "Sony IMX178 6.4MP BSI",
        "category": "sensor-specific",
    },
    "Sony IMX224 (ASI224)": {
        "weights": (0.3402, 0.4765, 0.1833),
        "description": "Sony IMX224 planetary sensor",
        "category": "sensor-specific",
    },
    "Canon EOS (Modern - 60D/600D/500D)": {
        "weights": (0.2600, 0.5200, 0.2200),
        "description": "Canon CMOS Digic 4/5 era",
        "category": "sensor-specific",
    },
    "Canon EOS (Legacy - 300D/40D/20D)": {
        "weights": (0.2450, 0.5350, 0.2200),
        "description": "Canon CMOS Digic 2/3 era",
        "category": "sensor-specific",
    },
    "Nikon DSLR (Modern - D5100/D7200)": {
        "weights": (0.2650, 0.5100, 0.2250),
        "description": "Nikon modern DX/FX CMOS",
        "category": "sensor-specific",
    },
    "Nikon DSLR (Legacy - D3/D300/D90)": {
        "weights": (0.2500, 0.5300, 0.2200),
        "description": "Nikon legacy CMOS",
        "category": "sensor-specific",
    },
    "Fujifilm X-Trans 5 HR": {
        "weights": (0.2800, 0.5100, 0.2100),
        "description": "Fujifilm X-Trans 5 40MP",
        "category": "sensor-specific",
    },
    "Panasonic MN34230 (ASI1600)": {
        "weights": (0.2650, 0.5250, 0.2100),
        "description": "Panasonic MN34230 4/3 inch CMOS",
        "category": "sensor-specific",
    },
    "ZWO Seestar S50": {
        "weights": (0.3333, 0.4866, 0.1801),
        "description": "ZWO Seestar S50",
        "category": "sensor-specific",
    },
    "ZWO Seestar S30": {
        "weights": (0.2928, 0.5053, 0.2019),
        "description": "ZWO Seestar S30",
        "category": "sensor-specific",
    },
    "Narrowband HOO": {
        "weights": (0.5000, 0.2500, 0.2500),
        "description": "Bicolor palette: Ha=Red, OIII=Green+Blue",
        "category": "narrowband",
    },
    "Narrowband SHO": {
        "weights": (0.3333, 0.3400, 0.3267),
        "description": "Hubble palette: SII=Red, Ha=Green, OIII=Blue",
        "category": "narrowband",
    },
}


LAST_LINEAR_EXPANSION_DIAG = {"pct_low": 0.0, "pct_high": 0.0, "low": 0.0, "high": 0.0}


def working_space_options():
    return list(SENSOR_PROFILES.keys())


def _profile_weights(working_space):
    profile = SENSOR_PROFILES.get(str(working_space), SENSOR_PROFILES[DEFAULT_PROFILE])
    return profile["weights"]


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
        if input_dtype == np.int16:
            return img_float / 32767.0
        return img_float / 4294967295.0

    if np.issubdtype(input_dtype, np.floating):
        if img_float.size == 0:
            return img_float
        current_max = float(np.max(img_float))
        if current_max <= 1.1:
            return img_float
        if current_max < 100000.0:
            return img_float / 65535.0
        return img_float / 4294967295.0

    return img_float


def _to_channels_first(image):
    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim == 2:
        return img, "hw", None
    if img.ndim != 3:
        raise ValueError("VeraLux HyperMetric Stretch expects a 2D mono or 3D RGB image")

    if img.shape[0] in (1, 3) and img.shape[-1] not in (3, 4):
        return img[:3] if img.shape[0] == 3 else img[0], "chw" if img.shape[0] == 3 else "chw_mono", None

    if img.shape[-1] < 3:
        if img.shape[-1] == 1:
            return img[..., 0], "hwc_mono", None
        raise ValueError("VeraLux HyperMetric Stretch expects RGB images to have at least 3 channels")

    extras = img[..., 3:] if img.shape[-1] > 3 else None
    return np.moveaxis(img[..., :3], -1, 0), "hwc", extras


def _from_channels_first(data, layout, extras):
    out = np.clip(np.asarray(data, dtype=np.float32), 0.0, 1.0)
    if layout == "hw":
        return out.astype(np.float32, copy=False)
    if layout == "chw":
        return out.astype(np.float32, copy=False)
    if layout == "chw_mono":
        return out[np.newaxis, ...].astype(np.float32, copy=False)
    if layout == "hwc_mono":
        return out[..., np.newaxis].astype(np.float32, copy=False)

    out = np.moveaxis(out, 0, -1)
    if extras is not None:
        out = np.concatenate([out, np.asarray(extras, dtype=np.float32)], axis=-1)
    return out.astype(np.float32, copy=False)


def calculate_anchor(data_norm):
    data = np.asarray(data_norm, dtype=np.float32)
    if (data.ndim == 3 and data.shape[0] == 3) or (data.ndim == 2 and data.shape[0] == 3):
        stride = max(1, data.size // 500_000)
        floors = [np.percentile(data[channel].reshape(-1)[::stride], 0.5) for channel in range(3)]
        return max(0.0, float(min(floors)) - 0.00025)
    if data.ndim == 3 and data.shape[0] == 1:
        data = data[0]

    stride = max(1, data.size // 200_000)
    floor = float(np.percentile(data.reshape(-1)[::stride], 0.5))
    return max(0.0, floor - 0.00025)


def calculate_anchor_adaptive(data_norm, weights=None):
    data = np.asarray(data_norm, dtype=np.float32)
    weights = weights or _profile_weights(DEFAULT_PROFILE)
    if (data.ndim == 3 and data.shape[0] == 3) or (data.ndim == 2 and data.shape[0] == 3):
        r_w, g_w, b_w = weights
        base = (r_w * data[0]) + (g_w * data[1]) + (b_w * data[2])
    elif data.ndim == 3 and data.shape[0] == 1:
        base = data[0]
    else:
        base = data

    stride = max(1, base.size // 2_000_000)
    sample = base.reshape(-1)[::stride]
    hist, bin_edges = np.histogram(sample, bins=65536, range=(0.0, 1.0))
    hist_smooth = np.convolve(hist, np.ones(50) / 50.0, mode="same")

    search_start = 100
    if np.max(hist_smooth[:search_start]) > 0:
        search_start = 0
    peak_index = int(np.argmax(hist_smooth[search_start:]) + search_start)
    peak_value = float(hist_smooth[peak_index])
    target_value = peak_value * 0.06
    candidates = np.where(hist_smooth[:peak_index] < target_value)[0]

    if len(candidates) > 0:
        return max(0.0, float(bin_edges[candidates[-1]]))
    return max(0.0, float(np.percentile(sample, 0.5)))


def extract_luminance(data_norm, anchor, weights):
    data = np.asarray(data_norm, dtype=np.float32)
    img_anchored = np.maximum(data - float(anchor), 0.0)
    if (data.ndim == 3 and data.shape[0] == 3) or (data.ndim == 2 and data.shape[0] == 3):
        r_w, g_w, b_w = weights
        luminance = (r_w * img_anchored[0]) + (g_w * img_anchored[1]) + (b_w * img_anchored[2])
        return luminance, img_anchored
    if data.ndim == 3 and data.shape[0] == 1:
        return img_anchored[0], img_anchored[0]
    return img_anchored, img_anchored


def hyperbolic_stretch(data, stretch_d, protect_b, shadow_point=0.0):
    stretch_d = max(float(stretch_d), 0.1)
    protect_b = max(float(protect_b), 0.1)
    term1 = np.arcsinh(stretch_d * (np.asarray(data, dtype=np.float32) - shadow_point) + protect_b)
    term2 = np.arcsinh(protect_b)
    norm_factor = np.arcsinh(stretch_d * (1.0 - shadow_point) + protect_b) - term2
    if abs(norm_factor) < 1e-12:
        norm_factor = 1e-6
    return (term1 - term2) / norm_factor


def solve_log_d(luminance_sample, target_median, protect_b):
    sample = np.asarray(luminance_sample, dtype=np.float32)
    if sample.size == 0:
        return 2.0
    median_in = float(np.median(sample))
    if median_in < 1e-9:
        return 2.0

    low_log = 0.0
    high_log = 7.0
    best_log_d = 2.0
    for _ in range(40):
        mid_log = (low_log + high_log) / 2.0
        stretched = float(hyperbolic_stretch(median_in, 10.0**mid_log, protect_b))
        best_log_d = mid_log
        if abs(stretched - target_median) < 0.0001:
            break
        if stretched < target_median:
            low_log = mid_log
        else:
            high_log = mid_log
    return float(best_log_d)


def estimate_star_pressure(luminance):
    signal = np.asarray(luminance, dtype=np.float32)
    if signal.size == 0:
        return 0.0

    stride = max(1, signal.size // 300_000)
    sample = signal.reshape(-1)[::stride]
    sample = sample[sample > 1e-7]
    if sample.size < 100:
        return 0.0

    p999 = float(np.percentile(sample, 99.9))
    p9999 = float(np.percentile(sample, 99.99))
    bright_fraction = float(np.count_nonzero(sample > p999)) / float(sample.size)

    percentile_term = float(np.clip(p9999 / (p999 + 1e-9), 1.0, 5.0))
    percentile_term = (percentile_term - 1.0) / 4.0
    fraction_term = float(np.clip(bright_fraction * 200.0, 0.0, 1.0))
    return float(np.clip((0.7 * percentile_term) + (0.3 * fraction_term), 0.0, 1.0))


def _auto_solver_subsample(data):
    if data.ndim == 3 and data.shape[0] == 3:
        height, width = data.shape[1], data.shape[2]
        step = max(1, (height * width) // 100_000)
        return np.vstack(
            (
                data[0].reshape(-1)[::step],
                data[1].reshape(-1)[::step],
                data[2].reshape(-1)[::step],
            )
        )

    if data.ndim == 3 and data.shape[0] == 1:
        data = data[0]

    step = max(1, data.size // 100_000)
    return data.reshape(-1)[::step]


def solve_log_d_for_image(image, target_median=0.2, protect_b=6.0, working_space=DEFAULT_PROFILE,
                          use_adaptive_anchor=True, processing_mode="ready_to_use"):
    data, _layout, _extras = _to_channels_first(image)
    weights = _profile_weights(working_space)
    sub_data = _auto_solver_subsample(data)
    anchor = (
        calculate_anchor_adaptive(sub_data, weights=weights)
        if use_adaptive_anchor
        else calculate_anchor(sub_data)
    )
    luminance, _anchored = extract_luminance(sub_data, anchor, weights)
    star_pressure = estimate_star_pressure(luminance)
    valid = luminance.reshape(-1)
    valid = valid[valid > 1e-7]
    if valid.size == 0:
        return 2.0

    target = float(target_median)
    best_log_d = 2.0
    ready_mode = str(processing_mode) == "ready_to_use"
    for _ in range(15):
        best_log_d = solve_log_d(valid, target, float(protect_b))

        if star_pressure > 0.6:
            target *= 1.0 - (0.15 * star_pressure)

        if not ready_mode:
            break

        stretched = hyperbolic_stretch(valid, 10.0**best_log_d, float(protect_b))
        median = float(np.median(stretched))
        std = float(np.std(stretched))
        minimum = float(np.min(stretched))
        global_floor = max(minimum, median - (2.7 * std))
        if global_floor <= 0.001:
            break

        target -= 0.015
        if target < 0.05:
            break

    return float(best_log_d)


def apply_mtf(data, midtones):
    values = np.asarray(data, dtype=np.float32)
    term1 = (midtones - 1.0) * values
    term2 = (2.0 * midtones - 1.0) * values - midtones
    with np.errstate(divide="ignore", invalid="ignore"):
        out = term1 / term2
    return np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0)


def apply_linear_expansion(data, factor):
    global LAST_LINEAR_EXPANSION_DIAG

    values = np.asarray(data, dtype=np.float32)
    if float(factor) <= 0.001:
        LAST_LINEAR_EXPANSION_DIAG = {"pct_low": 0.0, "pct_high": 0.0, "low": 0.0, "high": 0.0}
        return values

    factor = float(np.clip(factor, 0.0, 1.0))
    abs_max = float(np.max(values))
    use_absolute_max = False
    if values.ndim == 2 and abs_max > 0.001:
        y_max, x_max = np.unravel_index(int(np.argmax(values)), values.shape)
        y0, y1 = max(0, y_max - 1), min(values.shape[0], y_max + 2)
        x0, x1 = max(0, x_max - 1), min(values.shape[1], x_max + 2)
        neighbors = values[y0:y1, x0:x1]
        neighbors = neighbors[neighbors < abs_max]
        if neighbors.size > 0 and float(np.max(neighbors)) >= (abs_max * 0.20):
            use_absolute_max = True

    stride = max(1, values.size // 500_000)
    sample = values.reshape(-1)[::stride]
    low = float(np.percentile(sample, 0.001))
    high = abs_max if use_absolute_max else float(np.percentile(sample, 99.999))
    if high <= low:
        LAST_LINEAR_EXPANSION_DIAG = {"pct_low": 0.0, "pct_high": 0.0, "low": low, "high": high}
        return values

    pct_low = (float(np.count_nonzero(sample <= low)) / float(sample.size)) * 100.0 if sample.size else 0.0
    pct_high = (float(np.count_nonzero(sample >= high)) / float(sample.size)) * 100.0 if sample.size else 0.0
    LAST_LINEAR_EXPANSION_DIAG = {
        "pct_low": float(pct_low),
        "pct_high": float(pct_high),
        "low": float(low),
        "high": float(high),
    }

    normalized = np.clip((values - low) / (high - low), 0.0, 1.0)
    return (values * (1.0 - factor)) + (normalized * factor)


def adaptive_output_scaling(img_data, working_space=DEFAULT_PROFILE, target_bg=0.20):
    img = np.asarray(img_data, dtype=np.float32).copy()
    luma_r, luma_g, luma_b = _profile_weights(working_space)
    is_rgb = img.ndim == 3 and img.shape[0] == 3
    luminance = (luma_r * img[0] + luma_g * img[1] + luma_b * img[2]) if is_rgb else img

    median_l = float(np.median(luminance))
    std_l = float(np.std(luminance))
    min_l = float(np.min(luminance))
    global_floor = max(min_l, median_l - 2.7 * std_l)
    abs_max = float(np.max(luminance))
    valid_physical_max = True

    if luminance.ndim == 2 and abs_max > 0.001:
        y_max, x_max = np.unravel_index(int(np.argmax(luminance)), luminance.shape)
        y0, y1 = max(0, y_max - 1), min(luminance.shape[0], y_max + 2)
        x0, x1 = max(0, x_max - 1), min(luminance.shape[1], x_max + 2)
        neighbors = luminance[y0:y1, x0:x1]
        neighbors = neighbors[neighbors < abs_max]
        if neighbors.size > 0 and float(np.max(neighbors)) < (abs_max * 0.20):
            valid_physical_max = False

    if is_rgb:
        stride = max(1, img[0].size // 500_000)
        soft_ceil = max(
            float(np.percentile(img[0].reshape(-1)[::stride], RTU_SOFT_CEIL_PERCENTILE)),
            float(np.percentile(img[1].reshape(-1)[::stride], RTU_SOFT_CEIL_PERCENTILE)),
            float(np.percentile(img[2].reshape(-1)[::stride], RTU_SOFT_CEIL_PERCENTILE)),
        )
    else:
        stride = max(1, luminance.size // 200_000)
        soft_ceil = float(np.percentile(luminance.reshape(-1)[::stride], RTU_SOFT_CEIL_PERCENTILE))

    if soft_ceil <= global_floor:
        soft_ceil = global_floor + 1e-6
    if abs_max <= soft_ceil:
        abs_max = soft_ceil + 1e-6

    scale_contrast = (0.98 - RTU_PEDESTAL) / (soft_ceil - global_floor + 1e-9)
    if valid_physical_max:
        scale_physical_limit = (1.0 - RTU_PEDESTAL) / (abs_max - global_floor + 1e-9)
        final_scale = min(scale_contrast, scale_physical_limit)
    else:
        final_scale = scale_contrast

    def expand(channel):
        return np.clip((channel - global_floor) * final_scale + RTU_PEDESTAL, 0.0, 1.0)

    if is_rgb:
        for channel in range(3):
            img[channel] = expand(img[channel])
        luminance = luma_r * img[0] + luma_g * img[1] + luma_b * img[2]
    else:
        img = expand(luminance)
        luminance = img

    current_bg = float(np.median(luminance))
    target_bg = float(target_bg)
    if 0.0 < current_bg < 1.0 and abs(current_bg - target_bg) > 1e-3:
        denominator = current_bg * (2.0 * target_bg - 1.0) - target_bg
        if abs(denominator) > 1e-9:
            midtones = (current_bg * (target_bg - 1.0)) / denominator
            if is_rgb:
                for channel in range(3):
                    img[channel] = apply_mtf(img[channel], midtones)
            else:
                img = apply_mtf(img, midtones)
    return img


def apply_ready_to_use_soft_clip(img_data, threshold=0.98, rolloff=2.0):
    def soft_clip_channel(channel):
        mask = channel > threshold
        result = channel.copy()
        if np.any(mask):
            t = np.clip((channel[mask] - threshold) / (1.0 - threshold + 1e-9), 0.0, 1.0)
            result[mask] = threshold + (1.0 - threshold) * (1.0 - np.power(1.0 - t, rolloff))
        return np.clip(result, 0.0, 1.0)

    img = np.asarray(img_data, dtype=np.float32).copy()
    if img.ndim == 3:
        for channel in range(img.shape[0]):
            img[channel] = soft_clip_channel(img[channel])
        return img
    return soft_clip_channel(img)


def effective_hybrid_params(processing_mode, color_strategy=0.0, color_grip=1.0,
                            shadow_convergence=0.0, linear_expansion=0.0):
    if processing_mode == "ready_to_use":
        strategy = float(np.clip(color_strategy, -1.0, 1.0))
        if strategy < 0:
            return 1.0, abs(strategy) * 3.0, 0.0
        return 1.0 - (strategy * 0.6), 0.0, 0.0
    return (
        float(np.clip(color_grip, 0.0, 1.0)),
        float(np.clip(shadow_convergence, 0.0, 3.0)),
        float(np.clip(linear_expansion, 0.0, 1.0)),
    )


def process_hypermetric_stretch(
    image,
    log_d=2.0,
    protect_b=6.0,
    convergence_power=3.5,
    working_space=DEFAULT_PROFILE,
    processing_mode="ready_to_use",
    target_bg=0.20,
    color_strategy=0.0,
    color_grip=1.0,
    shadow_convergence=0.0,
    linear_expansion=0.0,
    use_adaptive_anchor=True,
    auto_log_d=False,
):
    """Apply VeraLux HyperMetric Stretch and preserve the input image layout."""

    data, layout, extras = _to_channels_first(image)
    data = np.asarray(data, dtype=np.float32).copy()
    weights = _profile_weights(working_space)
    mode = "scientific" if processing_mode == "scientific" else "ready_to_use"
    grip, shadow, expansion = effective_hybrid_params(
        mode,
        color_strategy=color_strategy,
        color_grip=color_grip,
        shadow_convergence=shadow_convergence,
        linear_expansion=linear_expansion,
    )

    if auto_log_d:
        log_d = solve_log_d_for_image(data, target_bg, protect_b, working_space, use_adaptive_anchor, mode)

    anchor = (
        calculate_anchor_adaptive(data, weights=weights)
        if use_adaptive_anchor
        else calculate_anchor(data)
    )
    luminance, anchored = extract_luminance(data, anchor, weights)

    epsilon = 1e-9
    is_rgb = data.ndim == 3 and data.shape[0] == 3
    if is_rgb:
        luminance_safe = luminance + epsilon
        ratios = [anchored[index] / luminance_safe for index in range(3)]

    luminance_stretched = np.clip(
        hyperbolic_stretch(luminance, 10.0 ** float(log_d), float(protect_b)),
        0.0,
        1.0,
    )

    global LAST_LINEAR_EXPANSION_DIAG
    if mode == "ready_to_use" or expansion <= 0.001:
        LAST_LINEAR_EXPANSION_DIAG = {"pct_low": 0.0, "pct_high": 0.0, "low": 0.0, "high": 0.0}
    elif expansion > 0.001:
        luminance_stretched = np.clip(apply_linear_expansion(luminance_stretched, expansion), 0.0, 1.0)

    if is_rgb:
        convergence = np.power(luminance_stretched, float(convergence_power))
        final = np.zeros_like(data)
        for index in range(3):
            channel_ratio = ratios[index] * (1.0 - convergence) + convergence
            final[index] = luminance_stretched * channel_ratio

        if grip < 1.0 or shadow > 0.01:
            stretch_d = 10.0 ** float(log_d)
            scalar = np.zeros_like(final)
            for index in range(3):
                scalar[index] = hyperbolic_stretch(anchored[index], stretch_d, protect_b)
            scalar = np.clip(scalar, 0.0, 1.0)
            grip_map = np.full_like(luminance_stretched, grip)
            if shadow > 0.01:
                grip_map = grip_map * np.power(luminance_stretched, shadow)
            final = (final * grip_map) + (scalar * (1.0 - grip_map))
    else:
        final = luminance_stretched

    final = np.clip((final * 0.995) + 0.005, 0.0, 1.0).astype(np.float32)
    if mode == "ready_to_use":
        final = adaptive_output_scaling(final, working_space, target_bg)
        final = apply_ready_to_use_soft_clip(final, 0.98, 2.0)

    return _from_channels_first(final, layout, extras)

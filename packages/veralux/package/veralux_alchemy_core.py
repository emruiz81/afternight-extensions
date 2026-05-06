# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Alchemy) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Alchemy.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux Alchemy linear narrowband normalization and mixing core."""

from __future__ import annotations

import numpy as np


UPSTREAM_VERSION = "1.0.3"

PALETTE_PRESETS = {
    "preset_hoo": {"mix_r": 0.0, "mix_g": 1.0, "mix_b": 1.0},
    "preset_pseudo_sho": {"mix_r": 0.0, "mix_g": 0.5, "mix_b": 1.0},
    "preset_hso": {"mix_r": 0.0, "mix_g": 0.0, "mix_b": 1.0},
}


QUANTUM_COEFFS = {
    "Generic OSC": {
        "r1": 0.000,
        "r2": 1.000,
        "r3": 1.000,
        "g1": 1.000,
        "g2": 0.000,
        "g3": 0.000,
        "b1": 1.000,
        "b2": 0.000,
        "b3": 0.000,
    },
    "Sony IMX071": {"r1": 0.031, "r2": 0.776, "r3": 0.697, "g1": 0.730, "g2": 0.106, "g3": 0.090, "b1": 0.518, "b2": 0.033, "b3": 0.027},
    "Sony IMX178": {"r1": 0.024, "r2": 0.354, "r3": 0.111, "g1": 0.680, "g2": 0.053, "g3": 0.012, "b1": 0.370, "b2": 0.022, "b3": 0.006},
    "Sony IMX183": {"r1": 0.038, "r2": 0.665, "r3": 0.627, "g1": 0.722, "g2": 0.162, "g3": 0.122, "b1": 0.505, "b2": 0.075, "b3": 0.058},
    "Sony IMX193": {"r1": 0.041, "r2": 0.658, "r3": 0.672, "g1": 0.792, "g2": 0.134, "g3": 0.116, "b1": 0.395, "b2": 0.016, "b3": 0.013},
    "Sony IMX224": {"r1": 0.050, "r2": 0.656, "r3": 0.624, "g1": 0.812, "g2": 0.139, "g3": 0.112, "b1": 0.504, "b2": 0.033, "b3": 0.022},
    "Sony IMX269": {"r1": 0.037, "r2": 0.669, "r3": 0.579, "g1": 0.835, "g2": 0.125, "g3": 0.091, "b1": 0.577, "b2": 0.020, "b3": 0.013},
    "Sony IMX294": {"r1": 0.031, "r2": 0.658, "r3": 0.686, "g1": 0.902, "g2": 0.149, "g3": 0.166, "b1": 0.501, "b2": 0.052, "b3": 0.058},
    "Sony IMX385": {"r1": 0.054, "r2": 0.945, "r3": 0.871, "g1": 0.842, "g2": 0.476, "g3": 0.417, "b1": 0.518, "b2": 0.082, "b3": 0.076},
    "Sony IMX410": {"r1": 0.045, "r2": 0.658, "r3": 0.620, "g1": 0.803, "g2": 0.142, "g3": 0.119, "b1": 0.501, "b2": 0.030, "b3": 0.021},
    "Sony IMX415": {"r1": 0.077, "r2": 0.873, "r3": 0.811, "g1": 0.951, "g2": 0.283, "g3": 0.281, "b1": 0.771, "b2": 0.127, "b3": 0.119},
    "Sony IMX455": {"r1": 0.033, "r2": 0.651, "r3": 0.590, "g1": 0.672, "g2": 0.063, "g3": 0.081, "b1": 0.407, "b2": 0.018, "b3": 0.035},
    "Sony IMX462": {"r1": 0.043, "r2": 0.697, "r3": 0.825, "g1": 0.840, "g2": 0.321, "g3": 0.510, "b1": 0.490, "b2": 0.158, "b3": 0.315},
    "Sony IMX477": {"r1": 0.079, "r2": 0.741, "r3": 0.718, "g1": 0.970, "g2": 0.134, "g3": 0.108, "b1": 0.497, "b2": 0.040, "b3": 0.035},
    "Sony IMX482": {"r1": 0.038, "r2": 0.658, "r3": 0.686, "g1": 0.902, "g2": 0.149, "g3": 0.166, "b1": 0.501, "b2": 0.052, "b3": 0.058},
    "Sony IMX533": {"r1": 0.029, "r2": 0.803, "r3": 0.743, "g1": 0.893, "g2": 0.161, "g3": 0.176, "b1": 0.504, "b2": 0.051, "b3": 0.076},
    "Sony IMX571": {"r1": 0.023, "r2": 0.822, "r3": 0.757, "g1": 0.852, "g2": 0.083, "g3": 0.082, "b1": 0.501, "b2": 0.022, "b3": 0.035},
    "Sony IMX585": {"r1": 0.075, "r2": 0.983, "r3": 0.966, "g1": 0.835, "g2": 0.198, "g3": 0.252, "b1": 0.435, "b2": 0.052, "b3": 0.079},
    "Sony IMX662": {"r1": 0.043, "r2": 0.768, "r3": 0.840, "g1": 0.884, "g2": 0.286, "g3": 0.457, "b1": 0.493, "b2": 0.080, "b3": 0.139},
    "Sony IMX676": {"r1": 0.063, "r2": 0.648, "r3": 0.612, "g1": 0.865, "g2": 0.126, "g3": 0.103, "b1": 0.491, "b2": 0.038, "b3": 0.031},
    "Sony IMX678": {"r1": 0.067, "r2": 0.609, "r3": 0.611, "g1": 0.916, "g2": 0.150, "g3": 0.128, "b1": 0.494, "b2": 0.037, "b3": 0.031},
    "Sony IMX715": {"r1": 0.072, "r2": 0.665, "r3": 0.672, "g1": 0.871, "g2": 0.136, "g3": 0.124, "b1": 0.502, "b2": 0.043, "b3": 0.035},
    "Canon EOS 1D Mark III": {"r1": 0.010, "r2": 0.231, "r3": 0.147, "g1": 0.947, "g2": 0.034, "g3": 0.007, "b1": 0.679, "b2": 0.001, "b3": 0.001},
    "Canon EOS 20D": {"r1": 0.014, "r2": 0.244, "r3": 0.131, "g1": 0.845, "g2": 0.043, "g3": 0.024, "b1": 0.513, "b2": 0.002, "b3": 0.003},
    "Canon EOS 300D": {"r1": 0.008, "r2": 0.232, "r3": 0.063, "g1": 0.702, "g2": 0.012, "g3": 0.010, "b1": 0.485, "b2": 0.001, "b3": 0.001},
    "Canon EOS 40D": {"r1": 0.020, "r2": 0.224, "r3": 0.134, "g1": 0.916, "g2": 0.022, "g3": 0.012, "b1": 0.536, "b2": 0.004, "b3": 0.006},
    "Canon EOS 500D": {"r1": 0.081, "r2": 0.247, "r3": 0.128, "g1": 0.835, "g2": 0.038, "g3": 0.028, "b1": 0.577, "b2": 0.002, "b3": 0.000},
    "Canon EOS 50D": {"r1": 0.080, "r2": 0.231, "r3": 0.117, "g1": 0.843, "g2": 0.043, "g3": 0.024, "b1": 0.565, "b2": 0.004, "b3": 0.002},
    "Canon EOS 600D": {"r1": 0.035, "r2": 0.187, "r3": 0.125, "g1": 0.825, "g2": 0.024, "g3": 0.018, "b1": 0.521, "b2": 0.002, "b3": 0.001},
    "Canon EOS 60D": {"r1": 0.035, "r2": 0.212, "r3": 0.126, "g1": 0.819, "g2": 0.023, "g3": 0.017, "b1": 0.535, "b2": 0.002, "b3": 0.001},
    "Nikon D200": {"r1": 0.040, "r2": 0.219, "r3": 0.062, "g1": 0.556, "g2": 0.009, "g3": 0.005, "b1": 0.505, "b2": 0.001, "b3": 0.000},
    "Nikon D3": {"r1": 0.040, "r2": 0.193, "r3": 0.063, "g1": 0.574, "g2": 0.008, "g3": 0.005, "b1": 0.506, "b2": 0.001, "b3": 0.000},
    "Nikon D3X": {"r1": 0.029, "r2": 0.201, "r3": 0.120, "g1": 0.649, "g2": 0.013, "g3": 0.009, "b1": 0.523, "b2": 0.001, "b3": 0.001},
    "Nikon D300s": {"r1": 0.049, "r2": 0.222, "r3": 0.039, "g1": 0.533, "g2": 0.011, "g3": 0.008, "b1": 0.537, "b2": 0.003, "b3": 0.005},
    "Nikon D40": {"r1": 0.020, "r2": 0.133, "r3": 0.108, "g1": 0.560, "g2": 0.003, "g3": 0.003, "b1": 0.722, "b2": 0.001, "b3": 0.001},
    "Nikon D50": {"r1": 0.019, "r2": 0.158, "r3": 0.085, "g1": 0.524, "g2": 0.003, "g3": 0.004, "b1": 0.381, "b2": 0.001, "b3": 0.002},
    "Nikon D5100": {"r1": 0.044, "r2": 0.177, "r3": 0.078, "g1": 0.661, "g2": 0.018, "g3": 0.011, "b1": 0.521, "b2": 0.003, "b3": 0.004},
    "Nikon D700": {"r1": 0.040, "r2": 0.198, "r3": 0.074, "g1": 0.589, "g2": 0.007, "g3": 0.004, "b1": 0.505, "b2": 0.001, "b3": 0.001},
    "Nikon D7200": {"r1": 0.073, "r2": 0.093, "r3": 0.074, "g1": 0.532, "g2": 0.010, "g3": 0.011, "b1": 0.518, "b2": 0.006, "b3": 0.009},
    "Nikon D80": {"r1": 0.022, "r2": 0.179, "r3": 0.048, "g1": 0.509, "g2": 0.007, "g3": 0.005, "b1": 0.490, "b2": 0.001, "b3": 0.001},
    "Nikon D90": {"r1": 0.044, "r2": 0.240, "r3": 0.059, "g1": 0.547, "g2": 0.013, "g3": 0.011, "b1": 0.511, "b2": 0.002, "b3": 0.002},
    "Fujifilm X-Trans 5 HR": {"r1": 0.051, "r2": 0.049, "r3": 0.047, "g1": 0.413, "g2": 0.697, "g3": 0.724, "b1": 0.377, "b2": 0.650, "b3": 0.670},
    "Samsung ISOCELL": {"r1": 0.144, "r2": 0.665, "r3": 0.675, "g1": 0.499, "g2": 0.082, "g3": 0.063, "b1": 0.353, "b2": 0.055, "b3": 0.071},
    "ZWO Seestar S30": {"r1": 0.063, "r2": 0.648, "r3": 0.612, "g1": 0.865, "g2": 0.126, "g3": 0.103, "b1": 0.491, "b2": 0.038, "b3": 0.031},
    "ZWO Seestar S50": {"r1": 0.024, "r2": 0.822, "r3": 0.757, "g1": 0.852, "g2": 0.083, "g3": 0.082, "b1": 0.501, "b2": 0.022, "b3": 0.035},
}


def sensor_profile_names():
    return list(QUANTUM_COEFFS.keys())


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


def calc_stats(channel):
    """Return robust median, MAD, and high-percentile signal strength."""

    values = np.asarray(channel, dtype=np.float32)
    if values.size == 0:
        raise ValueError("Cannot compute channel statistics for an empty image")

    stride = max(1, values.size // 1_000_000)
    sample = values.reshape(-1)[::stride]
    median = float(np.median(sample))
    mad = float(np.median(np.abs(sample - median)))
    peak = float(np.percentile(sample, 99.5))
    signal_strength = max(1e-9, peak - median)
    return median, mad, signal_strength


def linear_fit_channels(rgb_channels, align_bg=True, auto_gain=True, manual_boost=1.0):
    """Align green/blue background and signal strength to the red reference."""

    rgb = np.asarray(rgb_channels, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[0] != 3:
        raise ValueError("linear_fit_channels expects a channels-first RGB image")

    red = rgb[0]
    green = rgb[1]
    blue = rgb[2]

    med_r, _mad_r, str_r = calc_stats(red)
    med_g, _mad_g, str_g = calc_stats(green)
    med_b, _mad_b, str_b = calc_stats(blue)

    if align_bg:
        green = green - med_g + med_r
        blue = blue - med_b + med_r

    gain_g = 1.0
    gain_b = 1.0
    if auto_gain:
        gain_g = str_r / str_g
        gain_b = str_r / str_b

    boost = float(np.clip(manual_boost, 0.01, 100.0))
    gain_g *= boost
    gain_b *= boost

    green = (green - med_r) * gain_g + med_r
    blue = (blue - med_r) * gain_b + med_r

    return np.stack(
        [
            np.clip(red, 0.0, 1.0),
            np.clip(green, 0.0, 1.0),
            np.clip(blue, 0.0, 1.0),
        ]
    ).astype(np.float32, copy=False)


def quantum_unmix_ha_oiii(norm_rgb, coef):
    """Separate Ha and OIII from dual-band OSC RGB using overlap coefficients."""

    rgb = np.asarray(norm_rgb, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[0] != 3:
        raise ValueError("quantum_unmix_ha_oiii expects a channels-first RGB image")

    red = rgb[0]
    green = rgb[1]
    blue = rgb[2]

    bg_r = float(np.median(red))
    bg_g = float(np.median(green))
    bg_b = float(np.median(blue))
    red0 = red - bg_r
    green0 = green - bg_g
    blue0 = blue - bg_b

    r2 = float(coef.get("r2", 1.0))
    r1 = float(coef.get("r1", 0.0))
    g1 = float(coef.get("g1", 1.0))
    g2 = float(coef.get("g2", 0.0))
    b1 = float(coef.get("b1", 1.0))
    b2 = float(coef.get("b2", 0.0))

    eps = 1e-8
    if abs(r2) < eps:
        return red, (green + blue) * 0.5

    cota = min(g2 / r2, 0.12)
    den_g = g1 - (g2 * r1 / r2)
    den_b = b1 - (b2 * r1 / r2)
    if abs(den_g) < eps or abs(den_b) < eps:
        return red, (green + blue) * 0.5

    oiii_g = (green0 - cota * red0) / den_g
    oiii_b = (blue0 - (b2 * red0 / r2)) / den_b

    bg_gb = max(bg_b, bg_g)
    oiii = ((2.0 * g1 * oiii_g) + (b1 * oiii_b)) / (2.0 * g1 + b1 + eps) + bg_gb
    ha = (red0 - r1 * (oiii - bg_gb)) / (r2 + eps) + (bg_r + bg_gb)

    return np.clip(ha, 0.0, 1.0), np.clip(oiii, 0.0, 1.0)


def mix_channels(norm_rgb, mix_r, mix_g, mix_b, quantum_unmix=False, sensor_profile="Generic OSC"):
    """Mix Ha/OIII contributions into output RGB channels."""

    rgb = np.asarray(norm_rgb, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[0] != 3:
        raise ValueError("mix_channels expects a channels-first RGB image")

    if quantum_unmix:
        coef = QUANTUM_COEFFS.get(sensor_profile, QUANTUM_COEFFS["Generic OSC"])
        ha, oiii = quantum_unmix_ha_oiii(rgb, coef)
    else:
        ha = rgb[0]
        oiii = (rgb[1] + rgb[2]) * 0.5

    mix_r = float(np.clip(mix_r, 0.0, 1.0))
    mix_g = float(np.clip(mix_g, 0.0, 1.0))
    mix_b = float(np.clip(mix_b, 0.0, 1.0))

    red_out = ha * (1.0 - mix_r) + oiii * mix_r
    green_out = ha * (1.0 - mix_g) + oiii * mix_g
    blue_out = ha * (1.0 - mix_b) + oiii * mix_b
    return np.stack([red_out, green_out, blue_out]).astype(np.float32, copy=False)


def mtf(values, midtones, lo, hi):
    """Siril-compatible midtones transfer function for preview helpers."""

    midtones = float(midtones)
    lo = float(lo)
    hi = float(hi)
    distance = hi - lo
    x = np.asarray(values, dtype=np.float32)
    if distance < 1e-9:
        return np.where(x > lo, 1.0, 0.0).astype(np.float32)

    xp = np.clip((x - lo) / distance, 0.0, 1.0)
    numerator = (midtones - 1.0) * xp
    denominator = (2.0 * midtones - 1.0) * xp - midtones
    with np.errstate(divide="ignore", invalid="ignore"):
        out = numerator / denominator
    return np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)


def find_linked_params_siril(rgb_channels):
    mad_norm = 1.4826
    shadows_clipping = -2.8
    target_bg = 0.25

    rgb = np.asarray(rgb_channels, dtype=np.float32)
    sum_c0 = 0.0
    sum_m = 0.0
    for channel in rgb[:3]:
        stride = max(1, channel.size // 500_000)
        sample = channel.reshape(-1)[::stride]
        median = float(np.median(sample))
        mad = float(np.median(np.abs(sample - median))) * mad_norm
        if mad == 0.0:
            mad = 0.001
        sum_c0 += median + (shadows_clipping * mad)
        sum_m += median

    c0 = max(sum_c0 / 3.0, 0.0)
    m_avg = sum_m / 3.0
    midtones = mtf(m_avg - c0, target_bg, 0.0, 1.0)
    return c0, midtones, 1.0


def apply_siril_autostretch(rgb_channels):
    """Apply linked auto-stretch for preview generation."""

    rgb = np.asarray(rgb_channels, dtype=np.float32)
    shadows, midtones, highlights = find_linked_params_siril(rgb)
    out = np.zeros_like(rgb, dtype=np.float32)
    for index in range(3):
        out[index] = mtf(rgb[index], midtones, shadows, highlights)
    return np.clip(out, 0.0, 1.0)


def _to_channels_first_rgb(image):
    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim != 3:
        raise ValueError("VeraLux Alchemy expects a 3-channel RGB image")

    if img.shape[0] == 3 and img.shape[-1] != 3:
        return img[:3], "chw", None

    if img.shape[-1] < 3:
        raise ValueError("VeraLux Alchemy expects a 3-channel RGB image")

    extras = img[..., 3:] if img.shape[-1] > 3 else None
    return np.moveaxis(img[..., :3], -1, 0), "hwc", extras


def _from_channels_first_rgb(rgb_channels, layout, extras):
    rgb = np.clip(np.asarray(rgb_channels, dtype=np.float32), 0.0, 1.0)
    if layout == "chw":
        return rgb.astype(np.float32, copy=False)

    out = np.moveaxis(rgb, 0, -1)
    if extras is not None:
        out = np.concatenate([out, np.asarray(extras, dtype=np.float32)], axis=-1)
    return out.astype(np.float32, copy=False)


def process_narrowband(
    image,
    bg_align=True,
    auto_fit=True,
    boost=1.0,
    mix_r=0.0,
    mix_g=1.0,
    mix_b=1.0,
    quantum_unmix=False,
    sensor_profile="Generic OSC",
):
    """Normalize optional Ha/OIII separation and mix into a linear RGB image."""

    rgb, layout, extras = _to_channels_first_rgb(image)
    if quantum_unmix:
        coef = QUANTUM_COEFFS.get(sensor_profile, QUANTUM_COEFFS["Generic OSC"])
        ha, oiii = quantum_unmix_ha_oiii(rgb, coef)
        base_rgb = np.stack([ha, oiii, oiii])
    else:
        base_rgb = rgb

    normalized = linear_fit_channels(
        base_rgb,
        align_bg=bool(bg_align),
        auto_gain=bool(auto_fit),
        manual_boost=float(boost),
    )
    mixed = mix_channels(
        normalized,
        float(mix_r),
        float(mix_g),
        float(mix_b),
        quantum_unmix=False,
        sensor_profile=sensor_profile,
    )
    return _from_channels_first_rgb(mixed, layout, extras)

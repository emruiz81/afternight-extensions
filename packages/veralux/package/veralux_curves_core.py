# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Curves by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Curves.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""VeraLux Curves spline-style photometric curve core."""

from __future__ import annotations

import numpy as np


UPSTREAM_VERSION = "1.0.1"
CHANNELS = ("RGB/K", "R", "G", "B", "L", "C", "S")


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
            return (img_float + 32768.0) / 65535.0
        return img_float / float(np.iinfo(input_dtype).max)

    if np.issubdtype(input_dtype, np.floating):
        if img_float.size == 0:
            return img_float
        current_max = float(np.max(img_float))
        if current_max <= 1.0 + 1e-5:
            return np.clip(img_float, 0.0, 1.0)
        if current_max <= 65535.0:
            return np.clip(img_float / 65535.0, 0.0, 1.0)
        return np.clip(img_float / 4294967295.0, 0.0, 1.0)

    return np.clip(img_float, 0.0, 1.0)


def _to_hwc_rgb(image):
    img = np.asarray(normalize_input(image), dtype=np.float32)
    if img.ndim == 2:
        return np.dstack([img, img, img]), "hw", None
    if img.ndim != 3:
        raise ValueError("VeraLux Curves expects a 2D mono or 3D RGB image")

    if img.shape[-1] >= 3:
        extras = img[..., 3:] if img.shape[-1] > 3 else None
        return img[..., :3], "hwc", extras
    if img.shape[-1] == 1:
        mono = img[..., 0]
        return np.dstack([mono, mono, mono]), "hwc_mono", None

    if img.shape[0] == 3:
        return np.moveaxis(img[:3], 0, -1), "chw", None
    if img.shape[0] == 1:
        mono = img[0]
        return np.dstack([mono, mono, mono]), "chw_mono", None

    raise ValueError("VeraLux Curves expects RGB images to have at least 3 channels")


def _from_hwc_rgb(rgb, layout, extras):
    out = np.clip(np.asarray(rgb, dtype=np.float32), 0.0, 1.0)
    if layout == "hw":
        return np.mean(out, axis=2).astype(np.float32, copy=False)
    if layout == "hwc_mono":
        return np.mean(out, axis=2, keepdims=True).astype(np.float32, copy=False)
    if layout == "chw":
        return np.moveaxis(out, -1, 0).astype(np.float32, copy=False)
    if layout == "chw_mono":
        return np.mean(out, axis=2)[np.newaxis, ...].astype(np.float32, copy=False)
    if extras is not None:
        out = np.concatenate([out, np.asarray(extras, dtype=np.float32)], axis=-1)
    return out.astype(np.float32, copy=False)


def _clean_points(points):
    source = list(points or [(0.0, 0.0), (1.0, 1.0)])
    if len(source) < 2:
        source = [(0.0, 0.0), (1.0, 1.0)]

    clipped = sorted(
        (
            float(np.clip(x, 0.0, 1.0)),
            float(y),
        )
        for x, y in source
    )
    cleaned = []
    eps = 1e-6
    for x, y in clipped:
        if cleaned and x <= cleaned[-1][0] + eps:
            x = cleaned[-1][0] + eps
        if x > 1.0:
            x = 1.0
        if cleaned and x <= cleaned[-1][0]:
            cleaned[-1] = (cleaned[-1][0], y)
            continue
        cleaned.append((x, y))

    if len(cleaned) < 2:
        return [(0.0, 0.0), (1.0, 1.0)]
    return cleaned


def _akima_derivatives(x_values, y_values):
    x = np.asarray(x_values, dtype=np.float64)
    y = np.asarray(y_values, dtype=np.float64)
    slopes = np.diff(y) / np.maximum(np.diff(x), 1e-12)
    count = len(x)

    if count == 2:
        return np.asarray([slopes[0], slopes[0]], dtype=np.float64)
    if count == 3:
        return np.asarray([slopes[0], 0.5 * (slopes[0] + slopes[1]), slopes[1]], dtype=np.float64)

    extended = np.empty(count + 3, dtype=np.float64)
    extended[2 : 2 + len(slopes)] = slopes
    extended[1] = (2.0 * extended[2]) - extended[3]
    extended[0] = (2.0 * extended[1]) - extended[2]
    extended[count + 1] = (2.0 * extended[count]) - extended[count - 1]
    extended[count + 2] = (2.0 * extended[count + 1]) - extended[count]

    derivatives = np.empty(count, dtype=np.float64)
    for index in range(count):
        weight_left = abs(extended[index + 3] - extended[index + 2])
        weight_right = abs(extended[index + 1] - extended[index])
        total = weight_left + weight_right
        if total > 1e-12:
            derivatives[index] = (
                (weight_left * extended[index + 1]) + (weight_right * extended[index + 2])
            ) / total
        else:
            derivatives[index] = 0.5 * (extended[index + 1] + extended[index + 2])
    return derivatives


def _hermite_interpolate(values, x_values, y_values):
    values = np.asarray(values, dtype=np.float64)
    x = np.asarray(x_values, dtype=np.float64)
    y = np.asarray(y_values, dtype=np.float64)
    derivatives = _akima_derivatives(x, y)

    indices = np.searchsorted(x, values, side="right") - 1
    indices = np.clip(indices, 0, len(x) - 2)
    x0 = x[indices]
    x1 = x[indices + 1]
    y0 = y[indices]
    y1 = y[indices + 1]
    d0 = derivatives[indices]
    d1 = derivatives[indices + 1]
    width = np.maximum(x1 - x0, 1e-12)
    t = (values - x0) / width
    t2 = t * t
    t3 = t2 * t

    h00 = (2.0 * t3) - (3.0 * t2) + 1.0
    h10 = t3 - (2.0 * t2) + t
    h01 = (-2.0 * t3) + (3.0 * t2)
    h11 = t3 - t2
    return (h00 * y0) + (h10 * width * d0) + (h01 * y1) + (h11 * width * d1)


def generate_lut(points, size=65536):
    """Generate a clipped high-precision LUT using a package-local Akima path."""

    cleaned = _clean_points(points)
    x, y = zip(*cleaned)
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    domain = np.linspace(0.0, 1.0, int(size), dtype=np.float64)
    lut = np.zeros_like(domain)

    min_x = float(x[0])
    max_x = float(x[-1])
    inner = (domain >= min_x) & (domain <= max_x)
    if len(cleaned) > 2:
        lut[inner] = _hermite_interpolate(domain[inner], x, y)
    else:
        lut[inner] = np.interp(domain[inner], x, y)

    if min_x > 0.0:
        lut[domain < min_x] = y[0]
    if max_x < 1.0:
        lut[domain > max_x] = y[-1]

    return np.clip(lut, 0.0, 1.0).astype(np.float32)


def curve_from_controls(
    *,
    black_point=0.0,
    shadow_lift=0.0,
    midtone_input=0.5,
    midtone_output=0.5,
    highlight_compression=0.0,
    white_point=1.0,
):
    """Build the first native Curves control-point set from numeric controls."""

    black = float(np.clip(black_point, 0.0, 0.98))
    white = float(np.clip(white_point, black + 0.01, 1.0))
    mid_x = float(np.clip(midtone_input, black + 0.005, white - 0.005))
    return [
        (black, float(np.clip(shadow_lift, 0.0, 1.0))),
        (mid_x, float(np.clip(midtone_output, 0.0, 1.0))),
        (white, float(np.clip(1.0 - float(highlight_compression), 0.0, 1.0))),
    ]


def curve_operation(
    domain,
    *,
    points=None,
    lum_range_enabled=False,
    lum_min=0.0,
    lum_max=1.0,
    feather=0.25,
):
    return {
        "domain": normalize_domain(domain),
        "points": list(points or [(0.0, 0.0), (1.0, 1.0)]),
        "lum_range_enabled": bool(lum_range_enabled),
        "lum_min": float(np.clip(lum_min, 0.0, 1.0)),
        "lum_max": float(np.clip(lum_max, 0.0, 1.0)),
        "feather": float(np.clip(feather, 0.0, 1.0)),
    }


def normalize_domain(domain):
    normalized = str(domain or "RGB/K").strip().upper()
    aliases = {
        "RGB": "RGB/K",
        "K": "RGB/K",
        "RGBK": "RGB/K",
        "LUMINANCE": "L",
        "CHROMINANCE": "C",
        "SATURATION": "S",
        "RED": "R",
        "GREEN": "G",
        "BLUE": "B",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in CHANNELS:
        return "RGB/K"
    return normalized


def compute_luminance_mask(rgb, lum_min, lum_max, feather=0.25):
    """Compute the upstream-style soft luminance range mask without SciPy."""

    image = np.asarray(rgb, dtype=np.float32)
    luminance = np.mean(image, axis=2)
    lo = float(np.clip(lum_min, 0.0, 1.0))
    hi = float(np.clip(lum_max, 0.0, 1.0))
    if hi < lo:
        lo, hi = hi, lo

    feather_width = float(np.clip(feather, 0.0, 1.0))
    if feather_width < 1e-6:
        return ((luminance >= lo) & (luminance <= hi)).astype(np.float32)

    mask = np.ones_like(luminance, dtype=np.float32)
    k_smooth = 2.5
    if lo > 0.0:
        lower = 1.0 / (1.0 + np.exp(-k_smooth * ((luminance - lo) / feather_width)))
        mask = np.minimum(mask, lower)
    if hi < 1.0:
        upper = 1.0 / (1.0 + np.exp(-k_smooth * ((hi - luminance) / feather_width)))
        mask = np.minimum(mask, upper)
    return np.clip(mask, 0.0, 1.0).astype(np.float32)


def _apply_lut(values, lut):
    table = np.asarray(lut, dtype=np.float32)
    if table.size < 2:
        return np.zeros_like(values, dtype=np.float32)

    clipped = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    scaled = clipped * float(table.size - 1)
    lower = np.floor(scaled).astype(np.int32)
    lower = np.minimum(lower, table.size - 2)
    fraction = (scaled - lower).astype(np.float32, copy=False)
    return (table[lower] * (1.0 - fraction)) + (table[lower + 1] * fraction)


def _apply_lut_with_mask(values, lut, mask):
    transformed = _apply_lut(values, lut).astype(np.float32, copy=False)
    if mask is None:
        return transformed
    if values.ndim == 3:
        blend = mask[..., np.newaxis]
    else:
        blend = mask
    return (values * (1.0 - blend) + transformed * blend).astype(np.float32, copy=False)


def rgb_to_lab(rgb):
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


def rgb_to_hsv(rgb):
    image = np.clip(np.asarray(rgb, dtype=np.float32), 0.0, 1.0)
    r = image[..., 0]
    g = image[..., 1]
    b = image[..., 2]
    maxc = np.max(image, axis=-1)
    minc = np.min(image, axis=-1)
    delta = maxc - minc
    saturation = np.where(maxc > 1e-12, delta / np.maximum(maxc, 1e-12), 0.0)

    hue = np.zeros_like(maxc, dtype=np.float32)
    nonzero = delta > 1e-12
    hue = np.where((maxc == r) & nonzero, ((g - b) / np.maximum(delta, 1e-12)) % 6.0, hue)
    hue = np.where((maxc == g) & nonzero, ((b - r) / np.maximum(delta, 1e-12)) + 2.0, hue)
    hue = np.where((maxc == b) & nonzero, ((r - g) / np.maximum(delta, 1e-12)) + 4.0, hue)
    hue = (hue / 6.0) % 1.0
    return np.stack([hue, saturation, maxc], axis=-1).astype(np.float32, copy=False)


def hsv_to_rgb(hsv):
    values = np.asarray(hsv, dtype=np.float32)
    h = (values[..., 0] % 1.0) * 6.0
    s = np.clip(values[..., 1], 0.0, 1.0)
    v = np.clip(values[..., 2], 0.0, 1.0)
    i = np.floor(h).astype(np.int32)
    f = h - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))

    i_mod = i % 6
    r = np.choose(i_mod, [v, q, p, p, t, v])
    g = np.choose(i_mod, [t, v, v, q, p, p])
    b = np.choose(i_mod, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1).astype(np.float32, copy=False)


def _operation_mask(rgb, operation):
    if not bool(operation.get("lum_range_enabled", False)):
        return None
    return compute_luminance_mask(
        rgb,
        operation.get("lum_min", 0.0),
        operation.get("lum_max", 1.0),
        operation.get("feather", operation.get("feather_sigma", 0.25)),
    )


def apply_operation(rgb, operation, lut_size=65536):
    """Apply one Curves operation to an HWC RGB float image."""

    domain = normalize_domain(operation.get("domain", "RGB/K"))
    lut = generate_lut(operation.get("points"), size=lut_size)
    result = np.clip(np.asarray(rgb, dtype=np.float32), 0.0, 1.0).copy()
    mask = _operation_mask(result, operation)

    if domain == "RGB/K":
        return np.clip(_apply_lut_with_mask(result, lut, mask), 0.0, 1.0)
    if domain in ("R", "G", "B"):
        index = {"R": 0, "G": 1, "B": 2}[domain]
        result[..., index] = _apply_lut_with_mask(result[..., index], lut, mask)
        return np.clip(result, 0.0, 1.0)
    if domain == "L":
        lab = rgb_to_lab(result)
        lightness = np.clip(lab[..., 0] / 100.0, 0.0, 1.0)
        lab[..., 0] = np.clip(_apply_lut_with_mask(lightness, lut, mask), 0.0, 1.0) * 100.0
        return lab_to_rgb(lab)
    if domain == "S":
        hsv = rgb_to_hsv(result)
        hsv[..., 1] = np.clip(_apply_lut_with_mask(hsv[..., 1], lut, mask), 0.0, 1.0)
        return hsv_to_rgb(hsv)
    if domain == "C":
        lab = rgb_to_lab(result)
        a = lab[..., 1]
        b = lab[..., 2]
        chroma = np.sqrt(a**2 + b**2)
        chroma_norm = np.clip(chroma / 128.0, 0.0, 1.0)
        chroma_new = _apply_lut_with_mask(chroma_norm, lut, mask) * 128.0
        with np.errstate(divide="ignore", invalid="ignore"):
            multiplier = chroma_new / chroma
        multiplier = np.where(chroma > 1e-12, multiplier, 1.0)
        lab[..., 1] = a * multiplier
        lab[..., 2] = b * multiplier
        return lab_to_rgb(lab)
    return result


def process_curves(image, operations, *, lut_size=65536):
    """Apply a stage list of VeraLux Curves operations and preserve source layout."""

    rgb, layout, extras = _to_hwc_rgb(image)
    result = np.asarray(rgb, dtype=np.float32)
    for operation in list(operations or []):
        result = apply_operation(result, operation, lut_size=lut_size)
    return _from_hwc_rgb(result, layout, extras)

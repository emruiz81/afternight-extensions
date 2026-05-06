# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Nox) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Nox.py
# Upstream baseline: a9fb2c7f505c488f5cfef5b7fa5022097551e06e; local port notes: see UPSTREAM.md.

"""VeraLux Nox gradient-reduction core.

The primary path below follows the original Nox 1.0.1 "Zenith" membrane
implementation: dual-scale variance protection, PSF vetoing, sparse
second-derivative regularization, iterative positive-residual rejection, cubic
model reconstruction, and linked smart-pedestal correction. A small NumPy-only
fallback keeps repository tests runnable when the optional runtime wheels have
not been installed in the developer shell.
"""

from __future__ import annotations

import math

import numpy as np

_cv2 = None
_cv2_import_attempted = False
_sparse = None
_scipy_cg = None
_scipy_expit = None
_scipy_import_attempted = False
_scipy_spsolve = None
_scipy_uniform_filter = None


UPSTREAM_VERSION = "1.0.1"
ORIGINAL_MAX_GRID = 50
ORIGINAL_TARGET_FLOOR = 0.001


def _load_cv2():
    """Return cv2 when available, importing it only once on first algorithm use."""

    global _cv2, _cv2_import_attempted
    if not _cv2_import_attempted:
        _cv2_import_attempted = True
        try:  # pragma: no cover - exercised in the packaged runtime.
            import cv2

            _cv2 = cv2
        except Exception:  # pragma: no cover - local test environments may omit OpenCV.
            _cv2 = None
    return _cv2


def _load_scipy():
    """Return True when SciPy solver helpers are available, importing lazily."""

    global _sparse, _scipy_cg, _scipy_expit, _scipy_import_attempted
    global _scipy_spsolve, _scipy_uniform_filter
    if not _scipy_import_attempted:
        _scipy_import_attempted = True
        try:  # pragma: no cover - exercised in the packaged runtime.
            from scipy import sparse
            from scipy.ndimage import uniform_filter
            from scipy.sparse.linalg import cg, spsolve
            from scipy.special import expit

            _sparse = sparse
            _scipy_cg = cg
            _scipy_expit = expit
            _scipy_spsolve = spsolve
            _scipy_uniform_filter = uniform_filter
        except Exception:  # pragma: no cover - local test environments may omit SciPy.
            _sparse = None
            _scipy_cg = None
            _scipy_expit = None
            _scipy_spsolve = None
            _scipy_uniform_filter = None
    return (
        _sparse is not None
        and _scipy_cg is not None
        and _scipy_spsolve is not None
        and _scipy_uniform_filter is not None
        and _scipy_expit is not None
    )


def _exact_solver_available():
    _load_cv2()
    _load_scipy()
    return (
        _cv2 is not None
        and _sparse is not None
        and _scipy_cg is not None
        and _scipy_spsolve is not None
        and _scipy_uniform_filter is not None
        and _scipy_expit is not None
    )


def normalize_input(image):
    """Normalize common integer/float image arrays using VeraLux Nox rules."""

    img_data = np.asarray(image)
    safe = np.nan_to_num(img_data, nan=0.0, posinf=1.0, neginf=0.0)
    if np.issubdtype(safe.dtype, np.integer):
        info = np.iinfo(safe.dtype)
        return safe.astype(np.float32) / float(info.max)

    img = safe.astype(np.float32, copy=False)
    if img.size == 0 or not np.isfinite(img).any():
        return img

    vmax = float(np.nanmax(img))
    if vmax <= 2.0:
        return img
    if vmax <= 10.0:
        sub = img[::8, ::8, :] if img.ndim == 3 else img[::8, ::8]
        hi = float(np.nanpercentile(sub, 99.99))
        if hi <= 2.0:
            return img
    if vmax <= 255.0:
        return img / 255.0
    return img / 65535.0


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


def _from_work_image(data, layout, extras=None, *, clip=True):
    out = np.asarray(data, dtype=np.float32)
    if clip:
        out = np.clip(out, 0.0, 1.0)
    if layout == "hw":
        return out.astype(np.float32, copy=False)
    if layout == "hwc_mono":
        return out[..., np.newaxis].astype(np.float32, copy=False)
    if layout == "chw_mono":
        return out[np.newaxis, ...].astype(np.float32, copy=False)
    if layout == "chw":
        return np.moveaxis(out, -1, 0).astype(np.float32, copy=False)
    if extras is not None:
        extras_data = np.asarray(extras, dtype=np.float32)
        if clip:
            extras_data = np.clip(extras_data, 0.0, 1.0)
        out = np.concatenate([out, extras_data], axis=-1)
    return out.astype(np.float32, copy=False)


def _resize_bilinear(image, out_h, out_w):
    values = np.asarray(image, dtype=np.float32)
    if values.ndim != 2:
        raise ValueError("VeraLux Nox resize expects a 2D plane")
    h, w = values.shape
    out_h = int(max(1, out_h))
    out_w = int(max(1, out_w))
    if h == out_h and w == out_w:
        return values.copy()
    ys = np.zeros((out_h,), dtype=np.float32) if h == 1 else np.linspace(0.0, h - 1, out_h, dtype=np.float32)
    xs = np.zeros((out_w,), dtype=np.float32) if w == 1 else np.linspace(0.0, w - 1, out_w, dtype=np.float32)

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


def _resize_nearest(image, out_h, out_w):
    values = np.asarray(image)
    h, w = values.shape[:2]
    out_h = int(max(1, out_h))
    out_w = int(max(1, out_w))
    ys = np.clip(np.rint(np.linspace(0, h - 1, out_h)).astype(np.int32), 0, h - 1)
    xs = np.clip(np.rint(np.linspace(0, w - 1, out_w)).astype(np.int32), 0, w - 1)
    return values[ys[:, np.newaxis], xs[np.newaxis, ...]]


def _resize(image, size, interpolation="linear"):
    out_w, out_h = int(size[0]), int(size[1])
    values = np.asarray(image)
    cv2 = _load_cv2()
    if cv2 is not None:
        flag = {
            "area": cv2.INTER_AREA,
            "cubic": cv2.INTER_CUBIC,
            "nearest": cv2.INTER_NEAREST,
            "linear": cv2.INTER_LINEAR,
        }.get(interpolation, cv2.INTER_LINEAR)
        return cv2.resize(values, (out_w, out_h), interpolation=flag)

    if interpolation == "nearest":
        return _resize_nearest(values, out_h, out_w).astype(values.dtype, copy=False)
    if values.ndim == 2:
        return _resize_bilinear(values, out_h, out_w)
    channels = [_resize_bilinear(values[..., index], out_h, out_w) for index in range(values.shape[-1])]
    return np.stack(channels, axis=-1).astype(np.float32, copy=False)


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


def _uniform_filter(image, size):
    _load_scipy()
    if _scipy_uniform_filter is not None:
        return _scipy_uniform_filter(image, size, mode="reflect")
    radius = max(0, int(size) // 2)
    return _box_blur_reflect(image, radius)


def _expit(values):
    _load_scipy()
    if _scipy_expit is not None:
        return _scipy_expit(values)
    clipped = np.clip(values, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _ellipse_kernel(size):
    if isinstance(size, tuple):
        h, w = int(size[1]), int(size[0])
    else:
        h = w = int(size)
    h = max(1, h)
    w = max(1, w)
    cv2 = _load_cv2()
    if cv2 is not None:
        return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (w, h))
    y, x = np.ogrid[:h, :w]
    cy = (h - 1) / 2.0
    cx = (w - 1) / 2.0
    ry = max(cy, 0.5)
    rx = max(cx, 0.5)
    return (((y - cy) / ry) ** 2 + ((x - cx) / rx) ** 2 <= 1.0).astype(np.uint8)


def _morph(values, kernel, op):
    data = np.asarray(values)
    cv2 = _load_cv2()
    if cv2 is not None:
        if op == "erode":
            return cv2.erode(data, kernel, iterations=1)
        return cv2.dilate(data, kernel, iterations=1)

    mask = np.asarray(kernel).astype(bool)
    pad_y = mask.shape[0] // 2
    pad_x = mask.shape[1] // 2
    padded = np.pad(data, ((pad_y, pad_y), (pad_x, pad_x)), mode="edge")
    parts = []
    for ky in range(mask.shape[0]):
        for kx in range(mask.shape[1]):
            if mask[ky, kx]:
                parts.append(padded[ky : ky + data.shape[0], kx : kx + data.shape[1]])
    stack = np.stack(parts, axis=0)
    if op == "erode":
        return np.min(stack, axis=0).astype(data.dtype, copy=False)
    return np.max(stack, axis=0).astype(data.dtype, copy=False)


def _copy_make_border_replicate(values, pad_y, pad_x):
    cv2 = _load_cv2()
    if cv2 is not None:
        return cv2.copyMakeBorder(values, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_REPLICATE)
    return np.pad(values, ((pad_y, pad_y), (pad_x, pad_x)), mode="edge")


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


def mtf(x, m, lo, hi):
    m = float(m)
    lo = float(lo)
    hi = float(hi)
    dist = hi - lo
    if dist < 1e-9:
        return np.zeros_like(x)
    xp = np.clip((x - lo) / dist, 0.0, 1.0)
    num = (m - 1.0) * xp
    den = (2.0 * m - 1.0) * xp - m
    return num / (den + 1e-9)


def apply_autostretch(image):
    """Apply the upstream Nox display autostretch used by the PyQt preview."""

    img = np.asarray(normalize_input(image), dtype=np.float32)
    mad_norm = 1.4826
    shadows_clipping = -2.8
    target_bg = 0.25

    def stretch_channel(channel):
        stride = max(1, channel.size // 100000)
        sample = channel.ravel()[::stride]
        median = float(np.median(sample))
        mad = float(np.median(np.abs(sample - median))) * mad_norm
        if mad == 0.0:
            mad = 1e-5
        c0 = max(0.0, median + shadows_clipping * mad)
        m2 = median - c0
        midtones = mtf(np.array([m2], dtype=np.float32), target_bg, 0.0, 1.0)[0]
        return mtf(channel, midtones, c0, 1.0)

    if img.ndim == 2:
        return stretch_channel(img)

    channels = [img[..., 0], img[..., 1], img[..., 2]]
    sum_c0 = 0.0
    sum_m = 0.0
    for channel in channels:
        stride = max(1, channel.size // 100000)
        sample = channel.ravel()[::stride]
        median = float(np.median(sample))
        mad = float(np.median(np.abs(sample - median))) * mad_norm
        if mad == 0.0:
            mad = 1e-5
        sum_c0 += median + shadows_clipping * mad
        sum_m += median
    c0 = max(0.0, sum_c0 / len(channels))
    m2 = (sum_m / len(channels)) - c0
    midtones = mtf(np.array([m2], dtype=np.float32), target_bg, 0.0, 1.0)[0]
    return mtf(img, midtones, c0, 1.0)


def construct_difference_matrix_1d(n, order=2):
    _load_scipy()
    if _sparse is None:
        return None
    if order == 1:
        e = np.ones(n)
        return _sparse.spdiags([-e, e], [0, 1], n - 1, n)
    if order == 2:
        e = np.ones(n)
        return _sparse.spdiags([e, -2 * e, e], [0, 1, 2], n - 2, n)
    return None


def construct_regularizer_kron(h, w):
    _load_scipy()
    if _sparse is None:
        return None
    i_h = _sparse.eye(h)
    i_w = _sparse.eye(w)
    d_h = construct_difference_matrix_1d(h, order=2)
    d_w = construct_difference_matrix_1d(w, order=2)
    dtd_h = d_h.T @ d_h
    dtd_w = d_w.T @ d_w
    p_y = _sparse.kron(dtd_h, i_w)
    p_x = _sparse.kron(i_h, dtd_w)
    return p_x + p_y


def compute_pyramid_variance(img_channel, grid_h, grid_w, fwhm_avg):
    """Return the upstream dual-resolution sky-weight map on the solver grid."""

    values = np.asarray(img_channel, dtype=np.float32)
    h, w = values.shape
    scale_proxy = min(1.0, 1024.0 / max(h, w))
    h_p = max(1, int(h * scale_proxy))
    w_p = max(1, int(w * scale_proxy))
    img_proxy = _resize(values, (w_p, h_p), "area")
    fwhm_proxy = max(float(fwhm_avg) * scale_proxy, 1.0)

    scales = [
        max(3, int(fwhm_proxy * 0.5)) | 1,
        max(3, int(fwhm_proxy * 2.0)) | 1,
        max(9, int(fwhm_proxy * 8.0)) | 1,
        max(15, int(fwhm_proxy * 20.0)) | 1,
    ]
    maps = []
    for win_size in scales:
        mean = _uniform_filter(img_proxy, win_size)
        mean_sq = _uniform_filter(img_proxy**2, win_size)
        variance = mean_sq - mean**2
        variance[variance < 0.0] = 0.0
        std_dev = np.sqrt(variance)
        v_med = float(np.median(std_dev))
        v_mad = float(np.median(np.abs(std_dev - v_med)))
        threshold = v_med + (3.0 * 1.4826 * v_mad) + (1.5 * 1.4826 * v_mad)
        if threshold < 1e-7:
            threshold = 1e-7
        arg = 10.0 * (std_dev - threshold) / threshold
        arg = np.nan_to_num(arg, nan=50.0, posinf=50.0, neginf=-50.0)
        maps.append(_expit(-arg))

    combined_micro = (0.50 * maps[3]) + (0.30 * maps[2]) + (0.15 * maps[1]) + (0.05 * maps[0])

    img_macro1 = _resize(values, (128, 128), "area")
    m1_mean = _uniform_filter(img_macro1, 3)
    m1_sq = _uniform_filter(img_macro1**2, 3)
    m1_var = m1_sq - m1_mean**2
    m1_var[m1_var < 0.0] = 0.0
    m1_std = np.sqrt(m1_var)
    m1_med = float(np.median(m1_std))
    m1_mad = float(np.median(np.abs(m1_std - m1_med)))
    m1_thresh = max(m1_med + (1.0 * 1.4826 * m1_mad), 1e-9)
    m1_arg = 9.0 * (m1_std - m1_thresh) / m1_thresh
    m1_arg = np.nan_to_num(m1_arg, nan=50.0, posinf=50.0, neginf=-50.0)
    weights_macro1 = _expit(-m1_arg)
    weights_macro1 = _morph(weights_macro1, _ellipse_kernel((5, 5)), "erode")

    img_macro2 = _resize(values, (64, 64), "area")
    m2_mean = _uniform_filter(img_macro2, 3)
    m2_sq = _uniform_filter(img_macro2**2, 3)
    m2_var = m2_sq - m2_mean**2
    m2_var[m2_var < 0.0] = 0.0
    m2_std = np.sqrt(m2_var)
    m2_med = float(np.median(m2_std))
    m2_mad = float(np.median(np.abs(m2_std - m2_med)))
    m2_thresh = max(m2_med + (0.70 * 1.4826 * m2_mad), 1e-9)
    m2_arg = 9.0 * (m2_std - m2_thresh) / m2_thresh
    m2_arg = np.nan_to_num(m2_arg, nan=50.0, posinf=50.0, neginf=-50.0)
    weights_macro2 = _expit(-m2_arg)
    weights_macro2 = _morph(weights_macro2, _ellipse_kernel((7, 7)), "erode")

    w_macro1_up = _resize(weights_macro1, (w_p, h_p), "linear")
    w_macro2_up = _resize(weights_macro2, (w_p, h_p), "linear")
    w_map_macro_proxy = np.maximum(w_macro1_up, w_macro2_up)
    final_combined = combined_micro * w_map_macro_proxy
    w_map_grid = _resize(final_combined, (grid_w, grid_h), "area")
    return np.asarray(w_map_grid, dtype=np.float32)


def calculate_heuristics(image, star_mask=None, fwhm_val=3.0):
    """Return the original Nox Scientific Auto-Tune stiffness/aggression pair."""

    work, _layout, _extras = _to_work_image(image)
    h, w = work.shape[:2]
    img = np.max(work, axis=2) if work.ndim == 3 else work
    scale = min(1.0, 2048.0 / max(h, w))
    proxy = _resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), "area")

    if star_mask is not None:
        mask = _coerce_mask_plane(star_mask, img.shape)
        mask_proxy = _resize(mask, (proxy.shape[1], proxy.shape[0]), "nearest")
    else:
        med = float(np.median(proxy))
        mad = float(np.median(np.abs(proxy - med)))
        thresh = med + 3.0 * (1.4826 * mad)
        mask_proxy = (proxy > thresh).astype(np.float32)

    feature_density = float(np.mean(mask_proxy > 0.1))
    aggr = 30.0 + (feature_density / 0.25) * 40.0
    aggr = float(np.clip(aggr, 25.0, 72.0))

    bg_pixels = proxy[mask_proxy <= 0.1]
    if len(bg_pixels) > 100:
        bg_med = float(np.median(bg_pixels))
        bg_mad = float(np.median(np.abs(bg_pixels - bg_med)))
        bg_std = float(np.std(bg_pixels))
        noise_sigma = 1.4826 * bg_mad
        if noise_sigma < 1e-9:
            noise_sigma = 1e-9
        bvi = bg_std / noise_sigma
        stiff = 1.0 + (bvi - 1.0) * 1.5
    else:
        stiff = 2.0

    if fwhm_val > 4.0:
        stiff += (float(fwhm_val) - 4.0) * 0.15
    stiff = float(np.clip(stiff, 1.0, 4.0))
    return stiff, aggr


def _membrane_solve_channel_fallback(img_2d, mask_2d, precomputed_variance, stiffness_val, aggr_percent, max_grid):
    h_orig, w_orig = img_2d.shape
    scale = min(1.0, float(max_grid) / max(h_orig, w_orig))
    h_grid = max(5, int(h_orig * scale))
    w_grid = max(5, int(w_orig * scale))
    y_grid = _resize(img_2d, (w_grid, h_grid), "area").astype(np.float32)
    v_grid = np.clip(np.asarray(precomputed_variance, dtype=np.float32), 0.0, 1.0)
    if v_grid.shape != y_grid.shape:
        v_grid = _resize(v_grid, (w_grid, h_grid), "area")

    if mask_2d is not None:
        m_small = _resize(mask_2d.astype(np.float32), (w_grid, h_grid), "area")
        m_bin = m_small > 0.999
        sky = _morph(m_bin.astype(np.uint8), _ellipse_kernel((3, 3)), "erode").astype(bool)
    else:
        sky = np.ones((h_grid, w_grid), dtype=bool)

    weights = np.clip(v_grid * sky.astype(np.float32), 0.0, 1.0)
    sample = y_grid[weights > 0.15]
    if sample.size < 16:
        sample = y_grid.reshape(-1)
    model = y_grid * weights + float(np.median(sample)) * (1.0 - weights)

    stiffness = float(np.clip(stiffness_val, 1.0, 4.0))
    lam = 0.65 + stiffness * 1.65
    p_base = 10 ** (-3.0 - (float(aggr_percent) / 40.0))
    for i in range(80 + int(stiffness * 22)):
        up = np.vstack([model[:1, :], model[:-1, :]])
        down = np.vstack([model[1:, :], model[-1:, :]])
        left = np.hstack([model[:, :1], model[:, :-1]])
        right = np.hstack([model[:, 1:], model[:, -1:]])
        neighbors = (up + down + left + right) * 0.25
        residual = y_grid - model
        reject = np.ones_like(weights)
        reject[residual > 0.0] = p_base / (10.0 ** min(i // 16, 4))
        dyn_weights = weights * reject
        model = (dyn_weights * y_grid + lam * neighbors) / (dyn_weights + lam + 1e-6)

    return _resize(model, (w_orig, h_orig), "cubic").astype(np.float32, copy=False)


def membrane_solve_channel(img_2d, mask_2d, precomputed_variance, stiffness_val, aggr_percent, max_grid=96):
    """Original Nox membrane solver for one image channel."""

    img_2d = np.asarray(img_2d, dtype=np.float32)
    h_orig, w_orig = img_2d.shape
    scale = min(1.0, float(max_grid) / max(h_orig, w_orig))
    h_grid = int(h_orig * scale)
    w_grid = int(w_orig * scale)
    if h_grid < 5 or w_grid < 5:
        kernel = (max(1, h_orig // 2), max(1, w_orig // 2))
        cv2 = _load_cv2()
        if cv2 is not None:
            return cv2.blur(img_2d, kernel)
        return _box_blur_reflect(img_2d, max(kernel) // 2)

    if not _exact_solver_available():
        return _membrane_solve_channel_fallback(
            img_2d,
            mask_2d,
            precomputed_variance,
            stiffness_val,
            aggr_percent,
            max_grid,
        )

    y_raw = _resize(img_2d, (w_grid, h_grid), "area").astype(np.float32)
    if mask_2d is not None:
        m_small = _resize(mask_2d.astype(np.float32), (w_grid, h_grid), "area")
        m_bin = m_small > 0.999
        kernel = _ellipse_kernel((3, 3))
        m_raw = _morph(m_bin.astype(np.uint8), kernel, "erode").astype(bool)
    else:
        m_raw = np.ones((h_grid, w_grid), dtype=bool)

    pad_y = int(h_grid * 0.10)
    pad_x = int(w_grid * 0.10)
    y_pad = _copy_make_border_replicate(y_raw, pad_y, pad_x)
    m_pad_u8 = _copy_make_border_replicate(m_raw.astype(np.uint8), pad_y, pad_x)
    v_pad = _copy_make_border_replicate(precomputed_variance, pad_y, pad_x)
    m_pad = m_pad_u8.astype(bool)

    h_p, w_p = y_pad.shape
    n_p = h_p * w_p
    y_flat = y_pad.flatten()
    v_flat = v_pad.flatten().astype(np.float32)
    lam = 10 ** ((float(stiffness_val) - 1.0) * 1.66 + 0.7)
    dtd = construct_regularizer_kron(h_p, w_p)

    w_flat = v_flat * m_pad.flatten().astype(np.float32)
    z_flat = np.zeros_like(y_flat)
    p_base = 10 ** (-3.0 - (float(aggr_percent) / 40.0))
    max_outer_loops = 10
    epsilon = 1e-6

    for i in range(max_outer_loops):
        w_lhs = _sparse.spdiags(w_flat + epsilon, 0, n_p, n_p)
        a_mat = w_lhs + lam * dtd
        b_vec = w_flat * y_flat
        z_prev = z_flat.copy()
        use_fallback = False
        try:
            z_flat, info = _scipy_cg(a_mat, b_vec, x0=z_flat, rtol=1e-7, maxiter=500)
            if info > 0:
                use_fallback = True
        except Exception:
            use_fallback = True
        if use_fallback:
            z_flat = _scipy_spsolve(a_mat.tocsc(), b_vec)

        diff = float(np.mean(np.abs(z_flat - z_prev)))
        res = y_flat - z_flat
        mask_user = m_pad.flatten()
        new_w_dyn = np.ones_like(w_flat)
        is_above = res > 0.0
        eff_i = min(i, 4)
        p_curr = p_base / (10.0 ** eff_i)
        new_w_dyn[is_above] = p_curr
        new_w_dyn[~is_above] = 1.0
        w_flat = new_w_dyn * v_flat * mask_user.astype(np.float32)

        if i > 2 and diff < 1e-4:
            break

    z_pad_2d = z_flat.reshape((h_p, w_p))
    z_crop = z_pad_2d[pad_y : pad_y + h_grid, pad_x : pad_x + w_grid]
    z_final = _resize(z_crop, (w_orig, h_orig), "cubic")
    return np.asarray(z_final, dtype=np.float32)


def _coerce_mask_plane(mask, shape):
    if mask is None:
        return None
    values = np.asarray(mask, dtype=np.float32)
    if values.ndim == 3:
        if values.shape[0] in (1, 3) and values.shape[1:] == tuple(shape):
            values = values[0] if values.shape[0] == 1 else np.max(values[:3], axis=0)
        elif values.shape[-1] == 1:
            values = values[..., 0]
        else:
            values = np.max(values[..., :3], axis=-1)
    values = np.squeeze(values)
    if values.shape != tuple(shape):
        values = _resize(values, (shape[1], shape[0]), "linear")
    return np.clip(values, 0.0, 1.0).astype(np.float32, copy=False)


def _protection_to_sky_mask(mask, shape, *, user_mask_is_sky=False):
    values = _coerce_mask_plane(mask, shape)
    if values is None:
        return None
    if user_mask_is_sky:
        return values > 0.5
    sky = values <= 0.5
    # The original Nox GUI applies a one-pixel "micro seal" to painted
    # protection masks before the Zenith membrane solver receives them.
    kernel = np.ones((3, 3), dtype=np.uint8)
    return _morph(sky.astype(np.uint8), kernel, "erode").astype(bool, copy=False)


def _process_work_image(
    work,
    *,
    stiffness,
    rejection_power,
    auto_mask,
    user_mask=None,
    star_mask=None,
    fwhm_val=4.0,
    user_mask_is_sky=False,
):
    h, w = work.shape[:2]
    num_channels = work.shape[2] if work.ndim == 3 else 1
    max_grid = ORIGINAL_MAX_GRID
    scale = min(1.0, float(max_grid) / max(h, w))
    h_grid = max(5, int(h * scale))
    w_grid = max(5, int(w * scale))

    img_master = np.max(work, axis=2) if num_channels == 3 else work
    master_v_map = compute_pyramid_variance(img_master, h_grid, w_grid, fwhm_val)

    if auto_mask and star_mask is not None:
        star_plane = _coerce_mask_plane(star_mask, (h, w))
        sm_small = _resize(star_plane, (w_grid, h_grid), "area")
        sm_bin = sm_small > 0.01
        kernel = _ellipse_kernel((3, 3))
        sm_dilated = _morph(sm_bin.astype(np.uint8), kernel, "dilate")
        veto_map = 1.0 - sm_dilated.astype(np.float32)
        master_v_map *= veto_map

    if not auto_mask:
        master_v_map = np.ones_like(master_v_map, dtype=np.float32)

    sky_mask = _protection_to_sky_mask(user_mask, (h, w), user_mask_is_sky=user_mask_is_sky)
    if sky_mask is None:
        sky_mask = np.ones((h, w), dtype=bool)

    stiffness = float(np.clip(stiffness, 1.0, 4.0))
    aggr = float(np.clip(rejection_power, 0.0, 100.0))

    model_out = np.zeros_like(work, dtype=np.float32)
    if num_channels == 1:
        model_out = membrane_solve_channel(work, sky_mask, master_v_map, stiffness, aggr, max_grid)
    else:
        for channel_index in range(3):
            model_out[..., channel_index] = membrane_solve_channel(
                work[..., channel_index],
                sky_mask,
                master_v_map,
                stiffness,
                aggr,
                max_grid,
            )

    corrected = work - model_out
    if num_channels == 3:
        floors = []
        for channel_index in range(3):
            sample = corrected[::5, ::5, channel_index]
            floors.append(float(np.percentile(sample, 0.1)))
        min_floor = min(floors)
        if min_floor < ORIGINAL_TARGET_FLOOR:
            corrected += ORIGINAL_TARGET_FLOOR - min_floor
    else:
        sample = corrected[::5, ::5]
        floor_val = float(np.percentile(sample, 0.1))
        if floor_val < ORIGINAL_TARGET_FLOOR:
            corrected += ORIGINAL_TARGET_FLOOR - floor_val

    return np.clip(corrected, 0.0, 1.0).astype(np.float32, copy=False), model_out.astype(
        np.float32,
        copy=False,
    )


def estimate_background_model(
    image,
    *,
    auto_mask=True,
    stiffness=2.0,
    model_grid=None,
    user_mask=None,
    rejection_power=50.0,
    star_mask=None,
    fwhm_val=4.0,
):
    """Estimate the upstream Nox background model for one channel."""

    del model_grid
    values = np.asarray(normalize_input(image), dtype=np.float32)
    if values.ndim != 2:
        raise ValueError("VeraLux Nox background estimation expects a 2D channel")
    corrected, model = _process_work_image(
        values,
        stiffness=stiffness,
        rejection_power=rejection_power,
        auto_mask=auto_mask,
        user_mask=user_mask,
        star_mask=star_mask,
        fwhm_val=fwhm_val,
    )
    del corrected
    return model.astype(np.float32, copy=False)


def compute_signal_mask(channel):
    """Return a 0..1 protected-signal estimate derived from the Nox variance map."""

    values = np.asarray(normalize_input(channel), dtype=np.float32)
    if values.ndim != 2:
        values = luminance(values)
    h, w = values.shape
    scale = min(1.0, float(ORIGINAL_MAX_GRID) / max(h, w))
    h_grid = max(5, int(h * scale))
    w_grid = max(5, int(w * scale))
    sky_weights = compute_pyramid_variance(values, h_grid, w_grid, 4.0)
    sky_full = _resize(sky_weights, (w, h), "linear")
    return np.clip(1.0 - sky_full, 0.0, 1.0).astype(np.float32, copy=False)


def process_gradient_reduction(
    image,
    *,
    stiffness=2.0,
    rejection_power=50.0,
    correction_strength=1.0,
    model_grid=None,
    auto_mask=True,
    user_mask=None,
    star_mask=None,
    fwhm_val=4.0,
    return_model=False,
    user_mask_is_sky=False,
):
    """Apply the VeraLux Nox 1.0.1 Zenith membrane correction."""

    del model_grid
    work, layout, extras = _to_work_image(image)
    corrected, model = _process_work_image(
        work,
        stiffness=stiffness,
        rejection_power=rejection_power,
        auto_mask=auto_mask,
        user_mask=user_mask,
        star_mask=star_mask,
        fwhm_val=fwhm_val,
        user_mask_is_sky=user_mask_is_sky,
    )

    strength = float(correction_strength)
    if abs(strength - 1.0) > 1e-6:
        strength = float(np.clip(strength, 0.0, 1.25))
        corrected = np.clip((work * (1.0 - strength)) + (corrected * strength), 0.0, 1.0)

    corrected_out = _from_work_image(corrected, layout, extras, clip=True)
    if return_model:
        model_out = _from_work_image(model, layout, None, clip=False)
        return corrected_out, model_out
    return corrected_out


def source_with_protection_overlay(image, user_mask=None, *, alpha=0.48):
    """Return a source-shaped preview with the optional protection mask overlaid."""

    work, layout, extras = _to_work_image(image)
    display = np.asarray(work, dtype=np.float32)

    mask = _coerce_mask_plane(user_mask, display.shape[:2]) if user_mask is not None else None
    if mask is None or float(np.max(mask, initial=0.0)) <= 0.0:
        return _from_work_image(display, layout, extras, clip=True)

    overlay_color = np.array([1.0, 0.69, 0.0], dtype=np.float32)
    blend = np.clip(mask, 0.0, 1.0) * float(np.clip(alpha, 0.0, 1.0))
    if display.ndim == 2:
        base = np.repeat(display[..., np.newaxis], 3, axis=-1)
        out = base * (1.0 - blend[..., np.newaxis]) + overlay_color * blend[..., np.newaxis]
        out = np.clip(out, 0.0, 1.0)
        if layout == "chw_mono":
            return np.moveaxis(out, -1, 0).astype(np.float32, copy=False)
        return out.astype(np.float32, copy=False)

    out = display * (1.0 - blend[..., np.newaxis]) + overlay_color * blend[..., np.newaxis]
    return _from_work_image(out, layout, extras, clip=True)

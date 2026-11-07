# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Cyril Richard
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (HDR Multiscale for Siril) by Franklin Marek (Seti Astro Suite), adapted for Siril by Cyril Richard.
# AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/HDR_multiscale.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""HDR Multiscale core: wavelet-based dynamic range compression for stretched images.

Everything from ``_B3`` to ``compute_wavescale_hdr`` is the upstream "Core Math Functions" section, unchanged
apart from ``_conv_sep_reflect``, which no longer calls SciPy (see its docstring).
``apply_hdr_multiscale`` is what the upstream dialog does around it: it reads a mono or RGB image as RGB in [0, 1],
blends the transformed image back through the luminance mask, and averages a mono source's result back to one plane.
"""

from __future__ import annotations

import numpy as np


UPSTREAM_VERSION = "1.0.2"

DEFAULT_SCALES = 5
DEFAULT_COMPRESSION = 1.5
DEFAULT_MASK_GAMMA = 5.0
DECAY_RATE = 0.5


# ============================================================================
# Core Math Functions
# ============================================================================

_B3 = np.array([1, 4, 6, 4, 1], dtype=np.float32) / 16.0


def _reflect_index(indices, size):
    """Map indices onto ``range(size)`` by half-sample symmetric extension, scipy.ndimage's ``reflect`` mode."""

    period = 2 * size
    folded = np.mod(indices, period)
    return np.where(folded >= size, period - 1 - folded, folded)


def _conv_sep_reflect(image2d, k1d, axis):
    """Separable 1D convolution with reflect padding

    Port divergence: upstream calls ``scipy.ndimage.convolve(image2d, k1d.reshape(...), mode="reflect")``. When a
    scale's dilated kernel is much longer than the image, as at high scale counts on a small preview area, SciPy reads
    past the reflected border and the result changes from run to run, NaN included. This computes the same convolution
    from the kernel's non-zero taps over an explicitly reflected copy, adding them in SciPy's order in float64, so it is
    bit-identical to SciPy wherever SciPy is stable and well-defined everywhere else.
    """
    kernel = np.asarray(k1d, dtype=np.float32)
    radius = len(kernel) // 2
    size = image2d.shape[axis]
    padded = np.take(image2d, _reflect_index(np.arange(-radius, size + radius), size), axis=axis)
    acc = np.zeros(image2d.shape, dtype=np.float64)
    window = [slice(None)] * image2d.ndim
    for tap, weight in enumerate(kernel[::-1]):
        if weight == 0.0:
            continue
        window[axis] = slice(tap, tap + size)
        acc += padded[tuple(window)].astype(np.float64) * np.float64(weight)
    return acc.astype(np.float32)


def _build_spaced_kernel(kernel, scale_idx):
    """Build dilated kernel for à trous algorithm"""
    if scale_idx == 0:
        return kernel.astype(np.float32, copy=False)
    step = 2**scale_idx
    spaced_len = len(kernel) + (len(kernel) - 1) * (step - 1)
    spaced = np.zeros(spaced_len, dtype=np.float32)
    spaced[0::step] = kernel
    return spaced


def _atrous_decompose(img2d, n_scales, base_k):
    """À trous wavelet decomposition"""
    current = img2d.astype(np.float32, copy=True)
    scales = []
    for s in range(n_scales):
        k = _build_spaced_kernel(base_k, s)
        tmp = _conv_sep_reflect(current, k, axis=1)
        smooth = _conv_sep_reflect(tmp, k, axis=0)
        scales.append(current - smooth)
        current = smooth
    scales.append(current)
    return scales


def _atrous_reconstruct(scales):
    """Reconstruct from wavelet scales"""
    out = scales[-1].astype(np.float32, copy=True)
    for w in scales[:-1]:
        out += w
    return out


def _rgb_to_lab(rgb):
    """RGB to Lab color space conversion"""
    M = np.array(
        [[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]],
        dtype=np.float32,
    )
    rgb = np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)
    xyz = rgb.reshape(-1, 3) @ M.T
    xyz = xyz.reshape(rgb.shape)
    xyz[..., 0] /= 0.95047
    xyz[..., 2] /= 1.08883

    delta = 6 / 29

    def f(t):
        return np.where(t > delta**3, np.cbrt(t), (t / (3 * delta**2)) + (4 / 29))

    fx, fy, fz = f(xyz[..., 0]), f(xyz[..., 1]), f(xyz[..., 2])
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return np.stack([L, a, b], axis=-1)


def _lab_to_rgb(lab):
    """Lab to RGB color space conversion"""
    M_inv = np.array(
        [[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560], [0.0556434, -0.2040259, 1.0572252]],
        dtype=np.float32,
    )
    delta = 6 / 29
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0

    def finv(t):
        return np.where(t > delta, t**3, 3 * delta**2 * (t - 4 / 29))

    X = 0.95047 * finv(fx)
    Y = finv(fy)
    Z = 1.08883 * finv(fz)
    xyz = np.stack([X, Y, Z], axis=-1)
    rgb = xyz.reshape(-1, 3) @ M_inv.T
    rgb = rgb.reshape(xyz.shape)
    return np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)


def _mask_from_L(L, gamma):
    """Create luminance mask from L channel"""
    m = np.clip(L / 100.0, 0.0, 1.0).astype(np.float32)
    if gamma != 1.0:
        m = np.power(m, gamma, dtype=np.float32)
    return m


def _apply_dim_curve(rgb, gamma):
    """Apply dimming curve to tame highlights"""
    return np.power(np.clip(rgb, 0.0, 1.0), gamma, dtype=np.float32)


def compute_wavescale_hdr(
    rgb_image, n_scales=5, compression_factor=1.5, mask_gamma=1.0, base_kernel=_B3, decay_rate=0.5, dim_gamma=None
):
    """
    Main HDR processing function
    Returns (transformed_rgb, luminance_mask)
    """
    lab = _rgb_to_lab(rgb_image)
    L0 = lab[..., 0].astype(np.float32, copy=True)
    scales = _atrous_decompose(L0, n_scales, base_kernel)

    mask = _mask_from_L(L0, mask_gamma)
    planes, residual = scales[:-1], scales[-1]

    # Process detail layers with decay
    for i, wp in enumerate(planes):
        decay = decay_rate**i
        scale = (1.0 + (compression_factor - 1.0) * mask * decay) * 2.0
        planes[i] = wp * scale

    Lr = _atrous_reconstruct(planes + [residual])

    # Midtones alignment
    med0 = float(np.median(L0))
    med1 = float(np.median(Lr)) or 1.0
    Lr = np.clip(Lr * (med0 / med1), 0.0, 100.0)

    lab[..., 0] = Lr
    rgb = _lab_to_rgb(lab)

    # Dimming curve
    g = (1.0 + n_scales * 0.2) if dim_gamma is None else float(dim_gamma)
    rgb = _apply_dim_curve(rgb, gamma=g)

    return rgb, mask


# ============================================================================
# The upstream dialog's work around the core (WaveScaleHDRDialog)
# ============================================================================


def normalize_input(image):
    """Return ``image`` as float32, with integer samples divided by their type's maximum."""

    data = np.asarray(image)
    if np.issubdtype(data.dtype, np.integer):
        return data.astype(np.float32) / float(np.iinfo(data.dtype).max)
    return data.astype(np.float32, copy=False)


def apply_hdr_multiscale(
    image,
    *,
    n_scales=DEFAULT_SCALES,
    compression_factor=DEFAULT_COMPRESSION,
    mask_gamma=DEFAULT_MASK_GAMMA,
    return_mask=False,
):
    """Run HDR Multiscale on an (H, W), (H, W, 1) or (H, W, 3) image in [0, 1] as the upstream dialog does.

    A mono image is processed as three equal channels and its result is their mean. The transformed image is blended
    with the source through the luminance mask, so dark areas keep their original values. With ``return_mask`` the
    luminance mask is returned in the source's shape instead of the result.
    """

    source = np.asarray(image, dtype=np.float32)
    mono = source.ndim == 2 or (source.ndim == 3 and source.shape[-1] == 1)
    if source.ndim == 3 and source.shape[-1] not in (1, 3):
        raise ValueError(f"HDR Multiscale expects a mono or RGB image; got shape {source.shape}.")
    plane = source.reshape(source.shape[0], source.shape[1]) if mono else source
    rgb = np.repeat(plane[:, :, None], 3, axis=2) if mono else plane
    rgb = np.clip(rgb, 0.0, 1.0).astype(np.float32, copy=False)

    transformed, mask = compute_wavescale_hdr(
        rgb, int(n_scales), float(compression_factor), float(mask_gamma), _B3, decay_rate=DECAY_RATE
    )
    if return_mask:
        if mono:
            return mask if source.ndim == 2 else mask[..., None]
        return np.repeat(mask[..., None], 3, axis=2)

    m3 = np.repeat(mask[..., None], 3, axis=2)
    blended = rgb * (1.0 - m3) + transformed * m3
    if mono:
        blended = np.mean(blended, axis=2, dtype=np.float32)
        if source.ndim == 3:
            blended = blended[..., None]
    return np.clip(blended, 0.0, 1.0).astype(np.float32, copy=False)

# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 Adrian Knagg-Baugh
# Copyright (c) 2025 Dave Lindner
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (Narrowband Continuum Subtraction for Siril) by Adrian Knagg-Baugh and Dave Lindner.
# AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/ContinuumSubtraction.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""Continuum Subtraction core: the continuum factor estimate, the subtraction and the RGB blend.

``aad``, ``find_min`` and ``compute_c`` are the upstream estimate: a coarse scan of the scale factor, a fine scan
around its minimum and a smooth-V fit of the average absolute deviation (AAD) of ``emission - continuum * c`` over a
region. The upstream dialog's Generate and Blend buttons are ``subtract_continuum`` and ``blend_into_rgb``.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import curve_fit


UPSTREAM_VERSION = "v3.0.7"

DEFAULT_C = 0.2
DEFAULT_STRENGTH = 2.0
LINES = ("Ha", "SII", "OIII")
# The upstream dialog's channel weights for each line: Ha into red, SII into green, OIII into blue.
LINE_WEIGHTS = {"Ha": (1.0, 0.0, 0.0), "SII": (0.0, 1.0, 0.0), "OIII": (0.0, 0.0, 1.0)}


def aad(data):
    mean = np.mean(data)
    return np.mean(np.abs(data - mean))


def find_min(nb, co, c_median, progress=None):
    scale_factors = np.linspace(-1, 5, 12)
    aad_values = []

    for i, sf in enumerate(scale_factors):
        value = aad(nb - (co - c_median) * sf)
        aad_values.append(value)
        if progress is not None:
            progress("Coarse bounds check...", i / (len(scale_factors) - 1))

    min_val = scale_factors[np.argmin(aad_values)]
    return min_val


def smooth_v(x, A, s0, eps, B):
    return A * np.sqrt((x - s0) ** 2 + eps**2) + B


def select_region(image, selection):
    """Return the pixels of ``image`` the estimate reads.

    ``selection`` is the upstream ``(x, y, width, height)`` rectangle, a boolean mask of the image's shape, or None for
    the whole image.
    """

    data = np.asarray(image)
    if selection is None:
        return data
    if isinstance(selection, np.ndarray):
        return data[selection]
    x, y, w, h = (int(value) for value in selection)
    return data[y : y + h, x : x + w]


def compute_c(narrowband_image, continuum_image, selection=None, c_median=None, progress=None):
    """Compute the optimal continuum scaling factor c

    Returns ``(c, details)``. ``details`` holds the fine scan (``scale_factors``, ``aad_values``), the fitted smooth-V
    parameters ``popt`` and ``fit_failed``. Port divergence: upstream lets a failed fit, or an infeasible starting
    point when the AAD minimum sits below zero, end the estimate with an error; here c falls back to the fine scan's
    best factor, clipped to [0, 1], and ``fit_failed`` says so.
    """
    nb = select_region(narrowband_image, selection)
    co = select_region(continuum_image, selection)
    if c_median is None:
        c_median = float(np.median(nb))

    approx_min = find_min(nb, co, c_median, progress)
    max_val = approx_min + 1.0
    min_val = approx_min - 1.0

    scale_factors = np.linspace(min_val, max_val, 40)
    aad_values = []

    for i, sf in enumerate(scale_factors):
        value = aad(nb - (co - c_median) * sf)
        aad_values.append(value)
        if progress is not None:
            progress("Optimizing continuum subtraction...", i / (len(scale_factors) - 1))

    B0 = np.min(aad_values)
    s0_0 = scale_factors[np.argmin(aad_values)]
    slope_est = (aad_values[-1] - aad_values[0]) / (scale_factors[-1] - scale_factors[0])
    A0 = slope_est
    eps0 = 0.01
    p0 = [A0, s0_0, eps0, B0]
    lb = [-1.0, 0.00, 0.0, 0.00]
    ub = [np.inf, 2 * max_val, np.inf, np.inf]

    details = {"scale_factors": scale_factors, "aad_values": aad_values, "popt": None, "fit_failed": False}
    try:
        popt, _ = curve_fit(smooth_v, scale_factors, aad_values, p0=p0, bounds=(lb, ub))
    except RuntimeError, ValueError:
        details["fit_failed"] = True
        return float(np.clip(s0_0, 0, 1)), details

    A_opt, s0_opt, eps_opt, B_opt = popt
    details["popt"] = popt
    c = float(np.clip(s0_opt, 0, 1))
    return c, details


def subtract_continuum(emission, continuum, c):
    """The upstream Generate step: ``emission - c * continuum``."""

    return np.asarray(emission, dtype=np.float32) - np.float32(c) * np.asarray(continuum, dtype=np.float32)


def blend_into_rgb(rgb, cs, strength, weights):
    """The upstream Blend step: add the median-centred continuum-subtracted line to each channel by its weight.

    ``rgb`` is (H, W, 3), ``cs`` is (H, W); the result keeps ``rgb``'s range, unclipped, as upstream writes it.
    """

    rgb = np.asarray(rgb, dtype=np.float32)
    cs_data = np.asarray(cs, dtype=np.float32)
    cs_median = np.median(cs_data)
    out = np.empty_like(rgb)
    for channel, weight in enumerate(weights):
        out[..., channel] = rgb[..., channel] + (cs_data - cs_median) * strength * weight
    return out


def normalize_input(image):
    """Return ``image`` as float32, with integer samples divided by their type's maximum."""

    data = np.asarray(image)
    if np.issubdtype(data.dtype, np.integer):
        return data.astype(np.float32) / float(np.iinfo(data.dtype).max)
    return data.astype(np.float32, copy=False)

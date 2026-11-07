# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Yannick Dutertre
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (NarrowbandNormalization for Siril) by Yannick Dutertre, built on the mathematics of Bill Blanshan and
# Mike Cranfield's NarrowbandNormalization PixInsight script, used with Bill Blanshan's permission.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/NarrowbandNormalization.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""NarrowbandNormalization core: the upstream NumPy engine, unchanged apart from input normalization.

Everything from ``_EPS`` to ``process_image`` is the upstream "CORE MATH ENGINE" and "PALETTE HANDLING" sections.
``normalize_input`` replaces the upstream "max above 1.5 means 16-bit" rule with one that reads the sample type, so
8-bit and 32-bit integer images land in [0, 1] too.
"""

from __future__ import annotations

import numpy as np


UPSTREAM_VERSION = "1.0.5"

PALETTES = ("HOO", "SHO", "HSO", "HOS")
LIGHTNESS_SOURCES = ("Off", "Original", "Ha", "SII", "OIII")
BLEND_MODES = ("Mode 1", "Mode 2", "Mode 3")

DEFAULT_PARAMS = {
    "palette": "HOO",
    "lightness": "Off",
    "blend_mode": "Mode 1",
    "blend_amount": 0.6,
    "scnr": 0.0,
    "oiii_boost": 1.0,
    "sii_boost": 1.0,
    "shadow_point": 1.0,
    "highlight_reduction": 1.0,
    "brightness": 1.0,
}


def normalize_input(image):
    """Return ``image`` as float32 in the [0, 1] working range.

    Integer samples are divided by their type's maximum. Floating-point samples whose maximum passes 1.5 are read as
    16-bit counts, as the upstream script reads them.
    """

    data = np.asarray(image)
    if np.issubdtype(data.dtype, np.integer):
        return data.astype(np.float32) / float(np.iinfo(data.dtype).max)
    return _normalize_range(data)


# ========================================================================
# CORE MATH ENGINE  (pure numpy -- no Qt / Siril dependency, unit-testable)
# ========================================================================

# Epsilon for divide-by-zero guards. Sized for float32 precision (~1.19e-7
# machine epsilon) rather than float64's ~2.2e-16 -- now that the pipeline
# runs in float32 throughout (see process_image), a 1e-12 threshold would be
# finer than float32 can even represent near typical operating magnitudes,
# making the guard effectively a no-op.
_EPS = 1e-6


def _mtf(m, x):
    """PixInsight-style midtones transfer function, m is a scalar."""
    x = np.asarray(x, dtype=np.float32)
    if abs(m - 0.5) < 1e-9:
        return x.copy()
    denom = (2.0 * m - 1.0) * x - m
    denom = np.where(np.abs(denom) < _EPS, np.copysign(_EPS, denom), denom)
    return ((m - 1.0) * x) / denom


def _rescale(x, lo, hi):
    if abs(hi - lo) < _EPS:
        return np.clip(x - lo, 0.0, 1.0)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def _normalize_range(data):
    data = np.asarray(data, dtype=np.float32)
    if data.size and float(np.nanmax(data)) > 1.5:
        return data / 65535.0
    return data


def _channel_stats(ch, blackpoint):
    """Returns (M, E0) exactly as the PixelMath M / E0 expressions do.
    Reductions (mean) explicitly accumulate in float64 even though ch
    itself is float32, to avoid precision loss when summing millions of
    pixels -- this costs nothing extra in memory since the result is a
    scalar, not a full-resolution array."""
    mn = float(np.min(ch))
    med = float(np.median(ch))
    M = mn + blackpoint * (med - mn)
    mean = float(np.mean(ch, dtype=np.float64))
    adev = float(np.mean(np.abs(ch - mean), dtype=np.float64))  # PixelMath adev()
    E0 = adev / 1.2533 + mean - M
    return M, E0


def _boost_factor(a_target, a_ref, boost):
    """The E1 / E4 rational boost-strength expression."""
    denom = a_target - 2.0 * a_target * a_ref + a_ref
    if abs(denom) < 1e-9:
        denom = 1e-9
    return (a_target * (1.0 - a_ref) / denom) / boost


def _normalize_channel(ch, M_ch, strength):
    """E2/E5 (rescale) + E3/E6 (screen-blended mtf stretch)."""
    rescaled = _rescale(ch, M_ch, 1.0)
    stretched = _mtf(strength, rescaled)
    floor_part = np.minimum(ch, M_ch)
    out = 1.0 - (1.0 - stretched) * (1.0 - floor_part)
    return np.clip(out, 0.0, 1.0)


# --- sRGB <-> XYZ <-> LAB, used only for the "Lightness" feature ---


def _srgb_to_linear(c):
    c = np.clip(c, 0.0, None)
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def _linear_to_srgb(c):
    c = np.clip(c, 0.0, None)
    return np.where(c > 0.0031308, 1.055 * (c ** (1.0 / 2.4)) - 0.055, 12.92 * c)


def _rgb_to_xyz(r, g, b):
    r1, g1, b1 = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)
    X = r1 * 0.4360747 + g1 * 0.3850649 + b1 * 0.1430804
    Y = r1 * 0.2225045 + g1 * 0.7168786 + b1 * 0.0606169
    Z = r1 * 0.0139322 + g1 * 0.0971045 + b1 * 0.7141733
    return X, Y, Z


def _f_lab(t):
    return np.where(t > 0.008856, np.cbrt(t), (7.787 * t) + 16.0 / 116.0)


def _f_lab_inv(t):
    return np.where(t > 0.206893, t**3, (t - 16.0 / 116.0) / 7.787)


def _xyz_to_lab(X, Y, Z):
    X1, Y1, Z1 = _f_lab(X), _f_lab(Y), _f_lab(Z)
    L = 116.0 * Y1 - 16.0
    a = 500.0 * (X1 - Y1)
    b = 200.0 * (Y1 - Z1)
    return L, a, b


def _lab_to_xyz(L, a, b):
    Y1 = (L + 16.0) / 116.0
    X1 = a / 500.0 + Y1
    Z1 = Y1 - b / 200.0
    return _f_lab_inv(X1), _f_lab_inv(Y1), _f_lab_inv(Z1)


def _xyz_to_rgb(X, Y, Z):
    R = X * 3.1338561 + Y * -1.6168667 + Z * -0.4906146
    G = X * -0.9787684 + Y * 1.9161415 + Z * 0.0334540
    B = X * 0.0719453 + Y * -0.2289914 + Z * 1.4052427
    return _linear_to_srgb(R), _linear_to_srgb(G), _linear_to_srgb(B)


def _cie_l_only(r, g, b):
    """CIEL(...) equivalent: just the L component, remapped like the
    Y2 formula does with (L+16)/116, ready to be used as Y2 directly."""
    X, Y, Z = _rgb_to_xyz(r, g, b)
    L, _, _ = _xyz_to_lab(X, Y, Z)
    return (L + 16.0) / 116.0


# --- synthetic green (HOO only) ---


def _synthetic_green(ha, oiii, mode, amount):
    amount = float(np.clip(amount, 0.0, 1.0))
    if mode == "Mode 1":  # linear alpha blend
        g = amount * ha + (1.0 - amount) * oiii
    elif mode == "Mode 2":  # geometric / "Cannistra-style" multiplicative blend
        g = (np.clip(ha, 0, 1) ** amount) * (np.clip(oiii, 0, 1) ** (1.0 - amount))
    else:  # "Mode 3": screen blend
        g = 1.0 - (1.0 - amount * ha) * (1.0 - (1.0 - amount) * oiii)
    return np.clip(g, 0.0, 1.0)


# --- final tone-shaping stage (E11 / E12 / E13) ---


def _highlight_reduction(x, hl_reduction):
    hl_reduction = max(hl_reduction, 1e-3)
    m = 1.0 - 0.5 / hl_reduction
    term_a = _mtf(m, x) * x
    term_b = x * (1.0 - x)
    return term_a + term_b


def _brightness_stretch(x, brightness):
    brightness = max(brightness, 1e-3)
    return _mtf(1.0 / brightness * 0.5, x)


# ========================================================================
# PALETTE HANDLING
# ========================================================================

# Maps palette name -> {source_name: rgb_slot_index}.
# The letter order in the palette name IS the R,G,B slot assignment.
PALETTE_SLOTS = {
    "HOO": {"Ha": 0, "OIII": 2},  # G is synthetic, no real SII
    "SHO": {"SII": 0, "Ha": 1, "OIII": 2},
    "HSO": {"Ha": 0, "SII": 1, "OIII": 2},
    "HOS": {"Ha": 0, "OIII": 1, "SII": 2},
}


def process_image(data, params):
    """
    data   : numpy array, shape (H, W, 3), float in [0, 1], channels already
             arranged in R,G,B slots matching the chosen palette's letter
             order (e.g. for 'SHO' slot 0 is SII, slot 1 is Ha, slot 2 is OIII).
    params : dict with keys:
             palette, lightness, blend_mode, blend_amount, scnr,
             oiii_boost, sii_boost, shadow_point, highlight_reduction,
             brightness
    returns: numpy array, shape (H, W, 3), float in [0, 1]
    """
    palette = params["palette"]
    slots = PALETTE_SLOTS[palette]
    data = np.asarray(data, dtype=np.float32)

    ha = data[:, :, slots["Ha"]]
    oiii = data[:, :, slots["OIII"]]
    sii = data[:, :, slots["SII"]] if "SII" in slots else None

    blackpoint = params["shadow_point"]

    # --- statistics & boost factors (reference is always Ha; the
    #     "M[1]" divisor in the original script is always the OIII M) ---
    M_ha, E0_ha = _channel_stats(ha, blackpoint)
    M_o, E0_o = _channel_stats(oiii, blackpoint)
    ref_denom = 1.0 - M_o
    if abs(ref_denom) < 1e-9:
        ref_denom = 1e-9
    A0_ha = E0_ha / ref_denom
    A0_o = E0_o / ref_denom

    E1 = _boost_factor(A0_o, A0_ha, params["oiii_boost"])
    oiii_norm = _normalize_channel(oiii, M_o, E1)

    if sii is not None:
        M_s, E0_s = _channel_stats(sii, blackpoint)
        A0_s = E0_s / ref_denom
        E4 = _boost_factor(A0_s, A0_ha, params["sii_boost"])
        sii_norm = _normalize_channel(sii, M_s, E4)
    else:
        sii_norm = None

    # --- assemble RGB into the palette's slot order ---
    out = np.empty_like(data)
    out[:, :, slots["Ha"]] = ha
    out[:, :, slots["OIII"]] = oiii_norm

    if sii is not None:
        out[:, :, slots["SII"]] = sii_norm
    else:
        green = _synthetic_green(ha, oiii_norm, params["blend_mode"], params["blend_amount"])
        # slot 1 is always the "G" slot for HOO in PALETTE_SLOTS
        out[:, :, 1] = green

    # --- SCNR (amount-based blend toward min(G, mean(R,B))) ---
    if sii is not None:
        scnr_amt = float(np.clip(params["scnr"], 0.0, 1.0))
        if scnr_amt > 0.0:
            r_slot, g_slot, b_slot = 0, 1, 2
            r_ch, g_ch, b_ch = out[:, :, r_slot], out[:, :, g_slot], out[:, :, b_slot]
            reduced = np.minimum(np.mean(np.stack([r_ch, b_ch]), axis=0), g_ch)
            out[:, :, g_slot] = (1.0 - scnr_amt) * g_ch + scnr_amt * reduced

    # --- Lightness (LAB) stage ---
    lightness = params["lightness"]
    if lightness != "Off":
        r, g, b = out[:, :, 0], out[:, :, 1], out[:, :, 2]
        X, Y, Z = _rgb_to_xyz(r, g, b)
        L, a, bb = _xyz_to_lab(X, Y, Z)
        del X, Y, Z, L  # L is never used below; free all four immediately

        if lightness == "Original":
            Y2 = _cie_l_only(data[:, :, 0], data[:, :, 1], data[:, :, 2])
        elif lightness == "Ha":
            Y2 = (ha + 0.16) / 1.16
        elif lightness == "SII" and sii is not None:
            Y2 = (sii + 0.16) / 1.16
        elif lightness == "SII" and sii is None:
            # No real SII in HOO: fall back to the raw (pre-normalization,
            # pre-blend) OIII channel, and let the caller know via a flag.
            Y2 = (oiii + 0.16) / 1.16
        else:  # "OIII"
            Y2 = (oiii + 0.16) / 1.16

        X2 = (a / 500.0) + Y2
        Z2 = Y2 - (bb / 200.0)
        del a, bb  # only needed to build X2/Z2, done with them now

        X3, Y3, Z3 = _f_lab_inv(X2), _f_lab_inv(Y2), _f_lab_inv(Z2)
        del X2, Y2, Z2

        r3, g3, b3 = _xyz_to_rgb(X3, Y3, Z3)
        del X3, Y3, Z3

        out[:, :, 0] = np.clip(r3, 0.0, 1.0)
        out[:, :, 1] = np.clip(g3, 0.0, 1.0)
        out[:, :, 2] = np.clip(b3, 0.0, 1.0)
        del r3, g3, b3

    # --- final highlight-reduction / brightness / clip ---
    out = _highlight_reduction(out, params["highlight_reduction"])
    out = _brightness_stretch(out, params["brightness"])
    out = _rescale(out, 0.0, 1.0)

    return out.astype(np.float32)

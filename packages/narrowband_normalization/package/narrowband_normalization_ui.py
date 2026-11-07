# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Yannick Dutertre
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (NarrowbandNormalization for Siril) by Yannick Dutertre. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/NarrowbandNormalization.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for Narrowband Normalization.

The controls, ranges and defaults are the upstream PyQt6 dialog's. The upstream dialog greys out the synthetic-green
controls unless the palette is HOO, and SCNR and SII boost when it is; ``enabled_when`` does the same here.
"""

from __future__ import annotations

from afternight import ui

import narrowband_normalization_core as core


ATTRIBUTION_TEXT = (
    f"AfterNight port of NarrowbandNormalization {core.UPSTREAM_VERSION} for Siril by Yannick Dutertre, built on "
    "Bill Blanshan and Mike Cranfield's NarrowbandNormalization mathematics with Bill Blanshan's permission. "
    "AfterNight port by Ezequiel Ruiz."
)

_HOO_ONLY = {"param": "palette", "equals": "HOO"}
_NOT_HOO = {"param": "palette", "not_equals": "HOO"}


def _float_param(param_id, label, *, default, minimum, maximum, tooltip, enabled_when=None):
    param = {
        "id": param_id,
        "type": "float",
        "label": label,
        "default": float(default),
        "min": float(minimum),
        "max": float(maximum),
        "step": 0.01,
        "tracking": False,
        "tooltip": tooltip,
    }
    if enabled_when is not None:
        param["enabled_when"] = dict(enabled_when)
    return param


def parameter_defs():
    defaults = core.DEFAULT_PARAMS
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            sub_area=True,
            sub_area_default_enabled=False,
            sub_area_size=[800, 600],
            sub_area_label="Preview: Narrowband Normalization",
            controls_panel_width=480,
            preview_hq_default=False,
            header_progress=False,
            target_selector=True,
            target_channel_filter=[3],
        ),
        {
            "id": "attribution",
            "type": "info",
            "text": ATTRIBUTION_TEXT,
        },
        {
            "id": "usage",
            "type": "info",
            "text": (
                "Use on a stretched RGB image whose channels already hold the palette's lines in its letter order: "
                "for SHO, red is SII, green is Ha and blue is OIII. HOO reads Ha from red and OIII from blue and "
                "builds green."
            ),
        },
        {
            "id": "palette_section",
            "type": "section",
            "label": "Palette",
        },
        {
            "id": "palette",
            "type": "choice",
            "label": "Palette",
            "default": defaults["palette"],
            "options": [[name, name] for name in core.PALETTES],
            "tooltip": "Which line each RGB channel holds, in the palette's letter order.",
        },
        {
            "id": "lightness",
            "type": "choice",
            "label": "Lightness",
            "default": defaults["lightness"],
            "options": [[name, name] for name in core.LIGHTNESS_SOURCES],
            "tooltip": (
                "Replaces the result's CIE L* with the original image's or one line's. HOO has no SII, so SII "
                "uses OIII there."
            ),
        },
        {
            "id": "green_section",
            "type": "section",
            "label": "Synthetic Green (HOO)",
        },
        {
            "id": "blend_mode",
            "type": "choice",
            "label": "Blend Mode",
            "default": defaults["blend_mode"],
            "options": [
                ["Mode 1 (linear)", "Mode 1"],
                ["Mode 2 (geometric)", "Mode 2"],
                ["Mode 3 (screen)", "Mode 3"],
            ],
            "enabled_when": dict(_HOO_ONLY),
            "tooltip": "How green is built from Ha and the normalized OIII.",
        },
        _float_param(
            "blend_amount",
            "Blend Amount",
            default=defaults["blend_amount"],
            minimum=0.0,
            maximum=1.0,
            enabled_when=_HOO_ONLY,
            tooltip="Share of Ha in the synthetic green; the rest is the normalized OIII.",
        ),
        {
            "id": "channel_section",
            "type": "section",
            "label": "Channel Controls",
        },
        _float_param(
            "scnr",
            "SCNR",
            default=defaults["scnr"],
            minimum=0.0,
            maximum=1.0,
            enabled_when=_NOT_HOO,
            tooltip="Blends green toward min(green, mean(red, blue)).",
        ),
        _float_param(
            "oiii_boost",
            "OIII Boost",
            default=defaults["oiii_boost"],
            minimum=0.5,
            maximum=2.0,
            tooltip="Strength of OIII's normalization toward Ha.",
        ),
        _float_param(
            "sii_boost",
            "SII Boost",
            default=defaults["sii_boost"],
            minimum=0.5,
            maximum=2.0,
            enabled_when=_NOT_HOO,
            tooltip="Strength of SII's normalization toward Ha.",
        ),
        {
            "id": "adjustment_section",
            "type": "section",
            "label": "Adjustments",
        },
        _float_param(
            "shadow_point",
            "Shadow Point",
            default=defaults["shadow_point"],
            minimum=0.0,
            maximum=1.0,
            tooltip="Where each line's floor sits between its minimum (0) and its median (1).",
        ),
        _float_param(
            "highlight_reduction",
            "Highlight Reduction",
            default=defaults["highlight_reduction"],
            minimum=0.1,
            maximum=3.0,
            tooltip="Compresses the highlights of the result; 1 leaves them as they are.",
        ),
        _float_param(
            "brightness",
            "Brightness",
            default=defaults["brightness"],
            minimum=0.1,
            maximum=3.0,
            tooltip="Midtones stretch of the result; 1 leaves it as it is.",
        ),
    ]

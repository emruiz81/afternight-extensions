# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 Adrian Knagg-Baugh
# Copyright (c) 2025 Dave Lindner
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (Narrowband Continuum Subtraction for Siril) by Adrian Knagg-Baugh and Dave Lindner.
# AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/ContinuumSubtraction.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""Native process-window parameter schemas for Continuum Subtraction and Continuum Blend.

The upstream dialog reads its images from files; here they are open views. Its Estimate, Generate and Blend buttons
become the two processes: Continuum Subtraction estimates c (or takes it from the slider) and subtracts the continuum
from the emission image, and Continuum Blend adds a continuum-subtracted line into an RGB image.
"""

from __future__ import annotations

from afternight import ui

import continuum_subtraction_core as core


ATTRIBUTION_TEXT = (
    f"AfterNight port of Narrowband Continuum Subtraction {core.UPSTREAM_VERSION} for Siril by Adrian Knagg-Baugh "
    "and Dave Lindner. AfterNight port by Ezequiel Ruiz."
)

_MANUAL_C = {"param": "estimate_c", "equals": False}
_AUTOMATIC_C = {"param": "estimate_c", "equals": True}
_CUSTOM_WEIGHTS = {"param": "preset", "equals": "Custom"}


def subtraction_parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            controls_panel_width=500,
            preview_hq_default=False,
            header_progress=False,
            target_selector=True,
            target_channel_filter=[1],
            target_selector_label="Emission line (linear)",
            target_selector_position="params",
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
                "Subtracts the broadband continuum from a linear, registered narrowband image: emission - c x "
                "continuum. For Ha the continuum is usually the red channel; extract it as a mono image first. The "
                "factor c is estimated by minimizing the result's average absolute deviation over a region around "
                "the subject."
            ),
        },
        {
            "id": "inputs",
            "type": "section",
            "label": "Images",
        },
        {
            "id": "emission_view",
            "type": "target_selector",
            "label": "Emission line (linear)",
            "tooltip": "The narrowband image the continuum is subtracted from; the result replaces it.",
        },
        {
            "id": "continuum_view",
            "type": "view_selector",
            "label": "Continuum (linear)",
            "default": "",
            "placeholder": "Select the continuum image",
            "channel_filter": [1],
            "match_target_geometry": True,
            "match_target_channels": True,
            "exclude_target": True,
            "tooltip": "Broadband image of the same field, registered to the emission image, such as its red channel.",
        },
        {
            "id": "factor",
            "type": "section",
            "label": "Continuum Factor",
        },
        {
            "id": "estimate_c",
            "type": "bool",
            "label": "Estimate c Automatically",
            "default": True,
            "tooltip": "Find c on every preview and Apply; the estimate is written to the log.",
        },
        {
            "id": "c",
            "type": "float",
            "label": "c",
            "default": core.DEFAULT_C,
            "min": 0.0,
            "max": 1.0,
            "step": 0.0001,
            "decimals": 4,
            "tracking": False,
            "enabled_when": dict(_MANUAL_C),
            "tooltip": "Continuum scaling factor used when it is not estimated.",
        },
        {
            "id": "region_mask",
            "type": "manual_mask_editor",
            "label": "Estimation Region",
            "use_param": "use_region_mask",
            "use_label": "Estimate within the painted region",
            "use_default": False,
            "brush_size": 80,
            "min_brush_size": 10,
            "max_brush_size": 400,
            "enabled_when": dict(_AUTOMATIC_C),
            "tooltip": (
                "Paint a generous region around the subject. Without it the whole image is used, which usually "
                "gives a poorer estimate."
            ),
        },
    ]


def blend_parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            controls_panel_width=500,
            preview_hq_default=False,
            header_progress=False,
            target_selector=True,
            target_channel_filter=[3],
            target_selector_label="RGB (linear)",
            target_selector_position="params",
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
                "Adds a continuum-subtracted line into a linear RGB image: each channel gains (line - median(line)) "
                "x strength x its weight."
            ),
        },
        {
            "id": "inputs",
            "type": "section",
            "label": "Images",
        },
        {
            "id": "rgb_view",
            "type": "target_selector",
            "label": "RGB (linear)",
            "tooltip": "The RGB image the line is added to; the result replaces it.",
        },
        {
            "id": "line_view",
            "type": "view_selector",
            "label": "Continuum-subtracted line",
            "default": "",
            "placeholder": "Select the continuum-subtracted image",
            "channel_filter": [1],
            "match_target_geometry": True,
            "match_target_channels": False,
            "exclude_target": True,
            "tooltip": "A mono result of Continuum Subtraction, registered to the RGB image.",
        },
        {
            "id": "blending",
            "type": "section",
            "label": "Blending",
        },
        {
            "id": "preset",
            "type": "choice",
            "label": "Channels",
            "default": "Ha",
            "options": [
                ["Ha into red", "Ha"],
                ["SII into green", "SII"],
                ["OIII into blue", "OIII"],
                ["Custom", "Custom"],
            ],
            "tooltip": "The upstream channel weights for each line, or your own.",
        },
        {
            "id": "strength",
            "type": "float",
            "label": "Strength (q)",
            "default": core.DEFAULT_STRENGTH,
            "min": 0.0,
            "max": 12.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "How strongly the line is added.",
        },
        *[
            {
                "id": f"{name.lower()}_weight",
                "type": "float",
                "label": f"{name} (%)",
                "default": default,
                "min": 0.0,
                "max": 100.0,
                "step": 1.0,
                "tracking": False,
                "enabled_when": dict(_CUSTOM_WEIGHTS),
                "tooltip": f"Share of the line added to {name.lower()} when Channels is Custom.",
            }
            for name, default in (("Red", 100.0), ("Green", 0.0), ("Blue", 0.0))
        ],
    ]

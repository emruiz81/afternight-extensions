# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Curves by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Curves.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Curves."""

from __future__ import annotations

from afternight import ui


ATTRIBUTION_TEXT = (
    "AfterNight port of VeraLux Curves, originally authored by Riccardo "
    "Paterniti for the VeraLux script suite."
)


def _domain_options():
    return [
        ["RGB/K", "RGB/K"],
        ["Red", "R"],
        ["Green", "G"],
        ["Blue", "B"],
        ["Luminance", "L"],
        ["Chrominance", "C"],
        ["Saturation", "S"],
    ]


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            sub_area=True,
            sub_area_default_enabled=False,
            sub_area_size=[800, 600],
            sub_area_label="Preview: Curves",
            controls_panel_width=520,
            preview_hq_default=True,
            header_progress=False,
            target_selector=True,
            target_channel_filter=[1, 3],
        ),
        {
            "id": "attribution",
            "type": "info",
            "text": ATTRIBUTION_TEXT,
        },
        {
            "id": "domain_section",
            "type": "section",
            "label": "Curve Domain",
        },
        {
            "id": "domain",
            "type": "choice",
            "label": "Domain",
            "default": "RGB/K",
            "options": _domain_options(),
            "tooltip": "Photometric domain to transform with the current curve.",
        },
        {
            "id": "curve_section",
            "type": "section",
            "label": "Curve",
        },
        {
            "id": "curve_points",
            "type": "curve_editor",
            "label": "Curve",
            "default": [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0]],
            "interpolation": "akima",
            "histogram": True,
            "grid": True,
            "guide": True,
            "histogram_areas": False,
            "tooltip": "Drag the curve to add or move points. Right-click an interior point to remove it.",
        },
        {
            "id": "range_section",
            "type": "section",
            "label": "Luminance Range",
        },
        {
            "id": "range_enabled",
            "type": "bool",
            "label": "Enable Range Limiting",
            "default": False,
            "tooltip": "Restrict the curve to a selected source-luminance range.",
        },
        {
            "id": "lum_min",
            "type": "float",
            "label": "Range Min",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.001,
            "tracking": False,
            "tooltip": "Minimum luminance included in the curve mask.",
        },
        {
            "id": "lum_max",
            "type": "float",
            "label": "Range Max",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.001,
            "tracking": False,
            "tooltip": "Maximum luminance included in the curve mask.",
        },
        {
            "id": "feather",
            "type": "float",
            "label": "Feather",
            "default": 0.25,
            "min": 0.0,
            "max": 1.0,
            "step": 0.001,
            "tracking": False,
            "tooltip": "Soft roll-off width at luminance-range boundaries.",
        },
    ]

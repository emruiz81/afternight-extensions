# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Curves by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Curves.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Curves."""

from __future__ import annotations

from afternight import ui

import veralux_curves_core as core


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
            size=[720, 700],
            resizable=True,
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
            "label": "Native Curve",
        },
        {
            "id": "black_point",
            "type": "float",
            "label": "Black Point",
            "default": 0.0,
            "min": 0.0,
            "max": 0.98,
            "step": 0.001,
            "tooltip": "Horizontal black-point clip. Values below this input map to the black endpoint.",
        },
        {
            "id": "shadow_lift",
            "type": "float",
            "label": "Shadow Lift",
            "default": 0.0,
            "min": 0.0,
            "max": 0.5,
            "step": 0.001,
            "tooltip": "Vertical black endpoint lift for matte or pedestal-preserving curves.",
        },
        {
            "id": "midtone_input",
            "type": "float",
            "label": "Midtone Input",
            "default": 0.5,
            "min": 0.01,
            "max": 0.99,
            "step": 0.001,
            "tooltip": "Input position of the middle curve control point.",
        },
        {
            "id": "midtone_output",
            "type": "float",
            "label": "Midtone Output",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.001,
            "tooltip": "Output value of the middle curve control point.",
        },
        {
            "id": "highlight_compression",
            "type": "float",
            "label": "Highlight Compression",
            "default": 0.0,
            "min": 0.0,
            "max": 0.5,
            "step": 0.001,
            "tooltip": "Vertical white endpoint reduction for gentle highlight damping.",
        },
        {
            "id": "white_point",
            "type": "float",
            "label": "White Point",
            "default": 1.0,
            "min": 0.01,
            "max": 1.0,
            "step": 0.001,
            "tooltip": "Horizontal white-point clip. Values above this input map to the white endpoint.",
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
            "tooltip": "Soft roll-off width at luminance-range boundaries.",
        },
        {
            "id": "upstream_version",
            "type": "info",
            "text": f"Ported from VeraLux Curves {core.UPSTREAM_VERSION}.",
        },
    ]

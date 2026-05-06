# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux StarComposer by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_StarComposer.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux StarComposer."""

from __future__ import annotations

from afternight import ui

from veralux_attribution import attribution_text
import veralux_starcomposer_core as core


ATTRIBUTION_TEXT = attribution_text("StarComposer", core.UPSTREAM_VERSION)


def _working_space_options():
    return [[name, name] for name in core.SENSOR_PROFILES.keys()]


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            preview_area=False,
            controls_panel_width=520,
            preview_hq_default=True,
            preview_autostretch=False,
            preview_autostretch_default=False,
            header_progress=False,
            target_selector=True,
            target_channel_filter=[1, 3],
            target_selector_label="Starless (stretched)",
            target_selector_position="params",
        ),
        {
            "id": "attribution",
            "type": "info",
            "text": ATTRIBUTION_TEXT,
        },
        {
            "id": "inputs",
            "type": "section",
            "label": "Inputs",
        },
        {
            "id": "starless_view",
            "type": "target_selector",
            "label": "Starless (stretched)",
            "tooltip": "Target starless base image used for output recomposition.",
        },
        {
            "id": "stars_view",
            "type": "view_selector",
            "label": "Stars (linear)",
            "default": "",
            "placeholder": "Select stars image",
            "channel_filter": [1, 3],
            "match_target_geometry": True,
            "match_target_channels": True,
            "exclude_target": True,
            "tooltip": "Second open image used as the shaped stars layer.",
        },
        {
            "id": "sensor",
            "type": "section",
            "label": "Sensor Profile",
        },
        {
            "id": "working_space",
            "type": "choice",
            "label": "Sensor Profile",
            "default": core.DEFAULT_PROFILE,
            "options": _working_space_options(),
            "tooltip": "Luminance weights used for hybrid color-vector reconstruction.",
        },
        {
            "id": "use_adaptive_anchor",
            "type": "bool",
            "label": "Adaptive Anchor",
            "default": True,
            "tooltip": "Automatically detects the black point of the star mask.",
        },
        {
            "id": "stretch",
            "type": "section",
            "label": "Star Stretch",
        },
        {
            "id": "log_d",
            "type": "float",
            "label": "Star Intensity",
            "default": 1.0,
            "min": 1.0,
            "max": 21.0,
            "step": 0.1,
            "tracking": False,
            "tooltip": "LogD-controlled rational stretch intensity.",
        },
        {
            "id": "profile_hardness",
            "type": "float",
            "label": "Profile Hardness",
            "default": 50.0,
            "min": 1.0,
            "max": 100.0,
            "step": 1.0,
            "tracking": False,
            "tooltip": "Toe-based PSF shaping control. Higher values tighten star profiles.",
        },
        {
            "id": "physics",
            "type": "section",
            "label": "Hybrid Physics",
        },
        {
            "id": "color_grip",
            "type": "float",
            "label": "Color Grip",
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Blends scalar sharpness with vector color-ratio preservation.",
        },
        {
            "id": "shadow_convergence",
            "type": "float",
            "label": "Shadow Convergence",
            "default": 0.0,
            "min": 0.0,
            "max": 3.0,
            "step": 0.1,
            "tracking": False,
            "tooltip": "Suppresses chromatic artifacts in low-signal star-mask shadows.",
        },
        {
            "id": "surgery",
            "type": "section",
            "label": "Star Surgery",
        },
        {
            "id": "large_structure_rejection",
            "type": "float",
            "label": "Large Structure Rejection",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Removes broad residual non-stellar structures from the mask.",
        },
        {
            "id": "star_reduction",
            "type": "float",
            "label": "Star Reduction",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Applies morphological reduction to shrink star diameters.",
        },
        {
            "id": "optical_healing",
            "type": "float",
            "label": "Optical Healing",
            "default": 0.0,
            "min": 0.0,
            "max": 20.0,
            "step": 1.0,
            "tracking": False,
            "tooltip": "Smooths chroma residuals while preserving luminance.",
        },
        {
            "id": "composition",
            "type": "section",
            "label": "Output Composition",
        },
        {
            "id": "blend_mode",
            "type": "choice",
            "label": "Blend Mode",
            "default": "screen",
            "options": [["Screen (Safe)", "screen"], ["Linear Add (Physical)", "linear_add"]],
            "tooltip": "Blend operation used when recomposing stars onto the active target.",
        },
    ]

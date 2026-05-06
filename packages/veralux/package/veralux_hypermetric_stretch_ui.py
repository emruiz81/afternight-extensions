# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Ported from VeraLux HyperMetric Stretch by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_HyperMetric_Stretch.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux HyperMetric Stretch."""

from __future__ import annotations

from afternight import ui

from veralux_attribution import attribution_text
import veralux_hypermetric_stretch_core as core


ATTRIBUTION_TEXT = attribution_text("HyperMetric Stretch", core.UPSTREAM_VERSION)


def _working_space_options():
    return [[name, name] for name in core.working_space_options()]


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            sub_area=True,
            sub_area_default_enabled=False,
            sub_area_size=[800, 600],
            sub_area_label="Preview: HyperMetric Stretch",
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
            "id": "workflow",
            "type": "section",
            "label": "Workflow",
        },
        {
            "id": "processing_mode",
            "type": "choice",
            "label": "Processing Mode",
            "default": "ready_to_use",
            "options": [
                ["Ready to Use", "ready_to_use"],
                ["Scientific", "scientific"],
            ],
            "tooltip": "Ready to Use applies final output scaling. Scientific exposes the color reconstruction controls.",
        },
        {
            "id": "working_space",
            "type": "choice",
            "label": "Sensor Profile",
            "default": core.DEFAULT_PROFILE,
            "options": _working_space_options(),
            "tooltip": "Luminance weights used to derive the stretch vector from RGB data.",
        },
        {
            "id": "target_bg",
            "type": "float",
            "label": "Target Background",
            "default": 0.20,
            "min": 0.05,
            "max": 0.50,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Median background target used when Auto-Calc Log D solves the stretch intensity.",
        },
        {
            "id": "stretch",
            "type": "section",
            "label": "HyperMetric Stretch",
        },
        {
            "id": "auto_log_d",
            "type": "button",
            "label": "Auto-Calc Log D",
            "button_role": "primary",
            "tooltip": "Compute the Log D value from the current image, Target Background, Sensor Profile, Protect b, and Adaptive Anchor settings.",
        },
        {
            "id": "log_d",
            "type": "float",
            "label": "Log D",
            "default": 2.0,
            "min": 0.0,
            "max": 7.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Hyperbolic stretch intensity. Use Auto-Calc Log D to solve this value from the current image.",
        },
        {
            "id": "protect_b",
            "type": "float",
            "label": "Protect b",
            "default": 6.0,
            "min": 0.1,
            "max": 15.0,
            "step": 0.1,
            "tracking": False,
            "tooltip": "Highlight protection knee for stellar cores and bright structures. Higher values preserve more headroom.",
        },
        {
            "id": "use_adaptive_anchor",
            "type": "bool",
            "label": "Adaptive Anchor",
            "default": True,
            "tooltip": "Estimate the signal anchor from the histogram instead of using a fixed black point.",
        },
        {
            "id": "convergence_power",
            "type": "float",
            "label": "Convergence Power",
            "default": 3.5,
            "min": 1.0,
            "max": 10.0,
            "step": 0.1,
            "tracking": False,
            "tooltip": "Controls how quickly saturated star color converges toward white in the highlights.",
        },
        {
            "id": "color",
            "type": "section",
            "label": "Ready Mode Color",
            "enabled_when": {"param": "processing_mode", "equals": "ready_to_use"},
        },
        {
            "id": "color_strategy",
            "type": "float",
            "label": "Color Strategy",
            "default": 0.0,
            "min": -1.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Ready mode color bias: negative values clean color noise, positive values soften highlight color.",
        },
        {
            "id": "scientific_color",
            "type": "section",
            "label": "Scientific Color Reconstruction",
            "enabled_when": {"param": "processing_mode", "equals": "scientific"},
        },
        {
            "id": "linear_expansion",
            "type": "float",
            "label": "Linear Expansion",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Scientific mode dynamic-range expansion applied before color reconstruction.",
        },
        {
            "id": "color_grip",
            "type": "float",
            "label": "Color Grip",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Scientific mode color-vector preservation strength.",
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
            "tooltip": "Scientific mode damping of color-vector preservation in shadows.",
        },
    ]

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux HyperMetric Stretch by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_HyperMetric_Stretch.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux HyperMetric Stretch."""

from __future__ import annotations

from afternight import ui

import veralux_hypermetric_stretch_core as core


ATTRIBUTION_TEXT = (
    "AfterNight port of VeraLux HyperMetric Stretch, originally authored by "
    "Riccardo Paterniti for the VeraLux Siril script suite."
)


def _working_space_options():
    return [[name, name] for name in core.working_space_options()]


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[720, 680],
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
            "id": "workflow",
            "type": "section",
            "label": "Workflow",
        },
        {
            "id": "processing_mode",
            "type": "choice",
            "label": "Mode",
            "default": "ready_to_use",
            "options": [
                ["Ready to Use", "ready_to_use"],
                ["Scientific", "scientific"],
            ],
            "tooltip": "Ready to Use applies final output scaling; Scientific keeps manual control.",
        },
        {
            "id": "working_space",
            "type": "choice",
            "label": "Working Space",
            "default": core.DEFAULT_PROFILE,
            "options": _working_space_options(),
            "tooltip": "Luminance weights used for the vector stretch.",
        },
        {
            "id": "target_bg",
            "type": "float",
            "label": "Target Background",
            "default": 0.20,
            "min": 0.05,
            "max": 0.50,
            "step": 0.01,
            "tooltip": "Ready-to-use median background target.",
        },
        {
            "id": "use_adaptive_anchor",
            "type": "bool",
            "label": "Adaptive Anchor",
            "default": True,
            "tooltip": "Analyze histogram shape to estimate the signal start.",
        },
        {
            "id": "auto_log_d",
            "type": "bool",
            "label": "Auto Log D",
            "default": False,
            "tooltip": "Solve Log D from the current image and target background.",
        },
        {
            "id": "stretch",
            "type": "section",
            "label": "Stretch",
        },
        {
            "id": "log_d",
            "type": "float",
            "label": "Log D",
            "default": 2.0,
            "min": 0.0,
            "max": 7.0,
            "step": 0.01,
            "tooltip": "Hyperbolic stretch intensity. Ignored when Auto Log D is enabled.",
        },
        {
            "id": "protect_b",
            "type": "float",
            "label": "Protect b",
            "default": 6.0,
            "min": 0.1,
            "max": 15.0,
            "step": 0.1,
            "tooltip": "Highlight protection knee for stellar cores and bright structures.",
        },
        {
            "id": "convergence_power",
            "type": "float",
            "label": "Star Core Recovery",
            "default": 3.5,
            "min": 1.0,
            "max": 10.0,
            "step": 0.1,
            "tooltip": "Controls transition speed from saturated color to white cores.",
        },
        {
            "id": "color",
            "type": "section",
            "label": "Color Engine",
        },
        {
            "id": "color_strategy",
            "type": "float",
            "label": "Ready Color Strategy",
            "default": 0.0,
            "min": -1.0,
            "max": 1.0,
            "step": 0.01,
            "tooltip": "Ready mode: negative cleans color noise, positive softens highlight color.",
        },
        {
            "id": "linear_expansion",
            "type": "float",
            "label": "Linear Expansion",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tooltip": "Scientific mode dynamic-range expansion before color reconstruction.",
        },
        {
            "id": "color_grip",
            "type": "float",
            "label": "Color Grip",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
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
            "tooltip": "Scientific mode damping of vector preservation in shadows.",
        },
    ]

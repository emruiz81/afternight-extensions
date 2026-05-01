# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Nox by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Nox.py
# Upstream baseline: a9fb2c7f505c488f5cfef5b7fa5022097551e06e; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Nox."""

from __future__ import annotations

from afternight import ui

import veralux_nox_core as core


ATTRIBUTION_TEXT = (
    "AfterNight port of VeraLux Nox, originally authored by Riccardo "
    "Paterniti for the VeraLux script suite."
)


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[700, 640],
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
            "id": "solver",
            "type": "section",
            "label": "Background Model",
        },
        {
            "id": "auto_tune",
            "type": "bool",
            "label": "Auto Tune",
            "default": True,
            "tooltip": "Derive stiffness and signal rejection from the active image statistics.",
        },
        {
            "id": "auto_mask",
            "type": "bool",
            "label": "Protect Signal",
            "default": True,
            "tooltip": "Exclude stars and bright structures from the background model.",
        },
        {
            "id": "stiffness",
            "type": "float",
            "label": "Stiffness",
            "default": 2.0,
            "min": 1.0,
            "max": 4.0,
            "step": 0.1,
            "tooltip": "Controls how smooth the estimated background surface should be.",
        },
        {
            "id": "rejection_power",
            "type": "float",
            "label": "Rejection Power",
            "default": 55.0,
            "min": 25.0,
            "max": 72.0,
            "step": 1.0,
            "tooltip": "Strength of bright-signal rejection while building the background model.",
        },
        {
            "id": "model_grid",
            "type": "float",
            "label": "Model Grid",
            "default": 64.0,
            "min": 16.0,
            "max": 128.0,
            "step": 1.0,
            "tooltip": "Resolution of the internal background model grid.",
        },
        {
            "id": "correction",
            "type": "section",
            "label": "Correction",
        },
        {
            "id": "correction_strength",
            "type": "float",
            "label": "Correction Strength",
            "default": 1.0,
            "min": 0.0,
            "max": 1.25,
            "step": 0.05,
            "tooltip": "Amount of estimated additive gradient removed from the image.",
        },
        {
            "id": "output_model",
            "type": "bool",
            "label": "Output Background Model",
            "default": False,
            "tooltip": "Write the estimated background surface instead of the corrected image.",
        },
        {
            "id": "upstream_version",
            "type": "info",
            "text": f"Ported from VeraLux Nox {core.UPSTREAM_VERSION}.",
        },
    ]

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Revela by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Revela.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Revela."""

from __future__ import annotations

from afternight import ui


ATTRIBUTION_TEXT = (
    "AfterNight port of VeraLux Revela, originally authored by Riccardo "
    "Paterniti for the VeraLux Siril script suite."
)


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[640, 520],
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
            "id": "enhancement",
            "type": "section",
            "label": "Enhancement",
        },
        {
            "id": "texture",
            "type": "float",
            "label": "Texture",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tooltip": "Enhances fine high-frequency details.",
        },
        {
            "id": "structure",
            "type": "float",
            "label": "Structure",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tooltip": "Enhances medium-frequency volume and body.",
        },
        {
            "id": "protection",
            "type": "section",
            "label": "Protection",
        },
        {
            "id": "shadow_authority",
            "type": "float",
            "label": "Shadow Authority",
            "default": 33.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tooltip": "Adaptive luminance gate used to avoid lifting the noise floor.",
        },
        {
            "id": "protect_stars",
            "type": "bool",
            "label": "Isolate Stars",
            "default": True,
            "tooltip": "Detects high-energy stellar profiles and excludes them from sharpening.",
        },
        {
            "id": "show_mask",
            "type": "bool",
            "label": "Render Protection Mask",
            "default": False,
            "tooltip": "Outputs the active enhancement mask instead of the enhanced image.",
        },
    ]

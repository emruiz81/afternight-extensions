# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Revela by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Revela.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Revela."""

from __future__ import annotations

from afternight import ui

from veralux_attribution import attribution_text
import veralux_revela_core as core


ATTRIBUTION_TEXT = attribution_text("Revela", core.UPSTREAM_VERSION)


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            sub_area=True,
            sub_area_default_enabled=False,
            sub_area_size=[800, 600],
            sub_area_label="Preview: Revela",
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
            "tracking": False,
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
            "tracking": False,
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
            "tracking": False,
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

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Vectra by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Vectra.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Vectra."""

from __future__ import annotations

from afternight import ui


ATTRIBUTION_TEXT = (
    "AfterNight port of VeraLux Vectra, originally authored by Riccardo "
    "Paterniti for the VeraLux script suite."
)


def _vector_section(prefix, label, hue_degrees):
    return [
        {
            "id": f"{prefix}_vector",
            "type": "section",
            "label": f"{label} Vector ({hue_degrees} deg)",
        },
        {
            "id": f"{prefix}_hue",
            "type": "float",
            "label": "Hue Shift",
            "default": 0.0,
            "min": -60.0,
            "max": 60.0,
            "step": 1.0,
            "tracking": False,
            "tooltip": f"Rotates the {label.lower()} LCH color vector.",
        },
        {
            "id": f"{prefix}_saturation",
            "type": "float",
            "label": "Saturation",
            "default": 0.0,
            "min": -100.0,
            "max": 100.0,
            "step": 1.0,
            "tracking": False,
            "tooltip": f"Boosts or reduces chroma around the {label.lower()} vector.",
        },
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
            sub_area_label="Preview: Vectra",
            controls_panel_width=520,
            preview_hq_default=True,
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
            "id": "vector_tabs",
            "type": "tabs",
        },
        {
            "id": "primary_vectors",
            "type": "tab",
            "label": "Primary Vectors",
        },
        *_vector_section("red", "Red", 0),
        *_vector_section("green", "Green", 120),
        *_vector_section("blue", "Blue", 240),
        {
            "id": "secondary_vectors",
            "type": "tab",
            "label": "Secondary Vectors",
        },
        *_vector_section("yellow", "Yellow", 60),
        *_vector_section("cyan", "Cyan", 180),
        *_vector_section("magenta", "Magenta", 300),
        {
            "id": "end_vector_tabs",
            "type": "end_tabs",
        },
        {
            "id": "protection",
            "type": "section",
            "label": "Protection (Neutrality Lock)",
        },
        {
            "id": "shadow_authority",
            "type": "float",
            "label": "Shadow Authority (Background Lock)",
            "default": 0.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tracking": False,
            "tooltip": "Locks neutral background and shadow noise against unwanted color tinting.",
        },
        {
            "id": "protect_stars",
            "type": "bool",
            "label": "White Star Integrity (Energy Protection)",
            "default": True,
            "tooltip": "Protects high-energy stellar cores from aggressive vector edits.",
        },
    ]

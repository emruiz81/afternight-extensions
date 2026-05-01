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


def _vector_params(prefix, label):
    return [
        {
            "id": f"{prefix}_hue",
            "type": "float",
            "label": f"{label} Hue Shift",
            "default": 0.0,
            "min": -60.0,
            "max": 60.0,
            "step": 1.0,
            "tooltip": f"Rotates the {label.lower()} LCH color vector.",
        },
        {
            "id": f"{prefix}_saturation",
            "type": "float",
            "label": f"{label} Saturation",
            "default": 0.0,
            "min": -1.0,
            "max": 1.0,
            "step": 0.01,
            "tooltip": f"Boosts or reduces chroma around the {label.lower()} vector.",
        },
    ]


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[720, 760],
            resizable=True,
            target_selector=True,
            target_channel_filter=[3],
        ),
        {
            "id": "attribution",
            "type": "info",
            "text": ATTRIBUTION_TEXT,
        },
        {
            "id": "primary_vectors",
            "type": "section",
            "label": "Primary Vectors",
        },
        *_vector_params("red", "Red"),
        *_vector_params("green", "Green"),
        *_vector_params("blue", "Blue"),
        {
            "id": "secondary_vectors",
            "type": "section",
            "label": "Secondary Vectors",
        },
        *_vector_params("cyan", "Cyan"),
        *_vector_params("magenta", "Magenta"),
        *_vector_params("yellow", "Yellow"),
        {
            "id": "protection",
            "type": "section",
            "label": "Protection",
        },
        {
            "id": "shadow_authority",
            "type": "float",
            "label": "Shadow Authority",
            "default": 0.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tooltip": "Locks neutral background and shadow noise against unwanted color tinting.",
        },
        {
            "id": "protect_stars",
            "type": "bool",
            "label": "White Star Integrity",
            "default": True,
            "tooltip": "Protects high-energy stellar cores from aggressive vector edits.",
        },
    ]

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Silentium by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Silentium.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Silentium."""

from __future__ import annotations

from afternight import ui

import veralux_silentium_core as core


ATTRIBUTION_TEXT = (
    "AfterNight port of VeraLux Silentium, originally authored by Riccardo "
    "Paterniti for the VeraLux script suite."
)


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[700, 660],
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
            "id": "linear_noise",
            "type": "section",
            "label": "Linear Noise Model",
        },
        {
            "id": "noise_intensity",
            "type": "float",
            "label": "Noise Intensity",
            "default": 25.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tooltip": "Global multiscale noise-reduction strength.",
        },
        {
            "id": "adaptive_noise",
            "type": "bool",
            "label": "Adaptive Noise Model",
            "default": True,
            "tooltip": "Estimate local background noise per image region instead of using one global sigma.",
        },
        {
            "id": "detail_guard",
            "type": "float",
            "label": "Detail Guard",
            "default": 50.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tooltip": "Protects real signal, edges, and stellar structure from smoothing.",
        },
        {
            "id": "shadow_smoothness",
            "type": "float",
            "label": "Shadow Smoothness",
            "default": 10.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tooltip": "Extra background-domain cleaning gated away from detected signal.",
        },
        {
            "id": "chroma",
            "type": "section",
            "label": "Chroma",
        },
        {
            "id": "enable_chroma",
            "type": "bool",
            "label": "Enable Chroma Denoise",
            "default": True,
            "tooltip": "Reduce color-channel noise after luminance-domain cleanup.",
        },
        {
            "id": "chroma_strength",
            "type": "float",
            "label": "Chroma Strength",
            "default": 30.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tooltip": "Relative strength of chroma denoising.",
        },
        {
            "id": "protection",
            "type": "section",
            "label": "Protection",
        },
        {
            "id": "protect_highlights",
            "type": "bool",
            "label": "Protect Highlights",
            "default": True,
            "tooltip": "Blend high-confidence signal and stellar cores back toward the source.",
        },
        {
            "id": "upstream_version",
            "type": "info",
            "text": f"Ported from VeraLux Silentium {core.UPSTREAM_VERSION}.",
        },
    ]

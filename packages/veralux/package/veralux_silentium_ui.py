# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Silentium) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Silentium.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Silentium."""

from __future__ import annotations

from afternight import ui

from veralux_attribution import attribution_text
import veralux_silentium_core as core


ATTRIBUTION_TEXT = attribution_text("Silentium", core.UPSTREAM_VERSION)


def parameter_defs():
    window_meta = ui.process_window_meta(
        panel_variant="native",
        size=[1260, 760],
        resizable=True,
        sub_area=True,
        sub_area_default_enabled=True,
        sub_area_size=[800, 600],
        sub_area_label="Preview: Silentium",
        controls_panel_width=520,
        preview_hq_default=False,
        preview_autostretch=True,
        header_progress=False,
        target_selector=True,
        target_channel_filter=[1, 3],
    )
    window_meta["preview_autostretch_default"] = True

    return [
        window_meta,
        {
            "id": "attribution",
            "type": "info",
            "text": ATTRIBUTION_TEXT,
        },
        {
            "id": "silentium_core",
            "type": "section",
            "label": "Silentium Core",
        },
        {
            "id": "noise_intensity",
            "type": "float",
            "label": "Noise Intensity (Log S)",
            "default": 0.5,
            "min": 0.0,
            "max": 2.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Global noise-reduction strength on VeraLux Silentium's original 0..2 Log S scale.",
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
            "tracking": False,
            "tooltip": "Protects real signal, edges, and stellar structure from smoothing.",
        },
        {
            "id": "chroma",
            "type": "section",
            "label": "Chrominance (Color Noise)",
        },
        {
            "id": "enable_chroma",
            "type": "bool",
            "label": "Enable Chroma Denoise (LAB)",
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
            "tracking": False,
            "tooltip": "Relative strength of chroma denoising.",
        },
        {
            "id": "deep_space",
            "type": "section",
            "label": "Deep Space Smoothness (Shadows)",
        },
        {
            "id": "shadow_smoothness",
            "type": "float",
            "label": "Shadow Smoothness",
            "default": 10.0,
            "min": 0.0,
            "max": 100.0,
            "step": 1.0,
            "tracking": False,
            "tooltip": "Extra background-domain cleaning gated away from detected signal.",
        },
        {
            "id": "star_field",
            "type": "section",
            "label": "Star Field Handling",
        },
        {
            "id": "use_stars",
            "type": "bool",
            "label": "Use Star Protection",
            "default": True,
            "tooltip": "Use AfterNight star profiling for the PSF-style protection stage from the original Silentium flow.",
        },
        {
            "id": "auto_starless",
            "type": "bool",
            "label": "Auto Starless Detection",
            "default": True,
            "tooltip": "Disable the star-protection mask automatically when too few stars are detected.",
        },
    ]

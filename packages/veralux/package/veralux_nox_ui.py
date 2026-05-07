# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Nox) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Nox.py
# Upstream baseline: a9fb2c7f505c488f5cfef5b7fa5022097551e06e; local port notes: see UPSTREAM.md.

"""Native RT-preview parameter schema for VeraLux Nox."""

from __future__ import annotations

from afternight import ui

from veralux_attribution import attribution_text
import veralux_nox_core as core


ATTRIBUTION_TEXT = attribution_text("Nox", core.UPSTREAM_VERSION)


PREVIEW_PROTECTION_MASK = "protection_mask"
PREVIEW_CORRECTED = "corrected"
PREVIEW_BACKGROUND = "background_model"


def parameter_defs():
    window_meta = ui.process_window_meta(
        panel_variant="native",
        size=[1260, 760],
        resizable=True,
        controls_panel_width=520,
        preview_hq_default=False,
        preview_autostretch=True,
        preview_autostretch_default=True,
        header_progress=False,
        target_selector=True,
        target_channel_filter=[1, 3],
    )
    window_meta["preview_area"] = False

    return [
        window_meta,
        {
            "id": "attribution",
            "type": "info",
            "text": ATTRIBUTION_TEXT,
        },
        {
            "id": "preview",
            "type": "section",
            "label": "Preview",
        },
        {
            "id": "preview_mode",
            "type": "choice",
            "label": "Display",
            "default": PREVIEW_CORRECTED,
            "options": [
                ["Processed Image", PREVIEW_CORRECTED],
                ["Extracted Gradient", PREVIEW_BACKGROUND],
                ["Protection Mask", PREVIEW_PROTECTION_MASK],
            ],
            "tooltip": "Select what the next preview refresh renders.",
            "inline_actions": [
                {
                    "id": "refresh_preview",
                    "type": "button",
                    "label": "Update Preview",
                    "button_role": "primary",
                    "preview_refresh_role": True,
                    "preview_refresh_on_open": True,
                    "tooltip": "Recompute the processed image and extracted gradient for the current parameters.",
                },
            ],
        },
        {
            "id": "preview_status",
            "type": "info",
            "tone": "warning",
            "preview_status": True,
            "text": "Preview update needed.",
            "stale_text": "Preview update needed.",
            "ready_text": "Preview is up to date.",
            "updating_text": "Updating preview...",
        },
        {
            "id": "manual_mask",
            "type": "manual_mask_editor",
            "label": "Manual Protection Mask",
            "use_param": "use_manual_mask",
            "use_label": "Use manual protection mask",
            "use_default": False,
            "display_param": "preview_mode",
            "display_value": PREVIEW_PROTECTION_MASK,
            "brush_size": 50,
            "min_brush_size": 10,
            "max_brush_size": 200,
            "preview_invalidates": True,
            "tooltip": "Paint protected signal regions before updating the Nox preview.",
        },
        {
            "id": "physics",
            "type": "section",
            "label": "Physics & Automation",
        },
        {
            "id": "auto_mask",
            "type": "bool",
            "label": "Use PSF Auto-Masking",
            "default": True,
            "preview_invalidates": True,
            "tooltip": "Use AfterNight star profiling and Nox topology weights to protect stars and faint signal.",
        },
        {
            "id": "auto_calculate",
            "type": "button",
            "label": "Auto-Calculate",
            "button_role": "secondary",
            "tooltip": "Analyze the active image and update stiffness and signal rejection power.",
        },
        {
            "id": "rejection_power",
            "type": "int",
            "label": "Signal Rejection Power",
            "default": 50,
            "min": 0,
            "max": 100,
            "step": 1,
            "tracking": False,
            "preview_invalidates": True,
            "tooltip": "Original Nox aggression scale. Higher values prioritize signal preservation.",
        },
        {
            "id": "rejection_power_readout",
            "type": "value_description_label",
            "source": "rejection_power",
            "decimals": 0,
            "suffix": "%",
            "separator": " - ",
            "text": "50% - Balanced",
            "ranges": [
                [0.0, 29.999, "Risky (Absorbs Signal)"],
                [30.0, 70.0, "Balanced"],
                [70.001, 100.0, "Safe (Protects Signal)"],
            ],
        },
        {
            "id": "stiffness",
            "type": "float",
            "label": "Membrane Stiffness",
            "default": 2.0,
            "min": 1.0,
            "max": 4.0,
            "step": 0.1,
            "tracking": False,
            "preview_invalidates": True,
            "tooltip": "Tension of the Zenith background membrane.",
        },
        {
            "id": "stiffness_readout",
            "type": "value_description_label",
            "source": "stiffness",
            "decimals": 1,
            "separator": " ",
            "text": "2.0",
            "ranges": [
                [1.0, 1.5, "Elastic (Vignette)"],
                [3.5, 4.0, "Rigid (Nebula)"],
            ],
        },
        {
            "id": "output",
            "type": "section",
            "label": "Output",
        },
        {
            "id": "save_gradient_model",
            "type": "bool",
            "label": "Save Gradient Model",
            "default": False,
            "tooltip": "Open the extracted gradient model as a separate AfterNight image on apply.",
        },
    ]

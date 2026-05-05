# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Alchemy by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Alchemy.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for VeraLux Alchemy."""

from __future__ import annotations

from afternight import ui

from veralux_attribution import attribution_text
import veralux_alchemy_core as core


ATTRIBUTION_TEXT = attribution_text("Alchemy", core.UPSTREAM_VERSION)


def _sensor_options():
    return [[name, name] for name in core.sensor_profile_names()]


def _mix_readout(param_id, source, text):
    return {
        "id": param_id,
        "type": "percentage_mix_label",
        "source": source,
        "left_label": "Ha",
        "right_label": "OIII",
        "text": text,
    }


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            sub_area=True,
            sub_area_default_enabled=False,
            sub_area_size=[800, 600],
            sub_area_label="Preview: Alchemy",
            controls_panel_width=520,
            preview_hq_default=True,
            preview_autostretch=True,
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
            "id": "sensor_profile_section",
            "type": "section",
            "label": "Sensor Profile",
        },
        {
            "id": "sensor_profile",
            "type": "choice",
            "label": "Sensor",
            "default": "Generic OSC",
            "options": _sensor_options(),
            "tooltip": "Sensor profile used when Quantum Unmixing is enabled.",
        },
        {
            "id": "quantum_unmix",
            "type": "bool",
            "label": "Quantum Unmixing",
            "default": False,
            "tooltip": "Separate Ha and OIII with sensor-specific dual-band crosstalk coefficients.",
        },
        {
            "id": "normalization",
            "type": "section",
            "label": "Normalization",
        },
        {
            "id": "bg_align",
            "type": "bool",
            "label": "Background Neutralization",
            "default": True,
            "tooltip": "Aligns green and blue median backgrounds to the red reference channel.",
        },
        {
            "id": "auto_fit",
            "type": "bool",
            "label": "Auto Signal Fit",
            "default": True,
            "tooltip": "Matches green and blue signal strength to the red reference channel.",
        },
        {
            "id": "boost",
            "type": "float",
            "label": "OIII Boost",
            "default": 1.0,
            "min": 0.5,
            "max": 5.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "Manual gain applied to normalized OIII channels.",
        },
        {
            "id": "palette",
            "type": "section",
            "label": "Palette Mixer",
        },
        {
            "id": "mix_r",
            "type": "float",
            "label": "Red OIII Mix",
            "default": 0.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "0.0 is pure Ha, 1.0 is pure OIII.",
        },
        _mix_readout("mix_r_readout", "mix_r", "100% Ha, 0% OIII"),
        {
            "id": "mix_g",
            "type": "float",
            "label": "Green OIII Mix",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "0.0 is pure Ha, 1.0 is pure OIII.",
        },
        _mix_readout("mix_g_readout", "mix_g", "0% Ha, 100% OIII"),
        {
            "id": "mix_b",
            "type": "float",
            "label": "Blue OIII Mix",
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "0.0 is pure Ha, 1.0 is pure OIII.",
        },
        _mix_readout("mix_b_readout", "mix_b", "0% Ha, 100% OIII"),
        {
            "id": "preset_hoo",
            "type": "button",
            "label": "HOO",
            "tooltip": "Classic bi-color preset: R=Ha, G=OIII, B=OIII.",
        },
        {
            "id": "preset_pseudo_sho",
            "type": "button",
            "label": "Pseudo-SHO",
            "tooltip": "Gold/blue preset: R=Ha, G=50% Ha and 50% OIII, B=OIII.",
        },
        {
            "id": "preset_hso",
            "type": "button",
            "label": "HSO",
            "tooltip": "HSO-style preset: R=Ha, G=Ha, B=OIII.",
        },
    ]

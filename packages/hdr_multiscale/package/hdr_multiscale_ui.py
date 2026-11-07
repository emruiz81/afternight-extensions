# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Cyril Richard
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (HDR Multiscale for Siril) by Franklin Marek, adapted for Siril by Cyril Richard.
# AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/HDR_multiscale.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""Native process-window parameter schema for HDR Multiscale, with the upstream dialog's ranges and defaults."""

from __future__ import annotations

from afternight import ui

import hdr_multiscale_core as core


ATTRIBUTION_TEXT = (
    f"AfterNight port of HDR Multiscale {core.UPSTREAM_VERSION} for Siril, written by Franklin Marek "
    "(Seti Astro Suite) and adapted for Siril by Cyril Richard. AfterNight port by Ezequiel Ruiz."
)


def parameter_defs():
    return [
        ui.process_window_meta(
            panel_variant="native",
            size=[1260, 760],
            resizable=True,
            sub_area=True,
            sub_area_default_enabled=False,
            sub_area_size=[800, 600],
            sub_area_label="Preview: HDR Multiscale",
            controls_panel_width=460,
            preview_hq_default=False,
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
            "id": "usage",
            "type": "info",
            "text": (
                "Use on a stretched, non-linear image. HDR Multiscale compresses bright areas through an a-trous "
                "wavelet decomposition of Lab lightness and blends the result in through a luminance mask, so the "
                "background keeps its values."
            ),
        },
        {
            "id": "parameters",
            "type": "section",
            "label": "Parameters",
        },
        {
            "id": "n_scales",
            "type": "int",
            "label": "Number of Scales",
            "default": core.DEFAULT_SCALES,
            "min": 2,
            "max": 10,
            "step": 1,
            "tracking": False,
            "tooltip": "Number of wavelet decomposition scales; more scales reach larger structures.",
        },
        {
            "id": "compression",
            "type": "float",
            "label": "Compression",
            "default": core.DEFAULT_COMPRESSION,
            "min": 0.1,
            "max": 5.0,
            "step": 0.01,
            "tracking": False,
            "tooltip": "HDR compression strength.",
        },
        {
            "id": "mask_gamma",
            "type": "float",
            "label": "Mask Gamma",
            "default": core.DEFAULT_MASK_GAMMA,
            "min": 0.1,
            "max": 10.0,
            "step": 0.1,
            "tracking": False,
            "tooltip": "Controls where the HDR effect is applied based on luminance; higher keeps it to brighter areas.",
        },
        {
            "id": "show_mask",
            "type": "bool",
            "label": "Show Luminance Mask",
            "default": False,
            "tooltip": "Outputs the luminance mask that blends the HDR result in, instead of the result.",
        },
    ]

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Silentium by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Silentium.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Silentium."""

from __future__ import annotations

import numpy as np

import afternight
from afternight import ui

import veralux_silentium_core as core
import veralux_silentium_ui as silentium_ui


class VeraLuxSilentiumExtension(ui.ProcessWindow):
    component = "extension.veralux_silentium"

    def get_params(self):
        return silentium_ui.parameter_defs()

    def execute(
        self,
        target,
        src_image,
        dst_image,
        params,
        progress,
        masks=None,
        weights=None,
        output_masks=None,
    ):
        del target, masks, weights, output_masks
        progress.set_text("Applying VeraLux Silentium...")
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Silentium processing was cancelled.")

        source = np.asarray(src_image.to_numpy())
        result = core.process_noise_reduction(
            source,
            intensity=float(params.get("noise_intensity", 25.0)),
            detail_guard=float(params.get("detail_guard", 50.0)),
            adaptive_noise=bool(params.get("adaptive_noise", True)),
            enable_chroma=bool(params.get("enable_chroma", True)),
            chroma_strength=float(params.get("chroma_strength", 30.0)),
            shadow_smoothness=float(params.get("shadow_smoothness", 10.0)),
            protect_highlights=bool(params.get("protect_highlights", True)),
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Silentium processing was cancelled.")

        dst_image.from_numpy(np.asarray(result, dtype=np.float32))
        dst_image.set_metadata("afternight.extension", "veralux_silentium")
        dst_image.set_metadata("veralux.tool", "Silentium")
        dst_image.set_metadata("veralux.upstream_version", core.UPSTREAM_VERSION)
        dst_image.set_metadata("veralux.attribution", silentium_ui.ATTRIBUTION_TEXT)
        progress.set_value(100.0)
        afternight.log_info("VeraLux Silentium applied successfully.", component=self.component)

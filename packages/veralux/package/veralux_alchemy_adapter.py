# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Alchemy by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Alchemy.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Alchemy."""

from __future__ import annotations

import numpy as np

import afternight
from afternight import ui

import veralux_alchemy_core as core
import veralux_alchemy_ui as alchemy_ui


class VeraLuxAlchemyExtension(ui.ProcessWindow):
    component = "extension.veralux_alchemy"

    def get_params(self):
        return alchemy_ui.parameter_defs()

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
        progress.set_text("Applying VeraLux Alchemy...")
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Alchemy processing was cancelled.")

        source = np.asarray(src_image.to_numpy())
        result = core.process_narrowband(
            source,
            bg_align=bool(params.get("bg_align", True)),
            auto_fit=bool(params.get("auto_fit", True)),
            boost=float(params.get("boost", 1.0)),
            mix_r=float(params.get("mix_r", 0.0)),
            mix_g=float(params.get("mix_g", 1.0)),
            mix_b=float(params.get("mix_b", 1.0)),
            quantum_unmix=bool(params.get("quantum_unmix", False)),
            sensor_profile=str(params.get("sensor_profile", "Generic OSC")),
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Alchemy processing was cancelled.")

        dst_image.from_numpy(np.asarray(result, dtype=np.float32))
        dst_image.set_metadata("afternight.extension", "veralux_alchemy")
        dst_image.set_metadata("veralux.tool", "Alchemy")
        dst_image.set_metadata("veralux.upstream_version", core.UPSTREAM_VERSION)
        dst_image.set_metadata("veralux.attribution", alchemy_ui.ATTRIBUTION_TEXT)
        progress.set_value(100.0)
        afternight.log_info("VeraLux Alchemy applied successfully.", component=self.component)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Revela by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Revela.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Revela."""

from __future__ import annotations

import numpy as np

from afternight import ui

import veralux_revela_core as core
import veralux_revela_ui as revela_ui
import veralux_sdk as sdk


class VeraLuxRevelaExtension(ui.ProcessWindow):
    component = "extension.veralux_revela"

    def get_params(self):
        return revela_ui.parameter_defs()

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
        progress.set_text("Applying VeraLux Revela...")
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Revela processing was cancelled.")

        source = sdk.read_image(src_image)
        result = core.process_structure(
            source,
            texture_amt=float(params.get("texture", 0.0)),
            structure_amt=float(params.get("structure", 0.0)),
            shadow_auth=float(params.get("shadow_authority", 33.0)),
            protect_stars=bool(params.get("protect_stars", True)),
            return_mask=bool(params.get("show_mask", False)),
        )

        if bool(params.get("show_mask", False)) and source.ndim == 3:
            if source.shape[-1] == 1:
                result = result[..., np.newaxis]
            elif source.shape[-1] >= 3:
                result = np.repeat(result[..., np.newaxis], source.shape[-1], axis=2)

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Revela processing was cancelled.")

        sdk.write_image(dst_image, result)
        sdk.stamp_result(
            dst_image,
            extension_id="veralux_revela",
            tool_name="Revela",
            upstream_version=core.UPSTREAM_VERSION,
            attribution=revela_ui.ATTRIBUTION_TEXT,
        )
        progress.set_value(100.0)
        sdk.log_info("VeraLux Revela applied successfully.", component=self.component)

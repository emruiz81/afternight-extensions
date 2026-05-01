# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux StarComposer by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_StarComposer.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux StarComposer."""

from __future__ import annotations

from afternight import ui

import veralux_starcomposer_core as core
import veralux_starcomposer_ui as starcomposer_ui
import veralux_sdk as sdk


class VeraLuxStarComposerExtension(ui.ProcessWindow):
    component = "extension.veralux_starcomposer"

    def get_params(self):
        return starcomposer_ui.parameter_defs()

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
        progress.set_text("Applying VeraLux StarComposer...")
        if progress.is_cancelled():
            raise RuntimeError("VeraLux StarComposer processing was cancelled.")

        source = sdk.read_image(src_image)
        result = core.process_star_mask(
            source,
            log_d=float(params.get("log_d", 1.0)),
            profile_hardness=float(params.get("profile_hardness", 50.0)),
            color_grip=float(params.get("color_grip", 0.5)),
            shadow_convergence=float(params.get("shadow_convergence", 0.0)),
            star_reduction=float(params.get("star_reduction", 0.0)),
            optical_healing=float(params.get("optical_healing", 0.0)),
            large_structure_rejection=float(params.get("large_structure_rejection", 0.0)),
            working_space=str(params.get("working_space", core.DEFAULT_PROFILE)),
            use_adaptive_anchor=bool(params.get("use_adaptive_anchor", True)),
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux StarComposer processing was cancelled.")

        sdk.write_image(dst_image, result)
        sdk.stamp_result(
            dst_image,
            extension_id="veralux_starcomposer",
            tool_name="StarComposer",
            upstream_version=core.UPSTREAM_VERSION,
            attribution=starcomposer_ui.ATTRIBUTION_TEXT,
        )
        progress.set_value(100.0)
        sdk.log_info("VeraLux StarComposer applied successfully.", component=self.component)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Revela) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Revela.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Revela."""

from __future__ import annotations

import numpy as np

from afternight import ui

import veralux_revela_core as core
import veralux_revela_ui as revela_ui
import veralux_sdk as sdk


class VeraLuxRevelaExtension(ui.RTPreviewProcess):
    component = "extension.veralux_revela"

    def get_params(self):
        return revela_ui.parameter_defs()

    def on_process_launch(self):
        sdk.log_launch_banner(
            "Revela",
            "Photometric Local Contrast & Texture Engine",
            version=core.UPSTREAM_VERSION,
            component=self.component,
            include_contact=False,
        )
        sdk.log_info("VeraLux Revela: Input cache is managed by AfterNight image handles.", component=self.component)

    def _process(self, src_image, dst_image, params, progress, *, preview=False):
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Revela processing was cancelled.")

        sdk.warn_quality_fallbacks_once(
            self,
            core.quality_fallback_messages(),
            component=self.component,
        )

        if not preview:
            sdk.log_info(
                "VeraLux Revela: Processing "
                f"texture={float(params.get('texture', 0.0)):.2f}, "
                f"structure={float(params.get('structure', 0.0)):.2f}, "
                f"Shadow Authority={float(params.get('shadow_authority', 33.0)):.1f}.",
                component=self.component,
            )

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
        if not preview:
            sdk.stamp_result(
                dst_image,
                extension_id="veralux_revela",
                tool_name="Revela",
                upstream_version=core.UPSTREAM_VERSION,
                attribution=revela_ui.ATTRIBUTION_TEXT,
            )
            sdk.mark_result_nonlinear(dst_image, "veralux-revela")
        progress.set_value(100.0)

    def execute_preview(
        self,
        target,
        src_image,
        preview_image,
        params,
        progress,
        masks=None,
        weights=None,
    ):
        del target, masks, weights
        progress.set_text("Rendering VeraLux Revela preview...")
        self._process(src_image, preview_image, params, progress, preview=True)

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
        self._process(src_image, dst_image, params, progress, preview=False)
        sdk.log_info("VeraLux Revela applied successfully.", component=self.component)

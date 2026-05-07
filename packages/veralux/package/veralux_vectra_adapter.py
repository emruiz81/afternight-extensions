# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Vectra) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Vectra.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Vectra."""

from __future__ import annotations

from afternight import ui

import veralux_vectra_core as core
import veralux_vectra_ui as vectra_ui
import veralux_sdk as sdk


class VeraLuxVectraExtension(ui.RTPreviewProcess):
    component = "extension.veralux_vectra"

    def get_params(self):
        return vectra_ui.parameter_defs()

    @staticmethod
    def _saturation_from_ui(params, key):
        return float(params.get(key, 0.0)) / 100.0

    def _process(self, src_image, dst_image, params, progress, *, preview=False):
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Vectra processing was cancelled.")

        sdk.warn_quality_fallbacks_once(
            self,
            core.quality_fallback_messages(),
            component=self.component,
        )

        vectors = {
            "R": (float(params.get("red_hue", 0.0)), self._saturation_from_ui(params, "red_saturation")),
            "G": (float(params.get("green_hue", 0.0)), self._saturation_from_ui(params, "green_saturation")),
            "B": (float(params.get("blue_hue", 0.0)), self._saturation_from_ui(params, "blue_saturation")),
            "Y": (float(params.get("yellow_hue", 0.0)), self._saturation_from_ui(params, "yellow_saturation")),
            "C": (float(params.get("cyan_hue", 0.0)), self._saturation_from_ui(params, "cyan_saturation")),
            "M": (float(params.get("magenta_hue", 0.0)), self._saturation_from_ui(params, "magenta_saturation")),
        }

        source = sdk.read_image(src_image)
        result = core.process_vectors(
            source,
            vectors,
            shadow_auth=float(params.get("shadow_authority", 0.0)),
            protect_stars=bool(params.get("protect_stars", True)),
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Vectra processing was cancelled.")

        sdk.write_image(dst_image, result)
        if not preview:
            sdk.stamp_result(
                dst_image,
                extension_id="veralux_vectra",
                tool_name="Vectra",
                upstream_version=core.UPSTREAM_VERSION,
                attribution=vectra_ui.ATTRIBUTION_TEXT,
            )
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
        progress.set_text("Rendering VeraLux Vectra preview...")
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
        progress.set_text("Applying VeraLux Vectra...")
        self._process(src_image, dst_image, params, progress, preview=False)
        sdk.log_info("VeraLux Vectra applied successfully.", component=self.component)

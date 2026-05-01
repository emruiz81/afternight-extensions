# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Curves by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Curves.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Curves."""

from __future__ import annotations

from afternight import ui

import veralux_curves_core as core
import veralux_curves_ui as curves_ui
import veralux_sdk as sdk


class VeraLuxCurvesExtension(ui.ProcessWindow):
    component = "extension.veralux_curves"

    def get_params(self):
        return curves_ui.parameter_defs()

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
        progress.set_text("Applying VeraLux Curves...")
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Curves processing was cancelled.")

        points = core.curve_from_controls(
            black_point=float(params.get("black_point", 0.0)),
            shadow_lift=float(params.get("shadow_lift", 0.0)),
            midtone_input=float(params.get("midtone_input", 0.5)),
            midtone_output=float(params.get("midtone_output", 0.5)),
            highlight_compression=float(params.get("highlight_compression", 0.0)),
            white_point=float(params.get("white_point", 1.0)),
        )
        operation = core.curve_operation(
            str(params.get("domain", "RGB/K")),
            points=points,
            lum_range_enabled=bool(params.get("range_enabled", False)),
            lum_min=float(params.get("lum_min", 0.0)),
            lum_max=float(params.get("lum_max", 1.0)),
            feather=float(params.get("feather", 0.25)),
        )

        source = sdk.read_image(src_image)
        result = core.process_curves(source, [operation])

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Curves processing was cancelled.")

        sdk.write_image(dst_image, result)
        sdk.stamp_result(
            dst_image,
            extension_id="veralux_curves",
            tool_name="Curves",
            upstream_version=core.UPSTREAM_VERSION,
            attribution=curves_ui.ATTRIBUTION_TEXT,
        )
        progress.set_value(100.0)
        sdk.log_info("VeraLux Curves applied successfully.", component=self.component)

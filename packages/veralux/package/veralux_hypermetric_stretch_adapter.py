# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux HyperMetric Stretch by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_HyperMetric_Stretch.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux HyperMetric Stretch."""

from __future__ import annotations

import numpy as np

import afternight
from afternight import ui

import veralux_hypermetric_stretch_core as core
import veralux_hypermetric_stretch_ui as hms_ui


class VeraLuxHyperMetricStretchExtension(ui.ProcessWindow):
    component = "extension.veralux_hypermetric_stretch"

    def get_params(self):
        return hms_ui.parameter_defs()

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
        progress.set_text("Applying VeraLux HyperMetric Stretch...")
        if progress.is_cancelled():
            raise RuntimeError("VeraLux HyperMetric Stretch processing was cancelled.")

        source = np.asarray(src_image.to_numpy())
        result = core.process_hypermetric_stretch(
            source,
            log_d=float(params.get("log_d", 2.0)),
            protect_b=float(params.get("protect_b", 6.0)),
            convergence_power=float(params.get("convergence_power", 3.5)),
            working_space=str(params.get("working_space", core.DEFAULT_PROFILE)),
            processing_mode=str(params.get("processing_mode", "ready_to_use")),
            target_bg=float(params.get("target_bg", 0.20)),
            color_strategy=float(params.get("color_strategy", 0.0)),
            color_grip=float(params.get("color_grip", 1.0)),
            shadow_convergence=float(params.get("shadow_convergence", 0.0)),
            linear_expansion=float(params.get("linear_expansion", 0.0)),
            use_adaptive_anchor=bool(params.get("use_adaptive_anchor", True)),
            auto_log_d=bool(params.get("auto_log_d", False)),
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux HyperMetric Stretch processing was cancelled.")

        dst_image.from_numpy(np.asarray(result, dtype=np.float32))
        dst_image.set_metadata("afternight.extension", "veralux_hypermetric_stretch")
        dst_image.set_metadata("veralux.tool", "HyperMetric Stretch")
        dst_image.set_metadata("veralux.upstream_version", core.UPSTREAM_VERSION)
        dst_image.set_metadata("veralux.attribution", hms_ui.ATTRIBUTION_TEXT)
        progress.set_value(100.0)
        afternight.log_info(
            "VeraLux HyperMetric Stretch applied successfully.",
            component=self.component,
        )

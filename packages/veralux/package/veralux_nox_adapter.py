# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Nox by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Nox.py
# Upstream baseline: a9fb2c7f505c488f5cfef5b7fa5022097551e06e; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Nox."""

from __future__ import annotations

import numpy as np

import afternight
from afternight import ui

import veralux_nox_core as core
import veralux_nox_ui as nox_ui


class VeraLuxNoxExtension(ui.ProcessWindow):
    component = "extension.veralux_nox"

    def get_params(self):
        return nox_ui.parameter_defs()

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
        del target, weights, output_masks
        progress.set_text("Applying VeraLux Nox...")
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Nox processing was cancelled.")

        source = np.asarray(src_image.to_numpy())
        auto_tune = bool(params.get("auto_tune", True))
        if auto_tune:
            stiffness, rejection_power = core.calculate_heuristics(source)
        else:
            stiffness = float(params.get("stiffness", 2.0))
            rejection_power = float(params.get("rejection_power", 55.0))

        user_mask = None
        if masks:
            first_mask = masks[0]
            if hasattr(first_mask, "to_numpy"):
                user_mask = np.asarray(first_mask.to_numpy(), dtype=np.float32)
            else:
                user_mask = np.asarray(first_mask, dtype=np.float32)

        result = core.process_gradient_reduction(
            source,
            stiffness=stiffness,
            rejection_power=rejection_power,
            correction_strength=float(params.get("correction_strength", 1.0)),
            model_grid=float(params.get("model_grid", 64.0)),
            auto_mask=bool(params.get("auto_mask", True)),
            user_mask=user_mask,
            return_model=bool(params.get("output_model", False)),
        )
        if isinstance(result, tuple):
            result = result[1]

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Nox processing was cancelled.")

        dst_image.from_numpy(np.asarray(result, dtype=np.float32))
        dst_image.set_metadata("afternight.extension", "veralux_nox")
        dst_image.set_metadata("veralux.tool", "Nox")
        dst_image.set_metadata("veralux.upstream_version", core.UPSTREAM_VERSION)
        dst_image.set_metadata("veralux.attribution", nox_ui.ATTRIBUTION_TEXT)
        dst_image.set_metadata("veralux.nox.stiffness", f"{stiffness:.3f}")
        dst_image.set_metadata("veralux.nox.rejection_power", f"{rejection_power:.3f}")
        progress.set_value(100.0)
        afternight.log_info("VeraLux Nox applied successfully.", component=self.component)

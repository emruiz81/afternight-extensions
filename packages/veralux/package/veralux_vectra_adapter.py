# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 AfterNight contributors
# Ported from VeraLux Vectra by Riccardo Paterniti.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Vectra.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Vectra."""

from __future__ import annotations

import numpy as np

import afternight
from afternight import ui

import veralux_vectra_core as core
import veralux_vectra_ui as vectra_ui


class VeraLuxVectraExtension(ui.ProcessWindow):
    component = "extension.veralux_vectra"

    def get_params(self):
        return vectra_ui.parameter_defs()

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
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Vectra processing was cancelled.")

        vectors = {
            "R": (float(params.get("red_hue", 0.0)), float(params.get("red_saturation", 0.0))),
            "G": (float(params.get("green_hue", 0.0)), float(params.get("green_saturation", 0.0))),
            "B": (float(params.get("blue_hue", 0.0)), float(params.get("blue_saturation", 0.0))),
            "C": (float(params.get("cyan_hue", 0.0)), float(params.get("cyan_saturation", 0.0))),
            "M": (float(params.get("magenta_hue", 0.0)), float(params.get("magenta_saturation", 0.0))),
            "Y": (float(params.get("yellow_hue", 0.0)), float(params.get("yellow_saturation", 0.0))),
        }

        source = np.asarray(src_image.to_numpy())
        result = core.process_vectors(
            source,
            vectors,
            shadow_auth=float(params.get("shadow_authority", 0.0)),
            protect_stars=bool(params.get("protect_stars", True)),
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Vectra processing was cancelled.")

        dst_image.from_numpy(np.asarray(result, dtype=np.float32))
        dst_image.set_metadata("afternight.extension", "veralux_vectra")
        dst_image.set_metadata("veralux.tool", "Vectra")
        dst_image.set_metadata("veralux.upstream_version", core.UPSTREAM_VERSION)
        dst_image.set_metadata("veralux.attribution", vectra_ui.ATTRIBUTION_TEXT)
        progress.set_value(100.0)
        afternight.log_info("VeraLux Vectra applied successfully.", component=self.component)

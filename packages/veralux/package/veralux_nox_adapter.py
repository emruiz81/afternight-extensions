# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Nox) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Nox.py
# Upstream baseline: a9fb2c7f505c488f5cfef5b7fa5022097551e06e; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Nox."""

from __future__ import annotations

import numpy as np

from afternight import ui

import veralux_nox_core as core
import veralux_nox_ui as nox_ui
import veralux_sdk as sdk


class VeraLuxNoxExtension(ui.RTPreviewProcess):
    component = "extension.veralux_nox"

    def __init__(self, context):
        super().__init__(context)
        self._preview_refresh_requested = False
        self._preview_cache = {}
        self._preview_cache_source_shape = None

    def get_params(self):
        return nox_ui.parameter_defs()

    def _star_physics(self, src_image, params):
        if not bool(params.get("auto_mask", True)):
            return None, 4.0

        try:
            return sdk.star_mask_and_median_fwhm_from_find_stars(
                src_image,
                max_stars=8192,
                radius_scale=1.8,
                min_radius=3.0,
                max_radius=24.0,
            )
        except Exception as exc:
            sdk.log_warning(
                f"VeraLux Nox PSF auto-masking unavailable: {exc}",
                component=self.component,
            )
            return None, 4.0

    def _process(self, src_image, params, progress, masks=None):
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Nox processing was cancelled.")

        source = sdk.read_image(src_image)
        user_mask = sdk.first_mask_array(masks) if bool(params.get("use_manual_mask", False)) else None
        star_mask, fwhm_val = self._star_physics(src_image, params)

        result, model = core.process_gradient_reduction(
            source,
            stiffness=float(params.get("stiffness", 2.0)),
            rejection_power=float(params.get("rejection_power", 50.0)),
            auto_mask=bool(params.get("auto_mask", True)),
            user_mask=user_mask,
            star_mask=star_mask,
            fwhm_val=fwhm_val,
            return_model=True,
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Nox processing was cancelled.")
        return result, model, star_mask, fwhm_val

    def handle_param_action(self, action_id, target, src_image, params):
        del target
        if action_id == "refresh_preview":
            self._preview_refresh_requested = True
            return {}

        if action_id == "auto_calculate":
            source = sdk.read_image(src_image)
            stiffness, rejection_power = core.calculate_heuristics(source)
            stiffness_slider = round(float(stiffness), 1)
            rejection_slider = int(round(float(rejection_power)))
            sdk.log_info(
                "VeraLux Nox auto-calculate: "
                f"stiffness={stiffness_slider:.1f}, "
                f"signal_rejection={rejection_slider}%",
                component=self.component,
            )
            return {
                "stiffness": stiffness_slider,
                "rejection_power": rejection_slider,
            }

        return {}

    def _reset_preview_cache(self, source_shape):
        self._preview_cache_source_shape = source_shape
        self._preview_cache = {}

    def _cached_preview_for_mode(self, source, user_mask, preview_mode):
        if preview_mode == nox_ui.PREVIEW_BACKGROUND:
            model = self._preview_cache.get(nox_ui.PREVIEW_BACKGROUND)
            if model is not None:
                return np.clip(model, 0.0, 1.0).astype(np.float32, copy=False)
            return np.zeros_like(np.asarray(source), dtype=np.float32)

        if preview_mode == nox_ui.PREVIEW_PROTECTION_MASK:
            return core.source_with_protection_overlay(source, user_mask)

        return self._preview_cache.get(
            nox_ui.PREVIEW_CORRECTED,
            np.asarray(source, dtype=np.float32),
        )

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
        del target, weights
        source = sdk.read_image(src_image)
        source_shape = tuple(np.asarray(source).shape)
        if source_shape != self._preview_cache_source_shape:
            self._reset_preview_cache(source_shape)

        preview_mode = str(params.get("preview_mode", nox_ui.PREVIEW_CORRECTED))
        user_mask = sdk.first_mask_array(masks) if bool(params.get("use_manual_mask", False)) else None
        if not self._preview_refresh_requested:
            output = self._cached_preview_for_mode(source, user_mask, preview_mode)
            sdk.write_image(preview_image, output)
            progress.set_value(100.0)
            return

        progress.set_text("Rendering VeraLux Nox preview...")
        result, model, _star_mask, _fwhm_val = self._process(src_image, params, progress, masks=masks)
        self._preview_cache = {
            nox_ui.PREVIEW_CORRECTED: np.asarray(result, dtype=np.float32),
            nox_ui.PREVIEW_BACKGROUND: np.asarray(model, dtype=np.float32),
        }
        self._preview_refresh_requested = False

        output = self._cached_preview_for_mode(source, user_mask, preview_mode)
        sdk.write_image(preview_image, output)
        progress.set_value(100.0)

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
        result, model, _star_mask, fwhm_val = self._process(src_image, params, progress, masks=masks)

        sdk.write_image(dst_image, result)
        sdk.stamp_result(
            dst_image,
            extension_id="veralux_nox",
            tool_name="Nox",
            upstream_version=core.UPSTREAM_VERSION,
            attribution=nox_ui.ATTRIBUTION_TEXT,
            extra_metadata={
                "veralux.nox.stiffness": f"{float(params.get('stiffness', 2.0)):.3f}",
                "veralux.nox.rejection_power": f"{float(params.get('rejection_power', 50.0)):.3f}",
                "veralux.nox.fwhm": f"{float(fwhm_val):.3f}",
            },
        )

        if bool(params.get("save_gradient_model", False)):
            ui.open_image(
                np.clip(model, 0.0, 1.0).astype(np.float32, copy=False),
                title="VeraLux Nox Gradient Model",
                metadata={
                    "afternight.extension": "veralux_nox",
                    "veralux.tool": "Nox Gradient Model",
                    "veralux.upstream_version": core.UPSTREAM_VERSION,
                    "veralux.attribution": nox_ui.ATTRIBUTION_TEXT,
                },
            )

        progress.set_value(100.0)
        sdk.log_info("VeraLux Nox applied successfully.", component=self.component)

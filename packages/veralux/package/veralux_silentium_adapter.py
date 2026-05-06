# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Silentium) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Silentium.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Silentium."""

from __future__ import annotations

from afternight import ui

import veralux_silentium_core as core
import veralux_silentium_ui as silentium_ui
import veralux_sdk as sdk


class VeraLuxSilentiumExtension(ui.RTPreviewProcess):
    component = "extension.veralux_silentium"

    def get_params(self):
        return silentium_ui.parameter_defs()

    def _star_protection(self, src_image, params):
        if not bool(params.get("use_stars", True)):
            return None, None

        try:
            star_mask, fwhm_map = sdk.star_mask_and_fwhm_map_from_find_stars(
                src_image,
                radius_scale=1.8,
                min_radius=3.0,
                max_radius=24.0,
            )
        except Exception as exc:
            sdk.log_warning(
                f"VeraLux Silentium star protection unavailable: {exc}",
                component=self.component,
            )
            return None, None

        if bool(params.get("auto_starless", True)) and float(star_mask.max(initial=0.0)) < 0.1:
            return None, None

        # The upstream wavelet core looks for Siril's list.lst in the process
        # cwd, so the visible script path commonly falls back to a uniform
        # FWHM map while still applying the star mask. Threading AfterNight's
        # local FWHM map through here can collapse the threshold to near zero
        # across most preview ROIs, making Silentium look like a no-op.
        del fwhm_map
        return star_mask, None

    def _process(self, src_image, dst_image, params, progress, *, preview=False):
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Silentium processing was cancelled.")

        source = sdk.read_image(src_image)
        star_mask, fwhm_map = self._star_protection(src_image, params)
        result = core.process_noise_reduction(
            source,
            intensity=float(params.get("noise_intensity", 0.5)),
            detail_guard=float(params.get("detail_guard", 50.0)),
            adaptive_noise=bool(params.get("adaptive_noise", True)),
            enable_chroma=bool(params.get("enable_chroma", True)),
            chroma_strength=float(params.get("chroma_strength", 30.0)),
            shadow_smoothness=float(params.get("shadow_smoothness", 10.0)),
            use_stars=bool(params.get("use_stars", True)),
            auto_starless=bool(params.get("auto_starless", True)),
            star_mask=star_mask,
            fwhm_map=fwhm_map,
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Silentium processing was cancelled.")

        sdk.write_image(dst_image, result)
        if not preview:
            sdk.stamp_result(
                dst_image,
                extension_id="veralux_silentium",
                tool_name="Silentium",
                upstream_version=core.UPSTREAM_VERSION,
                attribution=silentium_ui.ATTRIBUTION_TEXT,
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
        progress.set_text("Rendering VeraLux Silentium preview...")
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
        progress.set_text("Applying VeraLux Silentium...")
        self._process(src_image, dst_image, params, progress, preview=False)
        sdk.log_info("VeraLux Silentium applied successfully.", component=self.component)

# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux StarComposer) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_StarComposer.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux StarComposer."""

from __future__ import annotations

import afternight
import numpy as np
from afternight import ui

import veralux_starcomposer_core as core
import veralux_starcomposer_ui as starcomposer_ui
import veralux_sdk as sdk


class VeraLuxStarComposerExtension(ui.RTPreviewProcess):
    component = "extension.veralux_starcomposer"
    PREVIEW_PROXY_MAX_DIMENSION = 3200

    def __init__(self, context):
        super().__init__(context)
        self._preview_stars_proxy_cache_key = None
        self._preview_stars_proxy_cache = None
        self._preview_shaped_stars_cache_key = None
        self._preview_shaped_stars_cache = None

    def get_params(self):
        return starcomposer_ui.parameter_defs()

    def on_process_launch(self):
        sdk.log_launch_banner(
            "StarComposer",
            "High-Fidelity Star Reconstruction Engine",
            version=core.UPSTREAM_VERSION,
            component=self.component,
        )
        sdk.log_info("VeraLux StarComposer: Select starless base and stars view to begin.", component=self.component)

    def _stars_image_handle(self, params):
        injected_image = params.get("_stars_image")
        if injected_image is None:
            injected_image = params.get("stars_image")
        if injected_image is not None:
            return injected_image

        stars_view = str(params.get("stars_view") or params.get("stars_view_name") or "").strip()
        if not stars_view:
            raise RuntimeError("VeraLux StarComposer requires a Stars (linear) selection.")

        stars_snapshot = afternight.snapshot_view(stars_view)
        stars_image = stars_snapshot.source_image
        if stars_image is None:
            raise RuntimeError(f"VeraLux StarComposer could not read Stars (linear) view: {stars_view}")
        return stars_image

    @staticmethod
    def _array_hw(array):
        data = np.asarray(array)
        if data.ndim < 2:
            return 0, 0
        if data.ndim == 3 and data.shape[0] in (1, 3) and data.shape[-1] not in (1, 3, 4):
            return int(data.shape[1]), int(data.shape[2])
        return int(data.shape[0]), int(data.shape[1])

    @staticmethod
    def _crop_array(array, x, y, width, height):
        data = np.asarray(array)
        if data.ndim == 2:
            return data[y : y + height, x : x + width]
        if data.ndim == 3 and data.shape[0] in (1, 3) and data.shape[-1] not in (1, 3, 4):
            return data[:, y : y + height, x : x + width]
        return data[y : y + height, x : x + width, ...]

    def _align_stars_to_starless_preview(self, stars, starless, src_image, *, preview):
        if not preview:
            return stars

        target_h, target_w = self._array_hw(starless)
        stars_h, stars_w = self._array_hw(stars)
        if target_h <= 0 or target_w <= 0 or (stars_h, stars_w) == (target_h, target_w):
            return stars

        properties = {}
        try:
            properties = dict(getattr(src_image, "properties", {}) or {})
        except Exception:
            properties = {}

        required_keys = ("offset_x", "offset_y", "source_width", "source_height")
        if all(key in properties for key in required_keys):
            offset_x = int(properties["offset_x"])
            offset_y = int(properties["offset_y"])
            source_w = int(properties["source_width"])
            source_h = int(properties["source_height"])
            if (
                (stars_h, stars_w) == (source_h, source_w)
                and offset_x >= 0
                and offset_y >= 0
                and offset_x + target_w <= stars_w
                and offset_y + target_h <= stars_h
            ):
                return self._crop_array(stars, offset_x, offset_y, target_w, target_h)

        return stars

    @staticmethod
    def _resize_array(array, out_h, out_w, *, downsample):
        data = np.asarray(array)
        in_h, in_w = VeraLuxStarComposerExtension._array_hw(data)
        out_h = int(max(1, out_h))
        out_w = int(max(1, out_w))
        if in_h == out_h and in_w == out_w:
            return data

        if core.cv2 is not None:
            interpolation = core.cv2.INTER_AREA if downsample else core.cv2.INTER_LINEAR
            if data.ndim == 2:
                return core.cv2.resize(data.astype(np.float32, copy=False), (out_w, out_h), interpolation=interpolation)
            if data.ndim == 3 and data.shape[0] in (1, 3) and data.shape[-1] not in (1, 3, 4):
                hwc = np.moveaxis(data.astype(np.float32, copy=False), 0, -1)
                resized = core.cv2.resize(hwc, (out_w, out_h), interpolation=interpolation)
                if resized.ndim == 2:
                    resized = resized[..., np.newaxis]
                return np.moveaxis(resized, -1, 0).astype(np.float32, copy=False)
            resized = core.cv2.resize(data.astype(np.float32, copy=False), (out_w, out_h), interpolation=interpolation)
            if data.ndim == 3 and resized.ndim == 2:
                resized = resized[..., np.newaxis]
            return resized.astype(np.float32, copy=False)

        y_idx = np.linspace(0, max(in_h - 1, 0), out_h).astype(np.intp)
        x_idx = np.linspace(0, max(in_w - 1, 0), out_w).astype(np.intp)
        if data.ndim == 2:
            return data[y_idx][:, x_idx].astype(np.float32, copy=False)
        if data.ndim == 3 and data.shape[0] in (1, 3) and data.shape[-1] not in (1, 3, 4):
            return data[:, y_idx, :][:, :, x_idx].astype(np.float32, copy=False)
        return data[y_idx][:, x_idx, ...].astype(np.float32, copy=False)

    def _preview_proxy_shape(self, array):
        height, width = self._array_hw(array)
        if height <= 0 or width <= 0:
            return height, width
        max_dimension = int(max(1, self.PREVIEW_PROXY_MAX_DIMENSION))
        largest = max(height, width)
        if largest <= max_dimension:
            return height, width
        scale = max_dimension / float(largest)
        return max(1, int(height * scale)), max(1, int(width * scale))

    @staticmethod
    def _stars_view_cache_name(params):
        if params.get("_stars_image") is not None or params.get("stars_image") is not None:
            return None
        stars_view = str(params.get("stars_view") or params.get("stars_view_name") or "").strip()
        return stars_view or None

    def _read_stars_for_preview(self, params, starless, src_image, proxy_shape):
        target_h, target_w = self._array_hw(starless)
        proxy_h, proxy_w = proxy_shape
        stars_view = self._stars_view_cache_name(params)
        cache_key = (stars_view, target_h, target_w, proxy_h, proxy_w) if stars_view else None
        if cache_key is not None and cache_key == self._preview_stars_proxy_cache_key:
            return self._preview_stars_proxy_cache

        stars = sdk.read_image(self._stars_image_handle(params))
        stars = self._align_stars_to_starless_preview(stars, starless, src_image, preview=True)
        stars_proxy = self._resize_array(
            stars,
            proxy_h,
            proxy_w,
            downsample=max(self._array_hw(stars)) > max(proxy_h, proxy_w),
        )
        stars_proxy = np.asarray(stars_proxy, dtype=np.float32)

        if cache_key is not None:
            self._preview_stars_proxy_cache_key = cache_key
            self._preview_stars_proxy_cache = stars_proxy.copy()
            self._preview_shaped_stars_cache_key = None
            self._preview_shaped_stars_cache = None
            return self._preview_stars_proxy_cache

        return stars_proxy

    @staticmethod
    def _shape_params_key(params, proxy_shape):
        return (
            tuple(proxy_shape),
            float(params.get("log_d", 1.0)),
            float(params.get("profile_hardness", 50.0)),
            float(params.get("color_grip", 0.5)),
            float(params.get("shadow_convergence", 0.0)),
            float(params.get("star_reduction", 0.0)),
            float(params.get("optical_healing", 0.0)),
            float(params.get("large_structure_rejection", 0.0)),
            str(params.get("working_space", core.DEFAULT_PROFILE)),
            bool(params.get("use_adaptive_anchor", True)),
        )

    def _shape_stars(self, stars, params, *, cache_key=None):
        if cache_key is not None and cache_key == self._preview_shaped_stars_cache_key:
            return self._preview_shaped_stars_cache

        if cache_key is None:
            sdk.log_info(
                "VeraLux StarComposer: Shaping stars with hybrid reconstruction engine.", component=self.component
            )
        shaped_stars = core.process_star_mask(
            stars,
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

        if cache_key is not None:
            self._preview_shaped_stars_cache_key = cache_key
            self._preview_shaped_stars_cache = np.asarray(shaped_stars, dtype=np.float32).copy()
            return self._preview_shaped_stars_cache

        return shaped_stars

    def _preview_result(self, starless, params, src_image):
        target_h, target_w = self._array_hw(starless)
        proxy_shape = self._preview_proxy_shape(starless)
        proxy_h, proxy_w = proxy_shape
        starless_proxy = self._resize_array(
            starless,
            proxy_h,
            proxy_w,
            downsample=max(target_h, target_w) > max(proxy_h, proxy_w),
        )
        stars_proxy = self._read_stars_for_preview(params, starless, src_image, proxy_shape)
        stars_cache_key = self._preview_stars_proxy_cache_key if self._stars_view_cache_name(params) else None
        shaped_cache_key = (stars_cache_key, self._shape_params_key(params, proxy_shape)) if stars_cache_key else None
        shaped_stars = self._shape_stars(
            stars_proxy,
            params,
            cache_key=shaped_cache_key,
        )
        blend_mode = core.normalize_blend_mode(params.get("blend_mode", "screen"))
        proxy_result = core.compose_with_starless(starless_proxy, shaped_stars, blend_mode=blend_mode)
        if (proxy_h, proxy_w) == (target_h, target_w):
            return proxy_result
        return self._resize_array(proxy_result, target_h, target_w, downsample=False)

    def _process(self, src_image, dst_image, params, progress, *, preview=False):
        if progress.is_cancelled():
            raise RuntimeError("VeraLux StarComposer processing was cancelled.")

        sdk.warn_quality_fallbacks_once(
            self,
            core.quality_fallback_messages(),
            component=self.component,
        )

        starless = sdk.read_image(src_image)
        if preview:
            result = self._preview_result(starless, params, src_image)
        else:
            stars = sdk.read_image(self._stars_image_handle(params))
            shaped_stars = self._shape_stars(stars, params)
            blend_mode = core.normalize_blend_mode(params.get("blend_mode", "screen"))
            sdk.log_info(f"VeraLux StarComposer: Compositing stars ({blend_mode}).", component=self.component)
            result = core.compose_with_starless(starless, shaped_stars, blend_mode=blend_mode)

        if progress.is_cancelled():
            raise RuntimeError("VeraLux StarComposer processing was cancelled.")

        sdk.write_image(dst_image, result)
        if not preview:
            sdk.stamp_result(
                dst_image,
                extension_id="veralux_starcomposer",
                tool_name="StarComposer",
                upstream_version=core.UPSTREAM_VERSION,
                attribution=starcomposer_ui.ATTRIBUTION_TEXT,
                extra_metadata={
                    "veralux.starcomposer.stars_view": params.get("stars_view", ""),
                    "veralux.starcomposer.blend_mode": blend_mode,
                },
            )
            sdk.mark_result_nonlinear(dst_image, "veralux-starcomposer")
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
        progress.set_text("Rendering VeraLux StarComposer preview...")
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
        progress.set_text("Applying VeraLux StarComposer...")
        self._process(src_image, dst_image, params, progress, preview=False)
        sdk.log_info("VeraLux StarComposer applied successfully.", component=self.component)

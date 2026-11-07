# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 Adrian Knagg-Baugh
# Copyright (c) 2025 Dave Lindner
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (Narrowband Continuum Subtraction for Siril) by Adrian Knagg-Baugh and Dave Lindner.
# AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/ContinuumSubtraction.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""AfterNight entry point and SDK adapters for Continuum Subtraction and Continuum Blend."""

from __future__ import annotations

import zlib

import numpy as np

import afternight
from afternight import ui

import continuum_subtraction_core as core
import continuum_subtraction_ui as cs_ui


EXTENSION_ID = "continuum_subtraction"


def _content_key(array):
    data = np.ascontiguousarray(array)
    return tuple(data.shape), data.dtype.str, zlib.crc32(data)


def _plane(array, what):
    """Return a mono image as (H, W), accepting (H, W, 1) and (1, H, W)."""

    data = np.asarray(array)
    if data.ndim == 3 and 1 in (data.shape[0], data.shape[-1]):
        data = data.reshape(data.shape[1:] if data.shape[0] == 1 else data.shape[:2])
    if data.ndim != 2:
        raise ValueError(f"Continuum Subtraction needs a mono {what}; it has shape {np.asarray(array).shape}.")
    return data


def _view_image(params, injected_key, view_key, label):
    injected = params.get(injected_key)
    if injected is not None:
        return injected
    view_name = str(params.get(view_key) or "").strip()
    if not view_name:
        raise RuntimeError(f"Select the {label} image.")
    image = afternight.snapshot_view(view_name).source_image
    if image is None:
        raise RuntimeError(f"Could not read the {label} view: {view_name}")
    return image


def _write_image(image_handle, result, dtype, shape):
    """Write ``result`` in the target's sample type and array shape; integer targets are clipped to their range."""

    data = np.asarray(result, dtype=np.float32).reshape(shape)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        data = np.nan_to_num(data, nan=0.0, posinf=1.0, neginf=0.0)
        # Truncate as AfterNight's native float-to-integer converters do.
        data = (np.clip(data, 0.0, 1.0) * float(info.max)).astype(dtype)
    image_handle.from_numpy(data)


def _region_mask(params, masks, shape):
    """Return the painted estimation region as a boolean array, or None to use the whole image."""

    if not bool(params.get("use_region_mask", False)) or not masks:
        return None
    first = next(iter(masks.values()), None) if isinstance(masks, dict) else masks[0]
    if first is None:
        return None
    mask = np.asarray(first.to_numpy() if hasattr(first, "to_numpy") else first, dtype=np.float32)
    mask = mask.reshape(mask.shape[:2]) if mask.ndim == 3 else mask
    if mask.shape != tuple(shape):
        raise ValueError(
            f"The estimation region is {mask.shape[1]}x{mask.shape[0]}; the image is {shape[1]}x{shape[0]}."
        )
    region = mask > 0.5
    return region if np.any(region) else None


class ContinuumSubtractionExtension(ui.RTPreviewProcess):
    component = "extension.continuum_subtraction"

    def __init__(self, context):
        super().__init__(context)
        self._estimate_key = None
        self._estimate = None

    def get_params(self):
        return cs_ui.subtraction_parameter_defs()

    def on_process_launch(self):
        afternight.log_info(
            f"Continuum Subtraction {core.UPSTREAM_VERSION}: AfterNight port of the Siril script by Adrian "
            "Knagg-Baugh and Dave Lindner. Select a linear continuum image registered to the emission image.",
            component=self.component,
        )

    def _estimate_c(self, emission, continuum, region, progress):
        key = (_content_key(emission), _content_key(continuum), None if region is None else _content_key(region))
        if key == self._estimate_key:
            return self._estimate, False

        def report(text, fraction):
            progress.set_text(text)
            progress.set_value(90.0 * float(fraction))

        c, details = core.compute_c(emission, continuum, selection=region, progress=report)
        self._estimate_key, self._estimate = key, (c, details, 0 if region is None else int(np.count_nonzero(region)))
        return self._estimate, True

    def _process(self, src_image, dst_image, params, progress, masks, *, preview):
        source = np.asarray(src_image.to_numpy())
        emission = core.normalize_input(_plane(source, "emission-line image"))
        continuum = core.normalize_input(
            _plane(_view_image(params, "_continuum_image", "continuum_view", "continuum").to_numpy(), "continuum image")
        )
        if continuum.shape != emission.shape:
            raise ValueError("The continuum image must have the emission image's size.")
        if progress.is_cancelled():
            raise RuntimeError("Continuum Subtraction was cancelled.")

        if bool(params.get("estimate_c", True)):
            region = _region_mask(params, masks, emission.shape)
            (c, details, region_pixels), fresh = self._estimate_c(emission, continuum, region, progress)
            if fresh or not preview:
                where = f"the painted region ({region_pixels} pixels)" if region_pixels else "the whole image"
                afternight.log_info(
                    f"Continuum Subtraction: estimated c = {c:.4f} over {where}.", component=self.component
                )
                if not region_pixels:
                    afternight.log_warning(
                        "Continuum Subtraction: no estimation region painted; the whole image usually gives a poorer "
                        "estimate than a generous region around the subject.",
                        component=self.component,
                    )
                if details["fit_failed"]:
                    afternight.log_warning(
                        "Continuum Subtraction: the smooth-V fit failed; c is the best factor of the fine scan.",
                        component=self.component,
                    )
        else:
            c = float(np.clip(float(params.get("c", core.DEFAULT_C)), 0.0, 1.0))

        if progress.is_cancelled():
            raise RuntimeError("Continuum Subtraction was cancelled.")
        result = core.subtract_continuum(emission, continuum, c)
        _write_image(dst_image, result, source.dtype, source.shape)
        if not preview:
            dst_image.set_metadata("afternight.extension", EXTENSION_ID)
            dst_image.set_metadata(f"{EXTENSION_ID}.upstream_version", core.UPSTREAM_VERSION)
            dst_image.set_metadata(f"{EXTENSION_ID}.c", f"{c:.6f}")
            dst_image.set_metadata(f"{EXTENSION_ID}.continuum_view", str(params.get("continuum_view") or ""))
            dst_image.set_metadata(f"{EXTENSION_ID}.attribution", cs_ui.ATTRIBUTION_TEXT)
        progress.set_value(100.0)
        return c

    def execute_preview(self, target, src_image, preview_image, params, progress, masks=None, weights=None):
        del target, weights
        progress.set_text("Rendering Continuum Subtraction preview...")
        self._process(src_image, preview_image, params, progress, masks, preview=True)

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
        progress.set_text("Applying Continuum Subtraction...")
        c = self._process(src_image, dst_image, params, progress, masks, preview=False)
        afternight.log_info(f"Continuum Subtraction applied with c = {c:.4f}.", component=self.component)


def blend_weights(params):
    preset = str(params.get("preset", "Ha"))
    if preset in core.LINE_WEIGHTS:
        return core.LINE_WEIGHTS[preset]
    if preset != "Custom":
        raise ValueError(f"Continuum Blend: unknown channel preset {preset!r}.")
    return tuple(
        float(np.clip(float(params.get(f"{name}_weight", default)), 0.0, 100.0)) / 100.0
        for name, default in (("red", 100.0), ("green", 0.0), ("blue", 0.0))
    )


class ContinuumBlendExtension(ui.RTPreviewProcess):
    component = "extension.continuum_subtraction_blend"

    def get_params(self):
        return cs_ui.blend_parameter_defs()

    def _process(self, src_image, dst_image, params, progress, *, preview):
        source = np.asarray(src_image.to_numpy())
        planar = source.ndim == 3 and source.shape[0] == 3 and source.shape[-1] != 3
        rgb = core.normalize_input(np.moveaxis(source, 0, -1) if planar else source)
        if rgb.ndim != 3 or rgb.shape[-1] != 3:
            raise ValueError(f"Continuum Blend needs an RGB image; it has shape {source.shape}.")
        line = core.normalize_input(
            _plane(
                _view_image(params, "_line_image", "line_view", "continuum-subtracted").to_numpy(),
                "continuum-subtracted image",
            )
        )
        if line.shape != rgb.shape[:2]:
            raise ValueError("The continuum-subtracted image must have the RGB image's size.")
        if progress.is_cancelled():
            raise RuntimeError("Continuum Blend was cancelled.")

        strength = float(np.clip(float(params.get("strength", core.DEFAULT_STRENGTH)), 0.0, 12.0))
        weights = blend_weights(params)
        result = core.blend_into_rgb(rgb, line, strength, weights)
        _write_image(dst_image, np.moveaxis(result, -1, 0) if planar else result, source.dtype, source.shape)
        if not preview:
            dst_image.set_metadata("afternight.extension", EXTENSION_ID)
            dst_image.set_metadata(f"{EXTENSION_ID}.upstream_version", core.UPSTREAM_VERSION)
            dst_image.set_metadata(f"{EXTENSION_ID}.blend_strength", f"{strength:.4f}")
            dst_image.set_metadata(f"{EXTENSION_ID}.blend_weights", ",".join(f"{weight:.4f}" for weight in weights))
            dst_image.set_metadata(f"{EXTENSION_ID}.attribution", cs_ui.ATTRIBUTION_TEXT)
        progress.set_value(100.0)
        return strength, weights

    def execute_preview(self, target, src_image, preview_image, params, progress, masks=None, weights=None):
        del target, masks, weights
        progress.set_text("Rendering Continuum Blend preview...")
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
        progress.set_text("Applying Continuum Blend...")
        strength, channel_weights = self._process(src_image, dst_image, params, progress, preview=False)
        afternight.log_info(
            f"Continuum Blend applied (strength {strength:.2f}, weights "
            + ", ".join(f"{weight:.2f}" for weight in channel_weights)
            + ").",
            component=self.component,
        )


__all__ = ["ContinuumBlendExtension", "ContinuumSubtractionExtension"]

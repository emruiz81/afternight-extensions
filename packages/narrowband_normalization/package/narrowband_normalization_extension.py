# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Yannick Dutertre
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (NarrowbandNormalization for Siril) by Yannick Dutertre. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/NarrowbandNormalization.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""AfterNight entry point and SDK adapter for Narrowband Normalization."""

from __future__ import annotations

import numpy as np

import afternight
from afternight import ui

import narrowband_normalization_core as core
import narrowband_normalization_ui as nbn_ui


EXTENSION_ID = "narrowband_normalization"


def settings_from_params(params):
    """Return the core's parameter dict from native window values, falling back to the upstream defaults."""

    source = dict(params or {})
    settings = {}
    for key, default in core.DEFAULT_PARAMS.items():
        value = source.get(key, default)
        settings[key] = str(value) if isinstance(default, str) else float(value)

    if settings["palette"] not in core.PALETTES:
        raise ValueError(f"Narrowband Normalization: unknown palette {settings['palette']!r}.")
    if settings["lightness"] not in core.LIGHTNESS_SOURCES:
        raise ValueError(f"Narrowband Normalization: unknown lightness source {settings['lightness']!r}.")
    if settings["blend_mode"] not in core.BLEND_MODES:
        raise ValueError(f"Narrowband Normalization: unknown blend mode {settings['blend_mode']!r}.")
    return settings


def to_hwc(data):
    """Return ``(array, layout)`` with the array channel-last; ``layout`` is ``hwc`` or ``chw``."""

    data = np.asarray(data)
    if data.ndim == 3 and data.shape[0] == 3 and data.shape[-1] != 3:
        return np.moveaxis(data, 0, -1), "chw"
    return data, "hwc"


def from_hwc(data, layout):
    return np.moveaxis(data, -1, 0) if layout == "chw" else data


def write_image(image_handle, result, dtype):
    """Write a float result in [0, 1] into ``image_handle`` in the source's sample type."""

    data = np.asarray(result, dtype=np.float32)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        data = np.nan_to_num(data, nan=0.0, posinf=1.0, neginf=0.0)
        # Truncate as AfterNight's native float-to-integer converters do.
        data = (np.clip(data, 0.0, 1.0) * float(info.max)).astype(dtype)
    image_handle.from_numpy(data)


class NarrowbandNormalizationExtension(ui.RTPreviewProcess):
    component = "extension.narrowband_normalization"

    def get_params(self):
        return nbn_ui.parameter_defs()

    def on_process_launch(self):
        afternight.log_info(
            f"Narrowband Normalization {core.UPSTREAM_VERSION}: AfterNight port of Yannick Dutertre's Siril script, "
            "built on Bill Blanshan and Mike Cranfield's NarrowbandNormalization.",
            component=self.component,
        )

    def _process(self, src_image, dst_image, params, progress, *, preview):
        settings = settings_from_params(params)
        source = np.asarray(src_image.to_numpy())
        data, layout = to_hwc(source)
        if data.ndim != 3 or data.shape[-1] != 3:
            raise ValueError(
                "Narrowband Normalization needs a 3-channel RGB image whose channels hold the palette's lines in "
                f"its letter order; the image has shape {source.shape}."
            )
        if progress.is_cancelled():
            raise RuntimeError("Narrowband Normalization was cancelled.")

        result = core.process_image(core.normalize_input(data), settings)

        if progress.is_cancelled():
            raise RuntimeError("Narrowband Normalization was cancelled.")
        write_image(dst_image, from_hwc(result, layout), source.dtype)
        if not preview:
            dst_image.set_metadata("afternight.extension", EXTENSION_ID)
            dst_image.set_metadata(f"{EXTENSION_ID}.upstream_version", core.UPSTREAM_VERSION)
            dst_image.set_metadata(f"{EXTENSION_ID}.palette", settings["palette"])
            dst_image.set_metadata(f"{EXTENSION_ID}.attribution", nbn_ui.ATTRIBUTION_TEXT)
            dst_image.set_metadata("ANSTVER", "1")
            dst_image.set_metadata("ANLIN", "nonlinear")
            dst_image.set_metadata("ANBASIS", "display-rgb")
            dst_image.set_metadata("ANASRC", "process")
            dst_image.set_metadata("ANOP", "narrowband-normalization")
        progress.set_value(100.0)
        return settings

    def execute_preview(self, target, src_image, preview_image, params, progress, masks=None, weights=None):
        del target, masks, weights
        progress.set_text("Rendering Narrowband Normalization preview...")
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
        progress.set_text("Applying Narrowband Normalization...")
        settings = self._process(src_image, dst_image, params, progress, preview=False)
        afternight.log_info(
            f"Narrowband Normalization applied (palette={settings['palette']}, lightness={settings['lightness']}).",
            component=self.component,
        )


__all__ = ["NarrowbandNormalizationExtension"]

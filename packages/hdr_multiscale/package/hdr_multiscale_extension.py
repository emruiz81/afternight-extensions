# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Cyril Richard
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (HDR Multiscale for Siril) by Franklin Marek, adapted for Siril by Cyril Richard.
# AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/c7a185babc74141bfb082059166ede79e4b80ee2/processing/HDR_multiscale.py
# Upstream baseline: c7a185babc74141bfb082059166ede79e4b80ee2; local port notes: see UPSTREAM.md.

"""AfterNight entry point and SDK adapter for HDR Multiscale."""

from __future__ import annotations

import numpy as np

import afternight
from afternight import ui

import hdr_multiscale_core as core
import hdr_multiscale_ui as hdr_ui


EXTENSION_ID = "hdr_multiscale"


def settings_from_params(params):
    """Return ``(n_scales, compression, mask_gamma, show_mask)`` from native window values, clamped to their ranges."""

    source = dict(params or {})
    n_scales = int(np.clip(int(source.get("n_scales", core.DEFAULT_SCALES)), 2, 10))
    compression = float(np.clip(float(source.get("compression", core.DEFAULT_COMPRESSION)), 0.1, 5.0))
    mask_gamma = float(np.clip(float(source.get("mask_gamma", core.DEFAULT_MASK_GAMMA)), 0.1, 10.0))
    return n_scales, compression, mask_gamma, bool(source.get("show_mask", False))


def to_channel_last(data):
    """Return ``(array, layout)`` with a channel-first RGB array moved channel-last; ``layout`` is ``chw`` or ``hwc``."""

    data = np.asarray(data)
    if data.ndim == 3 and data.shape[0] in (1, 3) and data.shape[-1] not in (1, 3):
        return np.moveaxis(data, 0, -1), "chw"
    return data, "hwc"


def from_channel_last(data, layout):
    return np.moveaxis(data, -1, 0) if layout == "chw" and data.ndim == 3 else data


def write_image(image_handle, result, dtype):
    """Write a float result in [0, 1] into ``image_handle`` in the source's sample type."""

    data = np.asarray(result, dtype=np.float32)
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        data = np.nan_to_num(data, nan=0.0, posinf=1.0, neginf=0.0)
        # Truncate as AfterNight's native float-to-integer converters do.
        data = (np.clip(data, 0.0, 1.0) * float(info.max)).astype(dtype)
    image_handle.from_numpy(data)


class HdrMultiscaleExtension(ui.RTPreviewProcess):
    component = "extension.hdr_multiscale"

    def get_params(self):
        return hdr_ui.parameter_defs()

    def on_process_launch(self):
        afternight.log_info(
            f"HDR Multiscale {core.UPSTREAM_VERSION}: AfterNight port of the Siril script by Franklin Marek and "
            "Cyril Richard. Use it on a stretched image.",
            component=self.component,
        )

    def _process(self, src_image, dst_image, params, progress, *, preview):
        n_scales, compression, mask_gamma, show_mask = settings_from_params(params)
        source = np.asarray(src_image.to_numpy())
        data, layout = to_channel_last(source)
        if progress.is_cancelled():
            raise RuntimeError("HDR Multiscale was cancelled.")

        result = core.apply_hdr_multiscale(
            core.normalize_input(data),
            n_scales=n_scales,
            compression_factor=compression,
            mask_gamma=mask_gamma,
            return_mask=show_mask,
        )

        if progress.is_cancelled():
            raise RuntimeError("HDR Multiscale was cancelled.")
        write_image(dst_image, from_channel_last(result, layout), source.dtype)
        if not preview:
            dst_image.set_metadata("afternight.extension", EXTENSION_ID)
            dst_image.set_metadata(f"{EXTENSION_ID}.upstream_version", core.UPSTREAM_VERSION)
            dst_image.set_metadata(f"{EXTENSION_ID}.attribution", hdr_ui.ATTRIBUTION_TEXT)
            dst_image.set_metadata("ANSTVER", "1")
            dst_image.set_metadata("ANLIN", "nonlinear")
            dst_image.set_metadata(
                "ANBASIS", "monochrome" if result.ndim == 2 or result.shape[-1] == 1 else "display-rgb"
            )
            dst_image.set_metadata("ANASRC", "process")
            dst_image.set_metadata("ANOP", "hdr-multiscale")
        progress.set_value(100.0)
        return n_scales, compression, mask_gamma

    def execute_preview(self, target, src_image, preview_image, params, progress, masks=None, weights=None):
        del target, masks, weights
        progress.set_text("Rendering HDR Multiscale preview...")
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
        progress.set_text("Applying HDR Multiscale...")
        n_scales, compression, mask_gamma = self._process(src_image, dst_image, params, progress, preview=False)
        afternight.log_info(
            f"HDR Multiscale applied ({n_scales} scales, compression {compression:.2f}, mask gamma {mask_gamma:.1f}).",
            component=self.component,
        )


__all__ = ["HdrMultiscaleExtension"]

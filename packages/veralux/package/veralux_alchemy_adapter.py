# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Alchemy) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Alchemy.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Alchemy."""

from __future__ import annotations

from afternight import ui

import veralux_alchemy_core as core
import veralux_alchemy_ui as alchemy_ui
import veralux_sdk as sdk


class VeraLuxAlchemyExtension(ui.RTPreviewProcess):
    component = "extension.veralux_alchemy"

    def get_params(self):
        return alchemy_ui.parameter_defs()

    def on_process_launch(self):
        sdk.log_launch_banner(
            "Alchemy",
            "Linear-Phase Narrowband Normalization & Mixing",
            version=core.UPSTREAM_VERSION,
            component=self.component,
            include_contact=False,
        )
        sdk.log_info("VeraLux Alchemy: Input cache is managed by AfterNight image handles.", component=self.component)

    def handle_param_action(self, action_id, target, src_image, params):
        del target, src_image, params
        preset = core.PALETTE_PRESETS.get(str(action_id))
        return dict(preset) if preset is not None else {}

    def _process(self, src_image, dst_image, params, progress, *, preview=False):
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Alchemy processing was cancelled.")

        if not preview:
            mode = "Quantum Unmix" if bool(params.get("quantum_unmix", False)) else "linear channel mix"
            sdk.log_info(
                "VeraLux Alchemy: Processing "
                f"{mode} (profile={params.get('sensor_profile', 'Generic OSC')}, "
                f"boost={float(params.get('boost', 1.0)):.2f}).",
                component=self.component,
            )

        source = sdk.read_image(src_image)
        result = core.process_narrowband(
            source,
            bg_align=bool(params.get("bg_align", True)),
            auto_fit=bool(params.get("auto_fit", True)),
            boost=float(params.get("boost", 1.0)),
            mix_r=float(params.get("mix_r", 0.0)),
            mix_g=float(params.get("mix_g", 1.0)),
            mix_b=float(params.get("mix_b", 1.0)),
            quantum_unmix=bool(params.get("quantum_unmix", False)),
            sensor_profile=str(params.get("sensor_profile", "Generic OSC")),
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Alchemy processing was cancelled.")

        output = core.preview_autostretch(result) if preview else result
        sdk.write_image(dst_image, output)
        if not preview:
            sdk.stamp_result(
                dst_image,
                extension_id="veralux_alchemy",
                tool_name="Alchemy",
                upstream_version=core.UPSTREAM_VERSION,
                attribution=alchemy_ui.ATTRIBUTION_TEXT,
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
        progress.set_text("Rendering VeraLux Alchemy preview...")
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
        progress.set_text("Applying VeraLux Alchemy...")
        self._process(src_image, dst_image, params, progress, preview=False)
        sdk.log_info("VeraLux Alchemy applied successfully.", component=self.component)

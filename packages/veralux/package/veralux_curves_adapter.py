# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 Riccardo Paterniti
# AfterNight port Copyright (c) 2026 Ezequiel Ruiz
# Original work (VeraLux Curves) by Riccardo Paterniti. AfterNight port by Ezequiel Ruiz.
# Original source: https://gitlab.com/free-astro/siril-scripts/-/blob/4ce0af52926e071caef55f4d17ac17ae8d8b4aac/VeraLux/VeraLux_Curves.py
# Upstream baseline: 4ce0af52926e071caef55f4d17ac17ae8d8b4aac; local port notes: see UPSTREAM.md.

"""AfterNight SDK adapter for VeraLux Curves."""

from __future__ import annotations

from afternight import ui

import veralux_curves_core as core
import veralux_curves_ui as curves_ui
import veralux_sdk as sdk


def _clamp_unit(value):
    return max(0.0, min(1.0, float(value)))


def _points_from_curve_editor(raw_points):
    if not isinstance(raw_points, (list, tuple)):
        return None

    points = []
    for raw_point in raw_points:
        if isinstance(raw_point, dict):
            x = raw_point.get("x", raw_point.get("input"))
            y = raw_point.get("y", raw_point.get("output"))
        elif isinstance(raw_point, (list, tuple)) and len(raw_point) >= 2:
            x, y = raw_point[0], raw_point[1]
        else:
            continue

        try:
            points.append((_clamp_unit(x), _clamp_unit(y)))
        except (TypeError, ValueError):
            continue

    if len(points) < 2:
        return None

    points.sort(key=lambda point: point[0])
    cleaned = []
    for x, y in points:
        if cleaned and x <= cleaned[-1][0] + 1.0e-6:
            cleaned[-1] = (cleaned[-1][0], y)
        else:
            cleaned.append((x, y))

    if not cleaned:
        return None
    if cleaned[0][0] > 1.0e-6:
        cleaned.insert(0, (0.0, 0.0))
    else:
        cleaned[0] = (0.0, cleaned[0][1])
    if cleaned[-1][0] < 1.0 - 1.0e-6:
        cleaned.append((1.0, 1.0))
    else:
        cleaned[-1] = (1.0, cleaned[-1][1])

    return cleaned if len(cleaned) >= 2 else None


class VeraLuxCurvesExtension(ui.RTPreviewProcess):
    component = "extension.veralux_curves"

    def get_params(self):
        return curves_ui.parameter_defs()

    def on_process_launch(self):
        sdk.log_launch_banner(
            "Curves",
            "Spline-Based Photometric Sculpting Engine",
            version=core.UPSTREAM_VERSION,
            component=self.component,
        )
        sdk.log_info("VeraLux Curves: Akima point-curve editor initialized.", component=self.component)

    def _curve_points_from_params(self, params):
        points = _points_from_curve_editor(params.get("curve_points"))
        if points is not None:
            return points

        return core.curve_from_controls(
            black_point=float(params.get("black_point", 0.0)),
            shadow_lift=float(params.get("shadow_lift", 0.0)),
            midtone_input=float(params.get("midtone_input", 0.5)),
            midtone_output=float(params.get("midtone_output", 0.5)),
            highlight_compression=float(params.get("highlight_compression", 0.0)),
            white_point=float(params.get("white_point", 1.0)),
        )

    def _operation_from_params(self, params):
        operation = core.curve_operation(
            str(params.get("domain", "RGB/K")),
            points=self._curve_points_from_params(params),
            lum_range_enabled=bool(params.get("range_enabled", False)),
            lum_min=float(params.get("lum_min", 0.0)),
            lum_max=float(params.get("lum_max", 1.0)),
            feather=float(params.get("feather", 0.25)),
        )
        return operation

    def _process(self, src_image, dst_image, params, progress, *, preview=False):
        if progress.is_cancelled():
            raise RuntimeError("VeraLux Curves processing was cancelled.")

        operation = self._operation_from_params(params)
        if not preview:
            range_state = "range-limited" if operation.get("lum_range_enabled") else "global"
            sdk.log_info(
                f"VeraLux Curves: Applying {operation.get('domain', 'RGB/K')} curve ({range_state}).",
                component=self.component,
            )
        sdk.warn_quality_fallbacks_once(
            self,
            core.quality_fallback_messages([operation]),
            component=self.component,
        )

        source = sdk.read_image(src_image)
        result = core.process_curves(
            source,
            [operation],
            lut_size=4096 if preview else 65536,
        )

        if progress.is_cancelled():
            raise RuntimeError("VeraLux Curves processing was cancelled.")

        sdk.write_image(dst_image, result)
        if not preview:
            sdk.stamp_result(
                dst_image,
                extension_id="veralux_curves",
                tool_name="Curves",
                upstream_version=core.UPSTREAM_VERSION,
                attribution=curves_ui.ATTRIBUTION_TEXT,
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
        progress.set_text("Rendering VeraLux Curves preview...")
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
        progress.set_text("Applying VeraLux Curves...")
        self._process(src_image, dst_image, params, progress, preview=False)
        sdk.log_info("VeraLux Curves applied successfully.", component=self.component)

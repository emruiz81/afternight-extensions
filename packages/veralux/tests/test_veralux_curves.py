import json
import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

from afternight import ui  # noqa: E402
import veralux_curves_core as core  # noqa: E402
import veralux_curves_ui as curves_ui  # noqa: E402
from veralux_curves_adapter import VeraLuxCurvesExtension  # noqa: E402
from veralux_extension import VeraLuxCurvesExtension as SuiteCurvesExtension  # noqa: E402


class FakeImage:
    def __init__(self, array):
        self.array = np.asarray(array, dtype=np.float32)
        self.metadata = {}

    def to_numpy(self):
        return self.array

    def from_numpy(self, array):
        self.array = np.asarray(array, dtype=np.float32)

    def set_metadata(self, key, value):
        self.metadata[str(key)] = str(value)


class FakeProgress:
    def __init__(self):
        self.text = ""
        self.value = 0.0
        self.cancelled = False

    def set_text(self, text):
        self.text = str(text)

    def set_value(self, value):
        self.value = float(value)

    def is_cancelled(self):
        return self.cancelled


def synthetic_rgb_gradient(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    gradient = (x + y) / float((size - 1) * 2)
    red = np.clip(gradient * 0.95 + 0.05, 0.0, 1.0)
    green = np.clip(gradient * 0.75 + 0.12, 0.0, 1.0)
    blue = np.clip(gradient * 0.45 + 0.20, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


class VeraLuxCurvesCoreTests(unittest.TestCase):
    def test_generate_lut_respects_endpoints_and_is_clipped(self):
        points = [(0.18, -0.15), (0.50, 0.72), (0.90, 1.15)]

        lut = core.generate_lut(points, size=512)

        self.assertEqual(lut.shape, (512,))
        self.assertGreaterEqual(float(lut.min()), 0.0)
        self.assertLessEqual(float(lut.max()), 1.0)
        self.assertAlmostEqual(float(lut[0]), 0.0, places=5)
        self.assertGreater(float(lut[256]), 0.62)
        self.assertAlmostEqual(float(lut[-1]), 1.0, places=5)

    def test_rgb_curve_brightens_midtones_and_preserves_layout(self):
        source = synthetic_rgb_gradient()
        operation = core.curve_operation(
            "RGB/K",
            points=core.curve_from_controls(midtone_input=0.50, midtone_output=0.68),
        )

        result = core.process_curves(source, [operation])

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreater(float(np.mean(result)), float(np.mean(source)))
        self.assertLessEqual(float(result.max()), 1.0)

    def test_luminance_range_limits_curve_to_selected_zone(self):
        source = synthetic_rgb_gradient()
        operation = core.curve_operation(
            "RGB/K",
            points=core.curve_from_controls(midtone_input=0.50, midtone_output=0.80),
            lum_range_enabled=True,
            lum_min=0.38,
            lum_max=0.62,
            feather=0.0,
        )

        result = core.process_curves(source, [operation])

        luminance = np.mean(source, axis=2)
        shadow_delta = float(np.mean(np.abs(result[luminance < 0.30] - source[luminance < 0.30])))
        midtone_delta = float(
            np.mean(
                np.abs(
                    result[(luminance > 0.43) & (luminance < 0.57)] - source[(luminance > 0.43) & (luminance < 0.57)]
                )
            )
        )
        highlight_delta = float(np.mean(np.abs(result[luminance > 0.72] - source[luminance > 0.72])))
        self.assertLess(shadow_delta, 1e-6)
        self.assertGreater(midtone_delta, 2e-2)
        self.assertLess(highlight_delta, 1e-6)


class VeraLuxCurvesAdapterTests(unittest.TestCase):
    def test_process_is_rt_preview_based_with_native_preview_defaults(self):
        self.assertTrue(issubclass(VeraLuxCurvesExtension, ui.RTPreviewProcess))

        defs = curves_ui.parameter_defs()
        by_id = {param["id"]: param for param in defs if "id" in param}

        self.assertTrue(by_id["window_meta"]["sub_area"])
        self.assertIs(by_id["window_meta"]["sub_area_default_enabled"], False)
        self.assertEqual(by_id["window_meta"]["sub_area_label"], "Preview: Curves")
        self.assertEqual(by_id["window_meta"]["window_size"], [1260, 760])
        self.assertEqual(by_id["window_meta"]["controls_panel_width"], 520)
        self.assertIs(by_id["window_meta"]["preview_hq_default"], False)
        self.assertIs(by_id["window_meta"]["header_progress"], False)

        section_labels = [param["label"] for param in defs if param.get("type") == "section"]
        self.assertEqual(
            section_labels,
            [
                "Curve Domain",
                "Curve",
                "Luminance Range",
            ],
        )

        self.assertEqual(by_id["curve_points"]["type"], "curve_editor")
        self.assertEqual(by_id["curve_points"]["default"], [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0]])
        self.assertEqual(by_id["curve_points"]["interpolation"], "akima")
        self.assertIs(by_id["curve_points"]["histogram"], True)
        self.assertIs(by_id["curve_points"]["grid"], True)
        self.assertIs(by_id["curve_points"]["guide"], True)

        for removed_id in (
            "black_point",
            "shadow_lift",
            "midtone_input",
            "midtone_output",
            "highlight_compression",
            "white_point",
        ):
            self.assertNotIn(removed_id, by_id)

        for param_id in (
            "lum_min",
            "lum_max",
            "feather",
        ):
            self.assertIs(by_id[param_id]["tracking"], False, param_id)

        for param in defs:
            if param.get("type") in {"float", "double", "int", "bool", "choice", "string"}:
                self.assertTrue(param.get("tooltip"), param["id"])

    def test_manifest_declares_curves_preview_capabilities(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        self.assertEqual(
            processes["curves"]["capabilities"],
            {"execute": True, "preview": True, "keep_open": True},
        )

    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_rgb_gradient())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxCurvesExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "domain": "RGB/K",
                "curve_points": [[0.0, 0.0], [0.50, 0.70], [1.0, 1.0]],
                "range_enabled": False,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(dst.array)), float(np.mean(src.array)))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_curves")
        self.assertEqual(dst.metadata["veralux.tool"], "Curves")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_writes_preview_image_without_provenance_metadata(self):
        src = FakeImage(synthetic_rgb_gradient())
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxCurvesExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "domain": "RGB/K",
                "curve_points": [[0.0, 0.0], [0.50, 0.70], [1.0, 1.0]],
                "range_enabled": False,
            },
            progress,
        )

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(preview.array)), float(np.mean(src.array)))
        self.assertEqual(preview.metadata, {})
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_curves_process(self):
        self.assertIs(SuiteCurvesExtension, VeraLuxCurvesExtension)


if __name__ == "__main__":
    unittest.main()

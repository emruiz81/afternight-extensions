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
import veralux_hypermetric_stretch_core as core  # noqa: E402
import veralux_hypermetric_stretch_ui as hms_ui  # noqa: E402
from veralux_hypermetric_stretch_adapter import VeraLuxHyperMetricStretchExtension  # noqa: E402
from veralux_extension import VeraLuxHyperMetricStretchExtension as SuiteHmsExtension  # noqa: E402


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


def synthetic_linear_rgb(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    sky = 0.008 + (x / size) * 0.006
    nebula = 0.045 * np.exp(-(((x - 38.0) ** 2) + ((y - 30.0) ** 2)) / (2.0 * 13.0**2))
    star = 0.38 * np.exp(-(((x - 18.0) ** 2) + ((y - 20.0) ** 2)) / (2.0 * 1.6**2))
    red = np.clip(sky + nebula * 1.2 + star, 0.0, 1.0)
    green = np.clip(sky * 0.9 + nebula * 0.85 + star * 0.85, 0.0, 1.0)
    blue = np.clip(sky * 0.8 + nebula * 0.65 + star * 0.70, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


class VeraLuxHyperMetricStretchCoreTests(unittest.TestCase):
    def test_ready_to_use_stretches_linear_rgb_and_targets_background(self):
        source = synthetic_linear_rgb()

        result = core.process_hypermetric_stretch(
            source,
            auto_log_d=True,
            target_bg=0.20,
            processing_mode="ready_to_use",
            working_space=core.DEFAULT_PROFILE,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.median(result[..., 1])), 0.10)
        self.assertGreater(float(np.mean(np.abs(result - source))), 1e-3)

    def test_scientific_mode_preserves_layout_and_uses_linear_expansion(self):
        source = np.moveaxis(synthetic_linear_rgb(), -1, 0)

        result = core.process_hypermetric_stretch(
            source,
            log_d=2.4,
            protect_b=6.0,
            processing_mode="scientific",
            linear_expansion=0.45,
            color_grip=0.75,
            shadow_convergence=0.6,
            use_adaptive_anchor=False,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreater(float(np.mean(result)), float(np.mean(source)))
        self.assertGreater(core.LAST_LINEAR_EXPANSION_DIAG["high"], core.LAST_LINEAR_EXPANSION_DIAG["low"])

    def test_auto_log_d_solver_uses_ready_to_use_floating_sky_check(self):
        source = synthetic_linear_rgb()

        log_d = core.solve_log_d_for_image(
            source,
            target_median=0.20,
            protect_b=6.0,
            processing_mode="ready_to_use",
        )
        scientific_log_d = core.solve_log_d_for_image(
            source,
            target_median=0.20,
            protect_b=6.0,
            processing_mode="scientific",
        )

        self.assertAlmostEqual(log_d, 2.16357421875)
        self.assertAlmostEqual(scientific_log_d, 3.0650634765625)
        self.assertLess(log_d, scientific_log_d)

    def test_mono_input_is_supported(self):
        source = synthetic_linear_rgb()[..., 0]

        result = core.process_hypermetric_stretch(source, log_d=2.0, processing_mode="scientific")

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreater(float(np.mean(result)), float(np.mean(source)))


class VeraLuxHyperMetricStretchAdapterTests(unittest.TestCase):
    def test_process_is_rt_preview_based_with_native_preview_defaults(self):
        self.assertTrue(issubclass(VeraLuxHyperMetricStretchExtension, ui.RTPreviewProcess))

        defs = hms_ui.parameter_defs()
        by_id = {param["id"]: param for param in defs if "id" in param}

        self.assertTrue(by_id["window_meta"]["sub_area"])
        self.assertIs(by_id["window_meta"]["sub_area_default_enabled"], False)
        self.assertEqual(by_id["window_meta"]["sub_area_label"], "Preview: HyperMetric Stretch")
        self.assertEqual(by_id["window_meta"]["window_size"], [1260, 760])
        self.assertEqual(by_id["window_meta"]["controls_panel_width"], 520)
        self.assertIs(by_id["window_meta"]["preview_hq_default"], False)
        self.assertIs(by_id["window_meta"]["header_progress"], False)
        self.assertEqual(defs[1]["id"], "rt_histogram")
        self.assertEqual(by_id["rt_histogram"]["type"], "rt_histogram")
        self.assertEqual(by_id["rt_histogram"]["label"], "Histogram")
        self.assertEqual(by_id["rt_histogram"]["height"], 220)
        self.assertIs(by_id["rt_histogram"]["grid"], True)
        self.assertIs(by_id["rt_histogram"]["clipping_info"], True)
        self.assertIs(by_id["rt_histogram"]["histogram_areas"], False)
        self.assertIs(by_id["rt_histogram"]["local_channel_normalization"], False)
        self.assertEqual(by_id["auto_log_d"]["label"], "Auto-Calc Log D")
        self.assertEqual(by_id["auto_log_d"]["type"], "button")
        self.assertEqual(by_id["auto_log_d"]["button_role"], "primary")
        self.assertEqual(by_id["working_space"]["label"], "Sensor Profile")
        self.assertEqual(by_id["convergence_power"]["label"], "Convergence Power")
        self.assertEqual(
            by_id["color"]["enabled_when"],
            {"param": "processing_mode", "equals": "ready_to_use"},
        )
        self.assertEqual(
            by_id["scientific_color"]["enabled_when"],
            {"param": "processing_mode", "equals": "scientific"},
        )

        section_labels = [param["label"] for param in defs if param.get("type") == "section"]
        self.assertEqual(
            section_labels,
            [
                "Workflow",
                "HyperMetric Stretch",
                "Ready Mode Color",
                "Scientific Color Reconstruction",
            ],
        )

        for param_id in (
            "target_bg",
            "log_d",
            "protect_b",
            "convergence_power",
            "color_strategy",
            "linear_expansion",
            "color_grip",
            "shadow_convergence",
        ):
            self.assertIs(by_id[param_id]["tracking"], False, param_id)

        for param in defs:
            if param.get("type") in {"float", "double", "int", "bool", "choice", "string"}:
                self.assertTrue(param.get("tooltip"), param["id"])

        ui_strings = []
        for param in defs:
            for key in ("label", "text", "tooltip", "sub_area_label"):
                if key in param:
                    ui_strings.append(str(param[key]))
            for option in param.get("options", []):
                if option:
                    ui_strings.append(str(option[0]))

        self.assertNotIn("siril", "\n".join(ui_strings).lower())

    def test_manifest_declares_hms_preview_capabilities(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        self.assertEqual(
            processes["hypermetric_stretch"]["capabilities"],
            {"execute": True, "preview": True, "keep_open": True},
        )

    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_linear_rgb())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxHyperMetricStretchExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "processing_mode": "ready_to_use",
                "working_space": core.DEFAULT_PROFILE,
                "target_bg": 0.18,
                "log_d": 2.0,
                "protect_b": 6.0,
                "convergence_power": 3.5,
                "color_strategy": 0.2,
                "color_grip": 1.0,
                "shadow_convergence": 0.0,
                "linear_expansion": 0.0,
                "use_adaptive_anchor": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(dst.array - src.array))), 1e-3)
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_hypermetric_stretch")
        self.assertEqual(dst.metadata["veralux.tool"], "HyperMetric Stretch")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_writes_preview_image_without_provenance_metadata(self):
        src = FakeImage(synthetic_linear_rgb())
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxHyperMetricStretchExtension(None)

        params = {
            "processing_mode": "ready_to_use",
            "working_space": core.DEFAULT_PROFILE,
            "target_bg": 0.18,
            "log_d": 2.0,
            "protect_b": 6.0,
            "convergence_power": 3.5,
            "color_strategy": 0.2,
            "color_grip": 1.0,
            "shadow_convergence": 0.0,
            "linear_expansion": 0.0,
            "use_adaptive_anchor": True,
        }

        extension.execute_preview(None, src, preview, params, progress)

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(preview.array - src.array))), 1e-3)
        self.assertEqual(preview.metadata, {})
        self.assertEqual(progress.value, 100.0)

    def test_auto_log_d_param_action_returns_log_d_update(self):
        src = FakeImage(synthetic_linear_rgb())
        extension = VeraLuxHyperMetricStretchExtension(None)

        updates = extension.handle_param_action(
            "auto_log_d",
            None,
            src,
            {
                "working_space": core.DEFAULT_PROFILE,
                "target_bg": 0.20,
                "protect_b": 6.0,
                "use_adaptive_anchor": True,
            },
        )

        self.assertEqual(set(updates), {"log_d"})
        self.assertGreater(updates["log_d"], 0.0)
        self.assertLess(updates["log_d"], 7.0)
        self.assertEqual(extension.handle_param_action("unknown", None, src, {}), {})

    def test_suite_entry_point_exports_hms_process(self):
        self.assertIs(SuiteHmsExtension, VeraLuxHyperMetricStretchExtension)


if __name__ == "__main__":
    unittest.main()

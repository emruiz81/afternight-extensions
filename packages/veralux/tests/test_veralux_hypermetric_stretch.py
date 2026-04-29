import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_hypermetric_stretch_core as core  # noqa: E402
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

    def test_auto_log_d_solver_returns_useful_range(self):
        source = synthetic_linear_rgb()

        log_d = core.solve_log_d_for_image(source, target_median=0.20, protect_b=6.0)

        self.assertGreater(log_d, 0.0)
        self.assertLess(log_d, 7.0)

    def test_mono_input_is_supported(self):
        source = synthetic_linear_rgb()[..., 0]

        result = core.process_hypermetric_stretch(source, log_d=2.0, processing_mode="scientific")

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreater(float(np.mean(result)), float(np.mean(source)))


class VeraLuxHyperMetricStretchAdapterTests(unittest.TestCase):
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
                "auto_log_d": True,
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

    def test_suite_entry_point_exports_hms_process(self):
        self.assertIs(SuiteHmsExtension, VeraLuxHyperMetricStretchExtension)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_nox_core as core  # noqa: E402
from veralux_extension import VeraLuxNoxExtension as SuiteNoxExtension  # noqa: E402
from veralux_nox_adapter import VeraLuxNoxExtension  # noqa: E402


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


def synthetic_gradient_field(size=96, seed=9):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    x_norm = x / float(size - 1)
    y_norm = y / float(size - 1)
    gradient = 0.075 + 0.135 * x_norm + 0.050 * y_norm
    nebula = 0.26 * np.exp(-(((x - 54.0) ** 2) + ((y - 48.0) ** 2)) / (2.0 * 11.0**2))
    star = 0.68 * np.exp(-(((x - 24.0) ** 2) + ((y - 23.0) ** 2)) / (2.0 * 1.7**2))
    noise = rng.normal(0.0, 0.004, size=(size, size)).astype(np.float32)
    red = np.clip(gradient * 1.08 + nebula * 1.10 + star + noise, 0.0, 1.0)
    green = np.clip(gradient * 0.98 + nebula * 0.82 + star + noise * 0.8, 0.0, 1.0)
    blue = np.clip(gradient * 0.88 + nebula * 0.55 + star + noise * 0.6, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def corner_medians(image):
    luminance = core.luminance(np.asarray(image, dtype=np.float32))
    patches = [
        luminance[:18, :18],
        luminance[:18, -18:],
        luminance[-18:, :18],
        luminance[-18:, -18:],
    ]
    return np.asarray([np.median(patch) for patch in patches], dtype=np.float32)


class VeraLuxNoxCoreTests(unittest.TestCase):
    def test_gradient_reduction_flattens_background_and_preserves_signal(self):
        source = synthetic_gradient_field()

        result = core.process_gradient_reduction(
            source,
            stiffness=2.3,
            rejection_power=62.0,
            correction_strength=1.0,
            model_grid=36,
            auto_mask=True,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)

        source_spread = float(np.ptp(corner_medians(source)))
        result_spread = float(np.ptp(corner_medians(result)))
        self.assertLess(result_spread, source_spread * 0.42)

        before_contrast = float(source[48, 54, 0] - np.median(source[:18, :18, 0]))
        after_contrast = float(result[48, 54, 0] - np.median(result[:18, :18, 0]))
        self.assertGreater(after_contrast, before_contrast * 0.82)

    def test_auto_mask_reduces_background_model_pull_from_bright_signal(self):
        source = synthetic_gradient_field()

        open_model = core.estimate_background_model(
            source[..., 0],
            auto_mask=False,
            stiffness=1.8,
            model_grid=32,
        )
        protected_model = core.estimate_background_model(
            source[..., 0],
            auto_mask=True,
            stiffness=1.8,
            model_grid=32,
        )

        self.assertLess(float(protected_model[48, 54]), float(open_model[48, 54]) * 0.88)

    def test_auto_tune_returns_bounded_physics_parameters(self):
        stiffness, rejection_power = core.calculate_heuristics(synthetic_gradient_field())

        self.assertGreaterEqual(stiffness, 1.0)
        self.assertLessEqual(stiffness, 4.0)
        self.assertGreaterEqual(rejection_power, 25.0)
        self.assertLessEqual(rejection_power, 72.0)


class VeraLuxNoxAdapterTests(unittest.TestCase):
    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_gradient_field())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "auto_tune": False,
                "stiffness": 2.2,
                "rejection_power": 60.0,
                "correction_strength": 1.0,
                "model_grid": 36,
                "auto_mask": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertLess(float(np.ptp(corner_medians(dst.array))), float(np.ptp(corner_medians(src.array))))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_nox")
        self.assertEqual(dst.metadata["veralux.tool"], "Nox")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_nox_process(self):
        self.assertIs(SuiteNoxExtension, VeraLuxNoxExtension)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_silentium_core as core  # noqa: E402
from veralux_extension import VeraLuxSilentiumExtension as SuiteSilentiumExtension  # noqa: E402
from veralux_silentium_adapter import VeraLuxSilentiumExtension  # noqa: E402


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


def synthetic_noisy_linear_rgb(size=80, seed=42):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    background = 0.08 + 0.015 * (x / float(size - 1))
    nebula = 0.22 * np.exp(-(((x - 36.0) ** 2) + ((y - 42.0) ** 2)) / (2.0 * 13.0**2))
    star = 0.72 * np.exp(-(((x - 23.0) ** 2) + ((y - 20.0) ** 2)) / (2.0 * 1.8**2))
    luminance = np.clip(background + nebula + star, 0.0, 1.0)
    rgb = np.stack(
        [
            luminance * 1.04,
            luminance * 0.98,
            luminance * 0.88,
        ],
        axis=-1,
    )
    noise = rng.normal(0.0, 0.022, size=rgb.shape).astype(np.float32)
    chroma_noise = rng.normal(0.0, 0.016, size=rgb.shape).astype(np.float32)
    chroma_noise -= np.mean(chroma_noise, axis=-1, keepdims=True)
    return np.clip(rgb + noise + chroma_noise, 0.0, 1.0).astype(np.float32)


def robust_sigma(values):
    flat = np.asarray(values, dtype=np.float32).reshape(-1)
    median = float(np.median(flat))
    mad = float(np.median(np.abs(flat - median)))
    return 1.4826 * mad


def luminance(values):
    rgb = np.asarray(values, dtype=np.float32)
    return (0.2126 * rgb[..., 0]) + (0.7152 * rgb[..., 1]) + (0.0722 * rgb[..., 2])


class VeraLuxSilentiumCoreTests(unittest.TestCase):
    def test_noise_reduction_reduces_background_sigma_and_preserves_star_core(self):
        source = synthetic_noisy_linear_rgb()
        background = np.s_[0:18, 0:18, :]
        star_before = float(source[20, 23, 0])

        result = core.process_noise_reduction(
            source,
            intensity=72.0,
            detail_guard=70.0,
            adaptive_noise=True,
            enable_chroma=False,
            chroma_strength=0.0,
            shadow_smoothness=35.0,
            protect_highlights=True,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertLess(robust_sigma(luminance(result[background])), robust_sigma(luminance(source[background])) * 0.82)
        self.assertGreater(float(result[20, 23, 0]), star_before * 0.94)

    def test_chroma_noise_reduction_reduces_channel_spread(self):
        source = synthetic_noisy_linear_rgb(seed=7)

        result = core.process_noise_reduction(
            source,
            intensity=55.0,
            detail_guard=55.0,
            adaptive_noise=True,
            enable_chroma=True,
            chroma_strength=70.0,
            shadow_smoothness=10.0,
        )

        source_spread = np.std(source - np.mean(source, axis=-1, keepdims=True), axis=-1)
        result_spread = np.std(result - np.mean(result, axis=-1, keepdims=True), axis=-1)
        self.assertLess(float(np.median(result_spread)), float(np.median(source_spread)))

    def test_shadow_report_summarizes_noise_and_pedestal(self):
        source = synthetic_noisy_linear_rgb(seed=11)
        result = core.process_noise_reduction(source, intensity=60.0)

        report = core.calculate_shadow_report(source, result)

        self.assertIn("VERALUX SILENTIUM", report)
        self.assertIn("Noise Reduction", report)
        self.assertIn("Pedestal Shift", report)


class VeraLuxSilentiumAdapterTests(unittest.TestCase):
    def test_execute_writes_denoised_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_noisy_linear_rgb())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxSilentiumExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "noise_intensity": 65.0,
                "detail_guard": 60.0,
                "adaptive_noise": True,
                "enable_chroma": True,
                "chroma_strength": 50.0,
                "shadow_smoothness": 20.0,
                "protect_highlights": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertLess(robust_sigma(dst.array[:18, :18, :]), robust_sigma(src.array[:18, :18, :]))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_silentium")
        self.assertEqual(dst.metadata["veralux.tool"], "Silentium")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_silentium_process(self):
        self.assertIs(SuiteSilentiumExtension, VeraLuxSilentiumExtension)


if __name__ == "__main__":
    unittest.main()

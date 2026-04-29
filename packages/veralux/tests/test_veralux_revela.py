import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_revela_core as core  # noqa: E402
from veralux_revela_adapter import VeraLuxRevelaExtension  # noqa: E402


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


def synthetic_mono_image(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    gradient = 0.04 + (x / size) * 0.08
    nebula = 0.28 * np.exp(-(((x - 42.0) ** 2) + ((y - 32.0) ** 2)) / (2.0 * 12.0**2))
    texture = 0.018 * np.sin(x * 0.8) * np.cos(y * 0.55)
    star = 0.75 * np.exp(-(((x - 20.0) ** 2) + ((y - 22.0) ** 2)) / (2.0 * 1.5**2))
    return np.clip(gradient + nebula + texture + star, 0.0, 1.0).astype(np.float32)


class VeraLuxRevelaCoreTests(unittest.TestCase):
    def test_zero_strength_preserves_mono_input(self):
        source = synthetic_mono_image()

        result = core.process_structure(
            source,
            texture_amt=0.0,
            structure_amt=0.0,
            shadow_auth=33.0,
            protect_stars=True,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertLess(float(np.max(np.abs(result - source))), 2e-5)

    def test_enhancement_is_finite_clipped_and_changes_signal(self):
        source = synthetic_mono_image()

        result = core.process_structure(
            source,
            texture_amt=0.55,
            structure_amt=0.35,
            shadow_auth=33.0,
            protect_stars=True,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.mean(np.abs(result - source))), 1e-4)

    def test_mask_mode_returns_active_gate_with_star_core_protection(self):
        source = synthetic_mono_image()

        mask = core.process_structure(
            source,
            texture_amt=0.5,
            structure_amt=0.5,
            shadow_auth=33.0,
            protect_stars=True,
            return_mask=True,
        )

        self.assertEqual(mask.shape, source.shape)
        self.assertGreaterEqual(float(mask.min()), 0.0)
        self.assertLessEqual(float(mask.max()), 1.0)
        self.assertLess(float(mask[22, 20]), float(mask[32, 42]))


class VeraLuxRevelaAdapterTests(unittest.TestCase):
    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_mono_image())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxRevelaExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "texture": 0.4,
                "structure": 0.2,
                "shadow_authority": 33.0,
                "protect_stars": True,
                "show_mask": False,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(dst.array - src.array))), 1e-4)
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_revela")
        self.assertEqual(dst.metadata["veralux.tool"], "Revela")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)


if __name__ == "__main__":
    unittest.main()

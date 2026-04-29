import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_alchemy_core as core  # noqa: E402
from veralux_alchemy_adapter import VeraLuxAlchemyExtension  # noqa: E402
from veralux_extension import VeraLuxAlchemyExtension as SuiteAlchemyExtension  # noqa: E402
from veralux_extension import VeraLuxRevelaExtension as SuiteRevelaExtension  # noqa: E402


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


def synthetic_rgb_image(size=48):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    ha = 0.05 + 0.45 * np.exp(-(((x - 17.0) ** 2) + ((y - 25.0) ** 2)) / (2.0 * 8.0**2))
    oiii = 0.03 + 0.13 * np.exp(-(((x - 33.0) ** 2) + ((y - 20.0) ** 2)) / (2.0 * 10.0**2))
    signal = 0.01 * np.sin(x * 0.31) * np.cos(y * 0.29)
    red = np.clip(ha + 0.02 * oiii + signal, 0.0, 1.0)
    green = np.clip(0.08 * ha + 0.70 * oiii + signal * 0.5, 0.0, 1.0)
    blue = np.clip(0.02 * ha + 0.60 * oiii - signal * 0.25, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


class VeraLuxAlchemyCoreTests(unittest.TestCase):
    def test_default_hoo_mix_is_finite_clipped_and_rgb_shaped(self):
        source = synthetic_rgb_image()

        result = core.process_narrowband(source)

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.mean(np.abs(result - source))), 1e-4)

    def test_custom_palette_rebalances_channel_output(self):
        source = synthetic_rgb_image()

        hoo = core.process_narrowband(source, mix_r=0.0, mix_g=1.0, mix_b=1.0)
        pseudo_sho = core.process_narrowband(source, mix_r=0.0, mix_g=0.5, mix_b=1.0)

        self.assertGreater(float(np.mean(np.abs(hoo[..., 1] - pseudo_sho[..., 1]))), 1e-4)
        self.assertLess(float(np.mean(np.abs(hoo[..., 0] - pseudo_sho[..., 0]))), 1e-6)

    def test_quantum_unmixing_changes_dual_band_result(self):
        source = synthetic_rgb_image()

        classic = core.process_narrowband(source, quantum_unmix=False)
        unmixed = core.process_narrowband(
            source,
            quantum_unmix=True,
            sensor_profile="Sony IMX571",
        )

        self.assertEqual(unmixed.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(unmixed)))
        self.assertGreater(float(np.mean(np.abs(unmixed - classic))), 1e-4)

    def test_rejects_non_rgb_input(self):
        with self.assertRaises(ValueError):
            core.process_narrowband(np.zeros((16, 16), dtype=np.float32))


class VeraLuxAlchemyAdapterTests(unittest.TestCase):
    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_rgb_image())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxAlchemyExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "bg_align": True,
                "auto_fit": True,
                "boost": 1.15,
                "mix_r": 0.0,
                "mix_g": 0.8,
                "mix_b": 1.0,
                "quantum_unmix": True,
                "sensor_profile": "Sony IMX571",
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(dst.array - src.array))), 1e-4)
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_alchemy")
        self.assertEqual(dst.metadata["veralux.tool"], "Alchemy")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_all_processes(self):
        self.assertIs(SuiteAlchemyExtension, VeraLuxAlchemyExtension)
        self.assertEqual(SuiteRevelaExtension.__name__, "VeraLuxRevelaExtension")


if __name__ == "__main__":
    unittest.main()

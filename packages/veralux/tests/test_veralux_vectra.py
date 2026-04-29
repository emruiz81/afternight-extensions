import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_vectra_core as core  # noqa: E402
from veralux_extension import VeraLuxVectraExtension as SuiteVectraExtension  # noqa: E402
from veralux_vectra_adapter import VeraLuxVectraExtension  # noqa: E402


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


def synthetic_stretched_rgb(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    background = 0.16 + (x / size) * 0.02
    red_nebula = 0.55 * np.exp(-(((x - 22.0) ** 2) + ((y - 31.0) ** 2)) / (2.0 * 10.0**2))
    blue_nebula = 0.42 * np.exp(-(((x - 43.0) ** 2) + ((y - 25.0) ** 2)) / (2.0 * 9.0**2))
    star = 0.72 * np.exp(-(((x - 32.0) ** 2) + ((y - 17.0) ** 2)) / (2.0 * 1.4**2))
    red = np.clip(background + red_nebula + star, 0.0, 1.0)
    green = np.clip(background * 0.94 + red_nebula * 0.20 + blue_nebula * 0.36 + star, 0.0, 1.0)
    blue = np.clip(background * 0.91 + blue_nebula + star, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


class VeraLuxVectraCoreTests(unittest.TestCase):
    def test_zero_vectors_preserve_rgb_input(self):
        source = synthetic_stretched_rgb()

        result = core.process_vectors(source, core.default_vectors(), shadow_auth=0.0, protect_stars=True)

        self.assertEqual(result.shape, source.shape)
        self.assertLess(float(np.max(np.abs(result - source))), 2e-4)

    def test_targeted_vector_shift_changes_chroma_without_large_luminance_shift(self):
        source = synthetic_stretched_rgb()
        vectors = core.default_vectors()
        vectors["R"] = (28.0, 0.45)

        result = core.process_vectors(source, vectors, shadow_auth=0.0, protect_stars=True)

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreater(float(np.mean(np.abs(result - source))), 1e-3)

        src_l = core.rgb_luminance(source)
        out_l = core.rgb_luminance(result)
        self.assertLess(float(np.mean(np.abs(out_l - src_l))), 2.5e-2)

    def test_shadow_authority_reduces_background_tinting(self):
        source = synthetic_stretched_rgb()
        source[:12, :12, 2] = np.clip(source[:12, :12, 2] + 0.12, 0.0, 1.0)
        vectors = core.default_vectors()
        vectors["B"] = (-35.0, 0.65)

        open_result = core.process_vectors(source, vectors, shadow_auth=0.0, protect_stars=False)
        locked_result = core.process_vectors(source, vectors, shadow_auth=100.0, protect_stars=False)

        background = np.s_[0:12, 0:12, :]
        open_delta = float(np.mean(np.abs(open_result[background] - source[background])))
        locked_delta = float(np.mean(np.abs(locked_result[background] - source[background])))
        self.assertLess(locked_delta, open_delta)


class VeraLuxVectraAdapterTests(unittest.TestCase):
    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_stretched_rgb())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxVectraExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "red_hue": 22.0,
                "red_saturation": 0.35,
                "blue_hue": -15.0,
                "blue_saturation": 0.20,
                "shadow_authority": 0.0,
                "protect_stars": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(dst.array - src.array))), 1e-3)
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_vectra")
        self.assertEqual(dst.metadata["veralux.tool"], "Vectra")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_vectra_process(self):
        self.assertIs(SuiteVectraExtension, VeraLuxVectraExtension)


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_starcomposer_core as core  # noqa: E402
from veralux_extension import VeraLuxStarComposerExtension as SuiteStarComposerExtension  # noqa: E402
from veralux_starcomposer_adapter import VeraLuxStarComposerExtension  # noqa: E402


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


def synthetic_star_mask(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    star_a = np.exp(-(((x - 20.0) ** 2) + ((y - 22.0) ** 2)) / (2.0 * 2.2**2))
    star_b = 0.6 * np.exp(-(((x - 44.0) ** 2) + ((y - 39.0) ** 2)) / (2.0 * 3.5**2))
    faint = 0.18 * np.exp(-(((x - 36.0) ** 2) + ((y - 17.0) ** 2)) / (2.0 * 1.8**2))
    red = np.clip(star_a + faint * 1.2, 0.0, 1.0)
    green = np.clip(star_a * 0.82 + star_b + faint, 0.0, 1.0)
    blue = np.clip(star_a * 0.58 + star_b * 0.92 + faint * 0.8, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


class VeraLuxStarComposerCoreTests(unittest.TestCase):
    def test_star_mask_shaping_is_finite_clipped_and_brighter(self):
        source = synthetic_star_mask()

        result = core.process_star_mask(
            source,
            log_d=2.0,
            profile_hardness=50.0,
            color_grip=0.55,
            shadow_convergence=0.0,
            star_reduction=0.0,
            optical_healing=0.0,
            large_structure_rejection=0.0,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.mean(result)), float(np.mean(source)))

    def test_star_reduction_reduces_star_footprint(self):
        source = synthetic_star_mask()

        shaped = core.process_star_mask(source, log_d=2.0, star_reduction=0.0)
        reduced = core.process_star_mask(source, log_d=2.0, star_reduction=0.55)

        self.assertLess(float(np.count_nonzero(reduced[..., 0] > 0.35)), float(np.count_nonzero(shaped[..., 0] > 0.35)))

    def test_screen_composite_preserves_bounds_and_brightens_base(self):
        starless = np.full_like(synthetic_star_mask(), 0.18)
        stars = core.process_star_mask(synthetic_star_mask(), log_d=1.8)

        result = core.compose_with_starless(starless, stars, blend_mode="screen")

        self.assertEqual(result.shape, starless.shape)
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.mean(result)), float(np.mean(starless)))


class VeraLuxStarComposerAdapterTests(unittest.TestCase):
    def test_execute_writes_shaped_stars_and_provenance_metadata(self):
        src = FakeImage(synthetic_star_mask())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxStarComposerExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "log_d": 1.8,
                "profile_hardness": 50.0,
                "color_grip": 0.55,
                "shadow_convergence": 0.0,
                "large_structure_rejection": 0.0,
                "star_reduction": 0.0,
                "optical_healing": 0.0,
                "use_adaptive_anchor": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(dst.array)), float(np.mean(src.array)))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_starcomposer")
        self.assertEqual(dst.metadata["veralux.tool"], "StarComposer")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_starcomposer_process(self):
        self.assertIs(SuiteStarComposerExtension, VeraLuxStarComposerExtension)


if __name__ == "__main__":
    unittest.main()

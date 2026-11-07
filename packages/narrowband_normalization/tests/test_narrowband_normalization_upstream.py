"""Parity of the ported engine with the upstream NarrowbandNormalization script on the same inputs."""

import sys
import unittest
from pathlib import Path

import numpy as np


TEST_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = TEST_ROOT.parent / "package"
sys.path.insert(0, str(TEST_ROOT))
sys.path.insert(0, str(PACKAGE_ROOT))

import narrowband_normalization_core as core  # noqa: E402
from siril_upstream_loader import load_upstream_script  # noqa: E402
from test_narrowband_normalization import palette_image, params  # noqa: E402


class NarrowbandNormalizationUpstreamParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = load_upstream_script(
            "processing/NarrowbandNormalization.py", "_afternight_upstream_narrowband_normalization"
        )

    def test_upstream_version_matches_the_captured_baseline(self):
        self.assertEqual(self.upstream.VERSION, core.UPSTREAM_VERSION)

    def test_engine_output_is_identical_for_every_palette_and_lightness(self):
        for palette in core.PALETTES:
            for lightness in core.LIGHTNESS_SOURCES:
                with self.subTest(palette=palette, lightness=lightness):
                    source = palette_image(palette, 48)
                    settings = params(palette=palette, lightness=lightness)
                    np.testing.assert_array_equal(
                        core.process_image(source, settings),
                        self.upstream.process_image(source, settings),
                    )

    def test_engine_output_is_identical_across_the_control_ranges(self):
        cases = [
            params(palette="HOO", blend_mode="Mode 2", blend_amount=0.25, oiii_boost=1.7, shadow_point=0.4),
            params(palette="HOO", blend_mode="Mode 3", blend_amount=0.9, highlight_reduction=2.5, brightness=0.4),
            params(palette="SHO", scnr=0.8, sii_boost=0.6, oiii_boost=1.9, shadow_point=0.0, brightness=2.7),
            params(palette="HSO", scnr=0.3, lightness="Original", highlight_reduction=0.2),
        ]
        for settings in cases:
            with self.subTest(settings=settings):
                source = palette_image(settings["palette"], 48)
                np.testing.assert_array_equal(
                    core.process_image(source, settings),
                    self.upstream.process_image(source, settings),
                )

    def test_float_input_normalization_matches_the_upstream_rule(self):
        counts = palette_image("SHO", 16) * 65535.0
        np.testing.assert_array_equal(core.normalize_input(counts), self.upstream._normalize_range(counts))


if __name__ == "__main__":
    unittest.main()

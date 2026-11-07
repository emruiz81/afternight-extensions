"""Parity of the port's continuum estimate with the upstream Continuum Subtraction script on the same inputs."""

import sys
import types
import unittest
from pathlib import Path

import numpy as np


TEST_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = TEST_ROOT.parent / "package"
sys.path.insert(0, str(TEST_ROOT))
sys.path.insert(0, str(PACKAGE_ROOT))

import continuum_subtraction_core as core  # noqa: E402
from siril_upstream_loader import load_upstream_script  # noqa: E402
from test_continuum_subtraction import synthetic_pair  # noqa: E402


class _QuietSiril:
    def update_progress(self, *args, **kwargs):
        pass

    def reset_progress(self, *args, **kwargs):
        pass


class ContinuumSubtractionUpstreamParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = load_upstream_script(
            "processing/ContinuumSubtraction.py", "_afternight_upstream_continuum_subtraction"
        )
        cls.window = types.SimpleNamespace(siril=_QuietSiril())

    def upstream_c(self, emission, continuum, selection):
        """The upstream Estimate button: the median of the selection, then compute_c."""

        x, y, w, h = selection
        c_median = float(np.median(emission[y : y + h, x : x + w]))
        return self.upstream.SirilCSWindow.compute_c(self.window, emission, continuum, selection, c_median, False)

    def test_upstream_version_matches_the_captured_baseline(self):
        self.assertEqual(self.upstream.version, core.UPSTREAM_VERSION)

    def test_aad_and_coarse_scan_are_identical(self):
        emission, continuum = synthetic_pair()

        self.assertEqual(core.aad(emission), self.upstream.aad(emission))
        self.assertEqual(
            core.find_min(emission, continuum, 0.05), self.upstream.find_min(emission, continuum, 0.05, _QuietSiril())
        )

    def test_estimated_c_is_identical(self):
        for true_c, selection in ((0.3, (16, 24, 64, 48)), (0.12, (0, 0, 96, 96)), (0.7, (30, 10, 40, 70))):
            with self.subTest(true_c=true_c, selection=selection):
                emission, continuum = synthetic_pair(true_c=true_c)
                ours, details = core.compute_c(emission, continuum, selection=selection)
                self.assertFalse(details["fit_failed"])
                self.assertEqual(ours, self.upstream_c(emission, continuum, selection))


if __name__ == "__main__":
    unittest.main()

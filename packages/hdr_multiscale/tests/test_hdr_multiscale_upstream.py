"""Parity of the port with the upstream HDR Multiscale script on the same inputs."""

import sys
import unittest
from pathlib import Path

import numpy as np


TEST_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = TEST_ROOT.parent / "package"
sys.path.insert(0, str(TEST_ROOT))
sys.path.insert(0, str(PACKAGE_ROOT))

import hdr_multiscale_core as core  # noqa: E402
from siril_upstream_loader import load_upstream_script  # noqa: E402
from test_hdr_multiscale import stretched_rgb  # noqa: E402


class HdrMultiscaleUpstreamParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = load_upstream_script("processing/HDR_multiscale.py", "_afternight_upstream_hdr_multiscale")

    def upstream_dialog_result(self, rgb, n_scales, compression, mask_gamma, *, mono=False):
        """What the upstream dialog's Preview and Apply produce: the core, the mask blend, the mono mean."""

        transformed, mask = self.upstream.compute_wavescale_hdr(
            rgb, n_scales, compression, mask_gamma, self.upstream._B3, decay_rate=0.5
        )
        m3 = np.repeat(mask[..., None], 3, axis=2)
        out = rgb * (1.0 - m3) + transformed * m3
        if mono:
            out = np.mean(out, axis=2, dtype=np.float32)
        return np.clip(out, 0.0, 1.0).astype(np.float32, copy=False)

    def test_upstream_version_matches_the_captured_baseline(self):
        self.assertEqual(self.upstream.VERSION, core.UPSTREAM_VERSION)

    def test_core_output_is_identical(self):
        # SciPy's reflect convolution is only stable while a scale's dilated kernel (4 * 2**(n-1) + 1 taps) is no
        # longer than the image, so every case keeps to that; past it the port is deterministic and upstream is not.
        cases = ((48, 5, 1.5, 5.0), (48, 2, 0.1, 0.1), (48, 4, 4.5, 1.0), (160, 6, 2.0, 9.9))
        for size, n_scales, compression, mask_gamma in cases:
            source = stretched_rgb(size)
            with self.subTest(size=size, n_scales=n_scales, compression=compression, mask_gamma=mask_gamma):
                ours = core.compute_wavescale_hdr(source, n_scales, compression, mask_gamma, core._B3, decay_rate=0.5)
                theirs = self.upstream.compute_wavescale_hdr(
                    source, n_scales, compression, mask_gamma, self.upstream._B3, decay_rate=0.5
                )
                np.testing.assert_array_equal(ours[0], theirs[0])
                np.testing.assert_array_equal(ours[1], theirs[1])

    def test_applied_rgb_matches_the_upstream_dialog(self):
        source = stretched_rgb(48)
        for n_scales, compression, mask_gamma in ((5, 1.5, 5.0), (3, 3.0, 2.0)):
            with self.subTest(n_scales=n_scales, compression=compression, mask_gamma=mask_gamma):
                np.testing.assert_array_equal(
                    core.apply_hdr_multiscale(
                        source, n_scales=n_scales, compression_factor=compression, mask_gamma=mask_gamma
                    ),
                    self.upstream_dialog_result(source, n_scales, compression, mask_gamma),
                )

    def test_applied_mono_matches_the_upstream_dialog(self):
        mono = stretched_rgb(48)[..., 1]
        rgb = np.repeat(mono[:, :, None], 3, axis=2)

        np.testing.assert_array_equal(
            core.apply_hdr_multiscale(mono), self.upstream_dialog_result(rgb, 5, 1.5, 5.0, mono=True)
        )


if __name__ == "__main__":
    unittest.main()

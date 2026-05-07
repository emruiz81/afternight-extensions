import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_curves_core as curves_core  # noqa: E402
import veralux_nox_core as nox_core  # noqa: E402
import veralux_revela_core as revela_core  # noqa: E402
import veralux_sdk as sdk  # noqa: E402
import veralux_silentium_core as silentium_core  # noqa: E402
import veralux_starcomposer_core as starcomposer_core  # noqa: E402
import veralux_vectra_core as vectra_core  # noqa: E402
from veralux_curves_adapter import VeraLuxCurvesExtension  # noqa: E402
from veralux_nox_adapter import VeraLuxNoxExtension  # noqa: E402
from veralux_revela_adapter import VeraLuxRevelaExtension  # noqa: E402
from veralux_silentium_adapter import VeraLuxSilentiumExtension  # noqa: E402
from veralux_starcomposer_adapter import VeraLuxStarComposerExtension  # noqa: E402
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
        self.value = 0.0

    def set_text(self, _text):
        pass

    def set_value(self, value):
        self.value = float(value)

    def is_cancelled(self):
        return False


def tiny_rgb(value=0.25):
    return np.full((8, 8, 3), float(value), dtype=np.float32)


class VeraLuxQualityFallbackWarningTests(unittest.TestCase):
    def setUp(self):
        self._original_log_warning = sdk.log_warning
        self.warnings = []

        def capture_warning(message, *, component):
            self.warnings.append((str(component), str(message)))

        sdk.log_warning = capture_warning

    def tearDown(self):
        sdk.log_warning = self._original_log_warning

    def warning_text(self):
        return "\n".join(message for _component, message in self.warnings)

    def test_warning_helper_logs_each_fallback_once_per_process_instance(self):
        class Owner:
            pass

        owner = Owner()

        sdk.warn_quality_fallbacks_once(owner, ["fallback active"], component="extension.test")
        sdk.warn_quality_fallbacks_once(owner, ["fallback active"], component="extension.test")

        self.assertEqual(self.warnings, [("extension.test", "fallback active")])

    def test_curves_warns_when_scipy_akima_fallback_is_active(self):
        original_akima = curves_core._Akima1DInterpolator
        original_process = curves_core.process_curves
        curves_core._Akima1DInterpolator = None
        curves_core.process_curves = lambda image, _operations, **_kwargs: np.asarray(image, dtype=np.float32)
        try:
            extension = VeraLuxCurvesExtension(None)
            extension.execute_preview(
                None,
                FakeImage(tiny_rgb()),
                FakeImage(tiny_rgb(0.0)),
                {
                    "domain": "RGB/K",
                    "curve_points": [[0.0, 0.0], [0.5, 0.7], [1.0, 1.0]],
                },
                FakeProgress(),
            )
            extension.execute_preview(
                None,
                FakeImage(tiny_rgb()),
                FakeImage(tiny_rgb(0.0)),
                {
                    "domain": "RGB/K",
                    "curve_points": [[0.0, 0.0], [0.5, 0.7], [1.0, 1.0]],
                },
                FakeProgress(),
            )
        finally:
            curves_core._Akima1DInterpolator = original_akima
            curves_core.process_curves = original_process

        self.assertEqual(len(self.warnings), 1)
        self.assertIn("VeraLux Curves", self.warning_text())
        self.assertIn("SciPy", self.warning_text())

    def test_starcomposer_warns_when_opencv_fallback_is_active(self):
        original_cv2 = starcomposer_core.cv2
        original_shape = starcomposer_core.process_star_mask
        original_compose = starcomposer_core.compose_with_starless
        starcomposer_core.cv2 = None
        starcomposer_core.process_star_mask = lambda stars, **_kwargs: np.asarray(stars, dtype=np.float32)
        starcomposer_core.compose_with_starless = (
            lambda starless, _stars, **_kwargs: np.asarray(starless, dtype=np.float32)
        )
        try:
            VeraLuxStarComposerExtension(None).execute_preview(
                None,
                FakeImage(tiny_rgb()),
                FakeImage(tiny_rgb(0.0)),
                {"_stars_image": FakeImage(tiny_rgb(0.5))},
                FakeProgress(),
            )
        finally:
            starcomposer_core.cv2 = original_cv2
            starcomposer_core.process_star_mask = original_shape
            starcomposer_core.compose_with_starless = original_compose

        self.assertIn("VeraLux StarComposer", self.warning_text())
        self.assertIn("OpenCV", self.warning_text())

    def test_silentium_warns_when_wavelet_dependencies_are_missing(self):
        original_pywt = silentium_core._pywt
        original_convolve = silentium_core._scipy_convolve2d
        original_maximum = silentium_core._scipy_maximum_filter
        original_process = silentium_core.process_noise_reduction
        silentium_core._pywt = None
        silentium_core._scipy_convolve2d = None
        silentium_core._scipy_maximum_filter = None
        silentium_core.process_noise_reduction = lambda image, **_kwargs: np.asarray(image, dtype=np.float32)
        try:
            VeraLuxSilentiumExtension(None).execute_preview(
                None,
                FakeImage(tiny_rgb()),
                FakeImage(tiny_rgb(0.0)),
                {"use_stars": False},
                FakeProgress(),
            )
        finally:
            silentium_core._pywt = original_pywt
            silentium_core._scipy_convolve2d = original_convolve
            silentium_core._scipy_maximum_filter = original_maximum
            silentium_core.process_noise_reduction = original_process

        self.assertIn("VeraLux Silentium", self.warning_text())
        self.assertIn("PyWavelets", self.warning_text())
        self.assertIn("SciPy", self.warning_text())

    def test_revela_warns_when_opencv_fallback_is_active(self):
        original_cv2 = revela_core._cv2
        original_process = revela_core.process_structure
        revela_core._cv2 = None
        revela_core.process_structure = lambda image, **_kwargs: np.asarray(image, dtype=np.float32)
        try:
            VeraLuxRevelaExtension(None).execute_preview(
                None,
                FakeImage(tiny_rgb()),
                FakeImage(tiny_rgb(0.0)),
                {},
                FakeProgress(),
            )
        finally:
            revela_core._cv2 = original_cv2
            revela_core.process_structure = original_process

        self.assertIn("VeraLux Revela", self.warning_text())
        self.assertIn("OpenCV", self.warning_text())

    def test_vectra_warns_when_scipy_convolve_fallback_is_active(self):
        original_convolve = vectra_core._nd_convolve
        original_process = vectra_core.process_vectors
        vectra_core._nd_convolve = None
        vectra_core.process_vectors = lambda image, *_args, **_kwargs: np.asarray(image, dtype=np.float32)
        try:
            VeraLuxVectraExtension(None).execute_preview(
                None,
                FakeImage(tiny_rgb()),
                FakeImage(tiny_rgb(0.0)),
                {},
                FakeProgress(),
            )
        finally:
            vectra_core._nd_convolve = original_convolve
            vectra_core.process_vectors = original_process

        self.assertIn("VeraLux Vectra", self.warning_text())
        self.assertIn("SciPy", self.warning_text())

    def test_nox_warns_when_exact_solver_dependencies_are_missing(self):
        original_state = (
            nox_core._cv2,
            nox_core._cv2_import_attempted,
            nox_core._sparse,
            nox_core._scipy_cg,
            nox_core._scipy_expit,
            nox_core._scipy_import_attempted,
            nox_core._scipy_spsolve,
            nox_core._scipy_uniform_filter,
            nox_core.process_gradient_reduction,
        )
        nox_core._cv2 = None
        nox_core._cv2_import_attempted = True
        nox_core._sparse = None
        nox_core._scipy_cg = None
        nox_core._scipy_expit = None
        nox_core._scipy_import_attempted = True
        nox_core._scipy_spsolve = None
        nox_core._scipy_uniform_filter = None
        nox_core.process_gradient_reduction = (
            lambda image, **_kwargs: (np.asarray(image, dtype=np.float32), np.zeros_like(image, dtype=np.float32))
        )
        try:
            VeraLuxNoxExtension(None).execute(
                None,
                FakeImage(tiny_rgb()),
                FakeImage(tiny_rgb(0.0)),
                {"auto_mask": False},
                FakeProgress(),
            )
        finally:
            (
                nox_core._cv2,
                nox_core._cv2_import_attempted,
                nox_core._sparse,
                nox_core._scipy_cg,
                nox_core._scipy_expit,
                nox_core._scipy_import_attempted,
                nox_core._scipy_spsolve,
                nox_core._scipy_uniform_filter,
                nox_core.process_gradient_reduction,
            ) = original_state

        self.assertIn("VeraLux Nox", self.warning_text())
        self.assertIn("OpenCV", self.warning_text())
        self.assertIn("SciPy", self.warning_text())


if __name__ == "__main__":
    unittest.main()

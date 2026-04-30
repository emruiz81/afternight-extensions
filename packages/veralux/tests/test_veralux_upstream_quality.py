import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

import numpy as np


TEST_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = TEST_ROOT.parents[0] / "package"
REPO_ROOT = TEST_ROOT.parents[2]
APP_REPO = REPO_ROOT.parent / "afternight"
DEFAULT_UPSTREAM_CHECKOUT = REPO_ROOT.parent / "siril-scripts"

sys.path.insert(0, str(TEST_ROOT))
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

from test_veralux_regression_metrics import synthetic_suite_rgb  # noqa: E402

import veralux_alchemy_core as alchemy_core  # noqa: E402
import veralux_curves_core as curves_core  # noqa: E402
import veralux_hypermetric_stretch_core as hms_core  # noqa: E402
import veralux_vectra_core as vectra_core  # noqa: E402


class _DummyQtObject:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _DummyQtObject()

    def __getattr__(self, _name):
        return _DummyQtObject()

    def __bool__(self):
        return False

    def connect(self, *args, **kwargs):
        return None

    def emit(self, *args, **kwargs):
        return None


class _DummyQtNamespace:
    def __getattr__(self, _name):
        return _DummyQtNamespace()

    def __call__(self, *args, **kwargs):
        return self

    def __or__(self, _other):
        return self

    def __ror__(self, _other):
        return self


def _dummy_pyqt_signal(*args, **kwargs):
    return _DummyQtObject()


class _ImportStubs:
    """Minimal Siril/PyQt stubs so upstream GUI scripts can expose core classes."""

    MODULE_NAMES = (
        "sirilpy",
        "PyQt6",
        "PyQt6.QtWidgets",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "astropy",
        "astropy.io",
        "astropy.io.fits",
        "cv2",
    )

    def __enter__(self):
        self._originals = {name: sys.modules.get(name) for name in self.MODULE_NAMES}
        self._missing = {name for name, module in self._originals.items() if module is None}

        sirilpy = types.ModuleType("sirilpy")
        sirilpy.ensure_installed = lambda *args, **kwargs: None
        sirilpy.SirilInterface = _DummyQtObject
        sirilpy.LogColor = types.SimpleNamespace(
            GREEN="green",
            RED="red",
            BLUE="blue",
            YELLOW="yellow",
            DEFAULT="default",
        )
        sys.modules["sirilpy"] = sirilpy

        pyqt = types.ModuleType("PyQt6")
        sys.modules["PyQt6"] = pyqt
        for submodule in ("QtWidgets", "QtCore", "QtGui"):
            module = types.ModuleType(f"PyQt6.{submodule}")

            def __getattr__(name, _submodule=submodule):
                if name == "Qt":
                    return _DummyQtNamespace()
                if name == "pyqtSignal":
                    return _dummy_pyqt_signal
                return _DummyQtObject

            module.__getattr__ = __getattr__
            if submodule == "QtCore":
                module.Qt = _DummyQtNamespace()
                module.pyqtSignal = _dummy_pyqt_signal
                module.QThread = _DummyQtObject
            sys.modules[f"PyQt6.{submodule}"] = module

        astropy = types.ModuleType("astropy")
        astropy_io = types.ModuleType("astropy.io")
        astropy_fits = types.ModuleType("astropy.io.fits")
        astropy.io = astropy_io
        astropy_io.fits = astropy_fits
        sys.modules["astropy"] = astropy
        sys.modules["astropy.io"] = astropy_io
        sys.modules["astropy.io.fits"] = astropy_fits

        try:
            __import__("cv2")
        except Exception:
            cv2 = types.ModuleType("cv2")

            def unavailable(*args, **kwargs):
                raise RuntimeError("OpenCV is not available in this upstream quality test")

            cv2.__getattr__ = lambda _name: unavailable
            sys.modules["cv2"] = cv2

        return self

    def __exit__(self, exc_type, exc, tb):
        for name, module in self._originals.items():
            if name in self._missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def _upstream_checkout():
    return Path(os.environ.get("VERALUX_UPSTREAM_CHECKOUT", DEFAULT_UPSTREAM_CHECKOUT))


def _load_upstream_module(checkout, filename):
    source = checkout / "VeraLux" / f"VeraLux_{filename}.py"
    if not source.is_file():
        raise unittest.SkipTest(f"Missing upstream VeraLux source: {source}")

    module_name = f"_afternight_upstream_veralux_{filename.lower()}"
    with _ImportStubs():
        spec = importlib.util.spec_from_file_location(module_name, source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return module


def _max_and_mean_delta(actual, expected):
    delta = np.abs(np.asarray(actual, dtype=np.float32) - np.asarray(expected, dtype=np.float32))
    return float(np.max(delta)), float(np.mean(delta))


class VeraLuxUpstreamQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        checkout = _upstream_checkout()
        if not (checkout / "VeraLux").is_dir():
            raise unittest.SkipTest(
                "Set VERALUX_UPSTREAM_CHECKOUT or provide ../siril-scripts to run upstream quality comparisons"
            )

        cls.upstream = {
            "alchemy": _load_upstream_module(checkout, "Alchemy"),
            "curves": _load_upstream_module(checkout, "Curves"),
            "hms": _load_upstream_module(checkout, "HyperMetric_Stretch"),
            "vectra": _load_upstream_module(checkout, "Vectra"),
        }

    def test_alchemy_matches_upstream_worker_core_for_classic_and_quantum_paths(self):
        source_hwc = synthetic_suite_rgb(64)
        source_chw = np.moveaxis(source_hwc, -1, 0)
        cases = {
            "classic": {
                "bg_align": True,
                "auto_fit": True,
                "boost": 1.35,
                "mix_r": 0.85,
                "mix_g": 0.35,
                "mix_b": 1.0,
                "quantum_unmix": False,
                "sensor_profile": "Generic OSC",
            },
            "quantum": {
                "bg_align": True,
                "auto_fit": True,
                "boost": 1.10,
                "mix_r": 0.70,
                "mix_g": 0.45,
                "mix_b": 1.0,
                "quantum_unmix": True,
                "sensor_profile": "Sony IMX571",
            },
        }

        upstream = self.upstream["alchemy"]
        for name, params in cases.items():
            with self.subTest(path=name):
                actual = alchemy_core.process_narrowband(source_hwc, **params)
                if params["quantum_unmix"]:
                    coef = upstream.QUANTUM_COEFFS[params["sensor_profile"]]
                    ha, oiii = upstream.VeraLuxNBCore._quantum_unmix_ha_oiii(source_chw, coef)
                    base_rgb = np.stack([ha, oiii, oiii])
                else:
                    base_rgb = source_chw

                normalized = upstream.VeraLuxNBCore.linear_fit_channels(
                    base_rgb,
                    align_bg=params["bg_align"],
                    auto_gain=params["auto_fit"],
                    manual_boost=params["boost"],
                )
                expected_chw = upstream.VeraLuxNBCore.mix_channels(
                    normalized,
                    params["mix_r"],
                    params["mix_g"],
                    params["mix_b"],
                    quantum_unmix=False,
                    sensor_profile=params["sensor_profile"],
                )
                expected = np.moveaxis(expected_chw, 0, -1)

                max_delta, mean_delta = _max_and_mean_delta(actual, expected)
                self.assertLessEqual(max_delta, 2e-6)
                self.assertLessEqual(mean_delta, 2e-7)

    def test_hypermetric_stretch_matches_upstream_ready_to_use_core(self):
        source_hwc = synthetic_suite_rgb(64)
        source_chw = np.moveaxis(source_hwc, -1, 0)
        color_strategy = 0.30
        grip, shadow, expansion = hms_core.effective_hybrid_params(
            "ready_to_use",
            color_strategy=color_strategy,
            linear_expansion=0.08,
        )

        actual = hms_core.process_hypermetric_stretch(
            source_hwc,
            processing_mode="ready_to_use",
            working_space=hms_core.DEFAULT_PROFILE,
            target_bg=0.22,
            use_adaptive_anchor=True,
            auto_log_d=False,
            log_d=2.2,
            protect_b=5.0,
            convergence_power=3.5,
            color_strategy=color_strategy,
            linear_expansion=0.08,
        )
        expected_chw = self.upstream["hms"].process_veralux_v6(
            source_chw,
            log_D=2.2,
            protect_b=5.0,
            convergence_power=3.5,
            working_space=hms_core.DEFAULT_PROFILE,
            processing_mode="ready_to_use",
            target_bg=0.22,
            color_grip=grip,
            shadow_convergence=shadow,
            linear_expansion=expansion,
            use_adaptive_anchor=True,
        )
        expected = np.moveaxis(expected_chw, 0, -1)

        max_delta, mean_delta = _max_and_mean_delta(actual, expected)
        self.assertLessEqual(max_delta, 1e-7)
        self.assertLessEqual(mean_delta, 1e-8)

    def test_vectra_matches_upstream_lch_core_with_local_filter_tolerance(self):
        source = synthetic_suite_rgb(64)
        vectors = vectra_core.default_vectors()
        vectors.update({
            "R": (28.0, 0.45),
            "G": (-18.0, 0.25),
            "B": (22.0, 0.50),
            "C": (-12.0, 0.20),
            "M": (16.0, 0.30),
            "Y": (-14.0, 0.25),
        })

        actual = vectra_core.process_vectors(source, vectors, shadow_auth=0.0, protect_stars=False)
        expected = self.upstream["vectra"].VectraCore.process_vectors(
            source,
            vectors,
            shadow_auth=0.0,
            protect_stars=False,
        )

        max_delta, mean_delta = _max_and_mean_delta(actual, expected)
        self.assertLessEqual(max_delta, 2e-4)
        self.assertLessEqual(mean_delta, 1e-5)

    def test_curves_tracks_upstream_akima_output_with_documented_local_interpolator_tolerance(self):
        source = synthetic_suite_rgb(64)
        points = curves_core.curve_from_controls(
            black_point=0.04,
            shadow_lift=0.06,
            midtone_input=0.42,
            midtone_output=0.64,
            highlight_compression=0.10,
            white_point=0.96,
        )
        actual = curves_core.process_curves(
            source,
            [curves_core.curve_operation("RGB/K", points=points, lum_range_enabled=False)],
        )

        upstream_curves = self.upstream["curves"]
        lut = upstream_curves.CurvesCore.generate_lut(points)
        expected = upstream_curves.CurvesCore.apply_pipeline(
            source,
            {"RGB/K": {"active": True, "lut": lut, "lum_range_enabled": False}},
        )

        delta = np.abs(actual - expected)
        self.assertEqual(actual.shape, expected.shape)
        self.assertTrue(np.all(np.isfinite(actual)))
        self.assertGreaterEqual(float(np.min(actual)), 0.0)
        self.assertLessEqual(float(np.max(actual)), 1.0)
        self.assertLessEqual(float(np.mean(delta)), 0.025)
        self.assertLessEqual(float(np.percentile(delta, 95.0)), 0.040)
        self.assertLessEqual(float(np.max(delta)), 0.050)


if __name__ == "__main__":
    unittest.main()

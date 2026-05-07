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

from test_veralux_regression_metrics import synthetic_star_mask, synthetic_suite_rgb  # noqa: E402

import veralux_alchemy_core as alchemy_core  # noqa: E402
import veralux_curves_core as curves_core  # noqa: E402
import veralux_hypermetric_stretch_core as hms_core  # noqa: E402
import veralux_starcomposer_core as starcomposer_core  # noqa: E402
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


def _upstream_hms_auto_log_d(upstream_hms, image_chw, target, protect_b, working_space, adaptive, mode):
    img_norm = upstream_hms.VeraLuxCore.normalize_input(image_chw)
    if img_norm.ndim == 3 and img_norm.shape[0] != 3 and img_norm.shape[2] == 3:
        img_norm = img_norm.transpose(2, 0, 1)

    if img_norm.ndim == 3 and img_norm.shape[0] == 3:
        height, width = img_norm.shape[1], img_norm.shape[2]
        step = max(1, (height * width) // 100000)
        sub_data = np.vstack(
            (
                img_norm[0].flatten()[::step],
                img_norm[1].flatten()[::step],
                img_norm[2].flatten()[::step],
            )
        )
    else:
        height, width = img_norm.shape
        step = max(1, (height * width) // 100000)
        sub_data = img_norm.flatten()[::step]

    weights = upstream_hms.SENSOR_PROFILES[working_space]["weights"]
    anchor = (
        upstream_hms.VeraLuxCore.calculate_anchor_adaptive(sub_data, weights=weights)
        if adaptive
        else upstream_hms.VeraLuxCore.calculate_anchor(sub_data)
    )
    luminance, _anchored = upstream_hms.VeraLuxCore.extract_luminance(sub_data, anchor, weights)
    star_pressure = upstream_hms.VeraLuxCore.estimate_star_pressure(luminance)
    valid = luminance[luminance > 1e-7]
    if len(valid) == 0:
        return 2.0

    target_temp = float(target)
    best_log_d = 2.0
    for _ in range(15):
        best_log_d = upstream_hms.VeraLuxCore.solve_log_d(valid, target_temp, protect_b)

        if star_pressure > 0.6:
            target_temp *= 1.0 - (0.15 * star_pressure)

        if mode != "ready_to_use":
            break

        stretch_d = 10.0**best_log_d
        valid_stretched = upstream_hms.VeraLuxCore.hyperbolic_stretch(valid, stretch_d, protect_b)
        median = float(np.median(valid_stretched))
        std = float(np.std(valid_stretched))
        minimum = float(np.min(valid_stretched))
        global_floor = max(minimum, median - (2.7 * std))
        if global_floor <= 0.001:
            break

        target_temp -= 0.015
        if target_temp < 0.05:
            break

    return best_log_d


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
            "starcomposer": _load_upstream_module(checkout, "StarComposer"),
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

    def test_hypermetric_auto_log_d_matches_upstream_solver(self):
        source_hwc = synthetic_suite_rgb(64)
        source_chw = np.moveaxis(source_hwc, -1, 0)

        actual = hms_core.solve_log_d_for_image(
            source_hwc,
            target_median=0.22,
            protect_b=5.0,
            working_space=hms_core.DEFAULT_PROFILE,
            use_adaptive_anchor=True,
            processing_mode="ready_to_use",
        )
        expected = _upstream_hms_auto_log_d(
            self.upstream["hms"],
            source_chw,
            target=0.22,
            protect_b=5.0,
            working_space=hms_core.DEFAULT_PROFILE,
            adaptive=True,
            mode="ready_to_use",
        )

        self.assertLessEqual(abs(actual - expected), 1e-12)

    def test_vectra_matches_upstream_lch_core(self):
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

        cases = (
            (0.0, False),
            (50.0, True),
            (100.0, True),
        )

        for shadow_auth, protect_stars in cases:
            with self.subTest(shadow_auth=shadow_auth, protect_stars=protect_stars):
                actual = vectra_core.process_vectors(
                    source,
                    vectors,
                    shadow_auth=shadow_auth,
                    protect_stars=protect_stars,
                )
                expected = self.upstream["vectra"].VectraCore.process_vectors(
                    source,
                    vectors,
                    shadow_auth=shadow_auth,
                    protect_stars=protect_stars,
                )

                max_delta, mean_delta = _max_and_mean_delta(actual, expected)
                if vectra_core._nd_convolve is not None:
                    self.assertLessEqual(max_delta, 1e-7)
                    self.assertLessEqual(mean_delta, 1e-8)
                else:
                    self.assertLessEqual(max_delta, 2e-4)
                    self.assertLessEqual(mean_delta, 1e-5)

    def test_curves_matches_upstream_akima_output_for_rgbk_and_luminance_paths(self):
        source = synthetic_suite_rgb(64)
        upstream_curves = self.upstream["curves"]

        cases = [
            (
                curves_core.curve_operation(
                    "RGB/K",
                    points=curves_core.curve_from_controls(
                        black_point=0.04,
                        shadow_lift=0.06,
                        midtone_input=0.42,
                        midtone_output=0.64,
                        highlight_compression=0.10,
                        white_point=0.96,
                    ),
                    lum_range_enabled=False,
                ),
                "RGB/K",
            ),
            (
                curves_core.curve_operation(
                    "L",
                    points=[(0.0, 0.0), (0.18, 0.10), (0.42, 0.62), (0.74, 0.80), (1.0, 1.0)],
                    lum_range_enabled=True,
                    lum_min=0.05,
                    lum_max=0.85,
                    feather=0.20,
                ),
                "L",
            ),
        ]

        if curves_core._cv2 is None:
            cases = cases[:1]

        for operation, domain in cases:
            with self.subTest(domain=domain):
                actual = curves_core.process_curves(source, [operation])
                lut = upstream_curves.CurvesCore.generate_lut(operation["points"])
                expected = upstream_curves.CurvesCore.apply_pipeline(
                    source,
                    {
                        domain: {
                            "active": True,
                            "lut": lut,
                            "lum_range_enabled": operation["lum_range_enabled"],
                            "lum_min": operation["lum_min"],
                            "lum_max": operation["lum_max"],
                            "feather_sigma": operation["feather"],
                        }
                    },
                )

                max_delta, mean_delta = _max_and_mean_delta(actual, expected)
                self.assertLessEqual(max_delta, 2e-6)
                self.assertLessEqual(mean_delta, 2e-7)

    def test_starcomposer_matches_upstream_shaping_without_post_surgery_clipping(self):
        if starcomposer_core.cv2 is None:
            self.skipTest("OpenCV is required for StarComposer upstream surgery parity")

        source = synthetic_star_mask(64)
        actual = starcomposer_core.process_star_mask(
            source,
            working_space=starcomposer_core.DEFAULT_PROFILE,
            use_adaptive_anchor=False,
            log_d=2.0,
            profile_hardness=70.0,
            color_grip=0.80,
            shadow_convergence=0.20,
            large_structure_rejection=0.35,
            star_reduction=0.45,
            optical_healing=8.0,
        )

        upstream = self.upstream["starcomposer"]
        expected_chw = upstream.process_star_pipeline(
            np.moveaxis(source, -1, 0),
            2.0,
            70.0,
            0.80,
            0.20,
            0.45,
            8.0,
            0.35,
            upstream.SENSOR_PROFILES[starcomposer_core.DEFAULT_PROFILE],
            False,
        )
        expected = np.moveaxis(expected_chw, 0, -1)

        self.assertLess(float(np.min(expected)), 0.0)
        max_delta, mean_delta = _max_and_mean_delta(actual, expected)
        self.assertLessEqual(max_delta, 2e-6)
        self.assertLessEqual(mean_delta, 2e-7)


if __name__ == "__main__":
    unittest.main()

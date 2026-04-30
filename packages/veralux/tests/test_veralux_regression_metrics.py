import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_alchemy_core as alchemy_core  # noqa: E402
import veralux_curves_core as curves_core  # noqa: E402
import veralux_hypermetric_stretch_core as hms_core  # noqa: E402
import veralux_nox_core as nox_core  # noqa: E402
import veralux_revela_core as revela_core  # noqa: E402
import veralux_silentium_core as silentium_core  # noqa: E402
import veralux_starcomposer_core as starcomposer_core  # noqa: E402
import veralux_vectra_core as vectra_core  # noqa: E402


NUMERIC_METRIC_KEYS = (
    "min",
    "max",
    "mean",
    "std",
    "p05",
    "p50",
    "p95",
    "sample_0",
    "sample_1",
    "sample_2",
    "sample_3",
    "mean_abs_delta",
)

GOLDEN_METRICS = {
    "alchemy": {
        "shape": (64, 64, 3),
        "min": 0.0,
        "max": 0.991287350654602,
        "mean": 0.1670539230108261,
        "std": 0.11733125895261765,
        "p05": 0.022101251408457756,
        "p50": 0.13799458742141724,
        "p95": 0.3896026313304901,
        "sample_0": 0.007020973600447178,
        "sample_1": 0.39728763699531555,
        "sample_2": 0.1505875587463379,
        "sample_3": 0.3863692879676819,
        "mean_abs_delta": 0.042930543422698975,
    },
    "curves": {
        "shape": (64, 64, 3),
        "min": 0.05999999865889549,
        "max": 0.81983482837677,
        "mean": 0.23060916364192963,
        "std": 0.12965720891952515,
        "p05": 0.08561979979276657,
        "p50": 0.19299283623695374,
        "p95": 0.4854523241519928,
        "sample_0": 0.07045140117406845,
        "sample_1": 0.45416775345802307,
        "sample_2": 0.19305935502052307,
        "sample_3": 0.513308048248291,
        "mean_abs_delta": 0.08510275930166245,
    },
    "hypermetric_stretch": {
        "shape": (64, 64, 3),
        "min": 0.0,
        "max": 1.0,
        "mean": 0.2447294443845749,
        "std": 0.1711459904909134,
        "p05": 0.042565926909446716,
        "p50": 0.20604649186134338,
        "p95": 0.583254873752594,
        "sample_0": 0.007219688966870308,
        "sample_1": 0.44477739930152893,
        "sample_2": 0.20409026741981506,
        "sample_3": 0.5648099184036255,
        "mean_abs_delta": 0.10259736329317093,
    },
    "nox": {
        "shape": (72, 72, 3),
        "min": 0.08557743579149246,
        "max": 0.6640941500663757,
        "mean": 0.1380259245634079,
        "std": 0.028428541496396065,
        "p05": 0.1075744777917862,
        "p50": 0.1335163116455078,
        "p95": 0.17834042012691498,
        "sample_0": 0.12309874594211578,
        "sample_1": 0.19369132816791534,
        "sample_2": 0.13814441859722137,
        "sample_3": 0.1256597489118576,
        "mean_abs_delta": 0.04931022226810455,
    },
    "revela": {
        "shape": (64, 64, 3),
        "min": 0.0,
        "max": 1.0,
        "mean": 0.14367461204528809,
        "std": 0.14451268315315247,
        "p05": 0.007081965915858746,
        "p50": 0.08763957023620605,
        "p95": 0.42554011940956116,
        "sample_0": 0.0,
        "sample_1": 0.40638354420661926,
        "sample_2": 0.09049724042415619,
        "sample_3": 0.5303980112075806,
        "mean_abs_delta": 0.05171206593513489,
    },
    "silentium": {
        "shape": (72, 72, 3),
        "min": 0.06610754877328873,
        "max": 0.6729746460914612,
        "mean": 0.12074855715036392,
        "std": 0.04168442264199257,
        "p05": 0.08133438974618912,
        "p50": 0.10715988278388977,
        "p95": 0.20375065505504608,
        "sample_0": 0.08327057957649231,
        "sample_1": 0.23248156905174255,
        "sample_2": 0.08649206906557083,
        "sample_3": 0.15459971129894257,
        "mean_abs_delta": 0.015253758057951927,
    },
    "starcomposer": {
        "shape": (64, 64, 3),
        "min": 0.0,
        "max": 0.7147598266601562,
        "mean": 0.01160376612097025,
        "std": 0.05300094187259674,
        "p05": 0.0,
        "p50": 2.539764129596265e-15,
        "p95": 0.05909467115998268,
        "sample_0": 2.4210821573763605e-25,
        "sample_1": 0.0003619871276896447,
        "sample_2": 7.137546846960885e-14,
        "sample_3": 0.126705601811409,
        "mean_abs_delta": 0.003460266860201955,
    },
    "vectra": {
        "shape": (64, 64, 3),
        "min": 0.038975100964307785,
        "max": 0.8174989223480225,
        "mean": 0.14761953055858612,
        "std": 0.09063466638326645,
        "p05": 0.056502822786569595,
        "p50": 0.1215343251824379,
        "p95": 0.32990655303001404,
        "sample_0": 0.047004006803035736,
        "sample_1": 0.25967296957969666,
        "sample_2": 0.12213574349880219,
        "sample_3": 0.3443865180015564,
        "mean_abs_delta": 0.006691101472824812,
    },
}


def synthetic_suite_rgb(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    x_norm = x / float(size - 1)
    y_norm = y / float(size - 1)
    background = 0.045 + (0.055 * x_norm) + (0.035 * y_norm)
    nebula_a = 0.34 * np.exp(-(((x - 39.0) ** 2) + ((y - 30.0) ** 2)) / (2.0 * 10.5**2))
    nebula_b = 0.21 * np.exp(-(((x - 21.0) ** 2) + ((y - 43.0) ** 2)) / (2.0 * 8.0**2))
    star_a = 0.62 * np.exp(-(((x - 18.0) ** 2) + ((y - 20.0) ** 2)) / (2.0 * 1.55**2))
    star_b = 0.34 * np.exp(-(((x - 48.0) ** 2) + ((y - 47.0) ** 2)) / (2.0 * 2.3**2))
    texture = 0.012 * np.sin(x * 0.43) * np.cos(y * 0.37)
    red = np.clip(background * 1.04 + nebula_a * 1.12 + nebula_b * 0.34 + star_a + star_b * 0.86 + texture,
                  0.0,
                  1.0)
    green = np.clip(background * 0.96 + nebula_a * 0.60 + nebula_b * 0.88 + star_a * 0.88 + star_b + texture * 0.45,
                    0.0,
                    1.0)
    blue = np.clip(background * 0.90 + nebula_a * 0.32 + nebula_b * 1.04 + star_a * 0.70 + star_b * 0.90 - texture * 0.30,
                   0.0,
                   1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def synthetic_gradient_rgb(size=72):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    x_norm = x / float(size - 1)
    y_norm = y / float(size - 1)
    gradient = 0.070 + 0.130 * x_norm + 0.055 * y_norm
    nebula = 0.24 * np.exp(-(((x - 42.0) ** 2) + ((y - 35.0) ** 2)) / (2.0 * 9.0**2))
    stars = 0.58 * np.exp(-(((x - 21.0) ** 2) + ((y - 18.0) ** 2)) / (2.0 * 1.7**2))
    ripple = 0.006 * np.sin(x * 0.29 + y * 0.11)
    red = np.clip(gradient * 1.08 + nebula * 1.10 + stars + ripple, 0.0, 1.0)
    green = np.clip(gradient * 0.98 + nebula * 0.82 + stars * 0.95 + ripple * 0.6, 0.0, 1.0)
    blue = np.clip(gradient * 0.88 + nebula * 0.55 + stars * 0.82 + ripple * 0.3, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def synthetic_noisy_rgb(size=72):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    base = 0.075 + 0.018 * (x / float(size - 1))
    nebula = 0.20 * np.exp(-(((x - 34.0) ** 2) + ((y - 38.0) ** 2)) / (2.0 * 12.0**2))
    star = 0.63 * np.exp(-(((x - 21.0) ** 2) + ((y - 19.0) ** 2)) / (2.0 * 1.7**2))
    luminance = np.clip(base + nebula + star, 0.0, 1.0)
    noise = 0.018 * np.sin(x * 2.17 + y * 0.71) + 0.013 * np.cos(x * 0.47 - y * 2.03)
    chroma = 0.010 * np.sin(x * 1.31) * np.cos(y * 1.73)
    red = np.clip(luminance * 1.05 + noise + chroma, 0.0, 1.0)
    green = np.clip(luminance * 0.98 + noise * 0.75 - chroma * 0.4, 0.0, 1.0)
    blue = np.clip(luminance * 0.88 + noise * 0.55 + chroma * 0.7, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def synthetic_star_mask(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    star_a = np.exp(-(((x - 20.0) ** 2) + ((y - 22.0) ** 2)) / (2.0 * 2.2**2))
    star_b = 0.64 * np.exp(-(((x - 44.0) ** 2) + ((y - 39.0) ** 2)) / (2.0 * 3.5**2))
    faint = 0.18 * np.exp(-(((x - 36.0) ** 2) + ((y - 17.0) ** 2)) / (2.0 * 1.8**2))
    red = np.clip(star_a + faint * 1.2, 0.0, 1.0)
    green = np.clip(star_a * 0.82 + star_b + faint, 0.0, 1.0)
    blue = np.clip(star_a * 0.58 + star_b * 0.92 + faint * 0.8, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def process_outputs():
    rgb = synthetic_suite_rgb()
    gradient = synthetic_gradient_rgb()
    noisy = synthetic_noisy_rgb()
    star_mask = synthetic_star_mask()

    previous_cv2 = revela_core._cv2
    revela_core._cv2 = None
    try:
        revela_output = revela_core.process_structure(
            rgb,
            texture_amt=1.0,
            structure_amt=1.0,
            shadow_auth=0.0,
            protect_stars=False,
        )
    finally:
        revela_core._cv2 = previous_cv2

    vectors = vectra_core.default_vectors()
    vectors.update({
        "R": (28.0, 0.45),
        "G": (-18.0, 0.25),
        "B": (22.0, 0.50),
        "C": (-12.0, 0.20),
        "M": (16.0, 0.30),
        "Y": (-14.0, 0.25),
    })

    return {
        "alchemy": (
            alchemy_core.process_narrowband(
                rgb,
                bg_align=True,
                auto_fit=True,
                boost=1.35,
                mix_r=0.85,
                mix_g=0.35,
                mix_b=1.0,
                quantum_unmix=False,
                sensor_profile="Generic OSC",
            ),
            rgb,
        ),
        "curves": (
            curves_core.process_curves(
                rgb,
                [
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
                    )
                ],
            ),
            rgb,
        ),
        "hypermetric_stretch": (
            hms_core.process_hypermetric_stretch(
                rgb,
                processing_mode="ready_to_use",
                working_space=hms_core.DEFAULT_PROFILE,
                target_bg=0.22,
                use_adaptive_anchor=True,
                auto_log_d=False,
                log_d=2.2,
                protect_b=5.0,
                convergence_power=3.5,
                color_strategy=0.30,
                linear_expansion=0.08,
                color_grip=0.80,
                shadow_convergence=0.18,
            ),
            rgb,
        ),
        "nox": (
            nox_core.process_gradient_reduction(
                gradient,
                auto_mask=False,
                stiffness=1.5,
                rejection_power=45.0,
                model_grid=16.0,
                correction_strength=1.0,
                return_model=False,
            ),
            gradient,
        ),
        "revela": (revela_output, rgb),
        "silentium": (
            silentium_core.process_noise_reduction(
                noisy,
                intensity=70.0,
                adaptive_noise=False,
                detail_guard=20.0,
                shadow_smoothness=35.0,
                enable_chroma=True,
                chroma_strength=45.0,
                protect_highlights=False,
            ),
            noisy,
        ),
        "starcomposer": (
            starcomposer_core.process_star_mask(
                star_mask,
                working_space=starcomposer_core.DEFAULT_PROFILE,
                use_adaptive_anchor=False,
                log_d=2.0,
                profile_hardness=70.0,
                color_grip=0.80,
                shadow_convergence=0.20,
                large_structure_rejection=0.35,
                star_reduction=0.45,
                optical_healing=8.0,
            ),
            star_mask,
        ),
        "vectra": (
            vectra_core.process_vectors(
                rgb,
                vectors,
                shadow_auth=0.0,
                protect_stars=False,
            ),
            rgb,
        ),
    }


def output_metrics(output, source):
    values = np.asarray(output, dtype=np.float32)
    source_values = np.asarray(source, dtype=np.float32)
    h, w = values.shape[:2]
    return {
        "shape": tuple(int(dim) for dim in values.shape),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "p05": float(np.percentile(values, 5.0)),
        "p50": float(np.percentile(values, 50.0)),
        "p95": float(np.percentile(values, 95.0)),
        "sample_0": float(values[0, 0, 0]),
        "sample_1": float(values[h // 2, w // 2, 1]),
        "sample_2": float(values[-1, -1, 2]),
        "sample_3": float(values[h // 3, w // 4, 0]),
        "mean_abs_delta": float(np.mean(np.abs(values - source_values))),
    }


class VeraLuxRegressionMetricTests(unittest.TestCase):
    def test_core_outputs_match_stable_synthetic_goldens(self):
        outputs = process_outputs()
        self.assertEqual(set(GOLDEN_METRICS), set(outputs))

        for name, (output, source) in outputs.items():
            with self.subTest(process=name):
                metrics = output_metrics(output, source)
                expected = GOLDEN_METRICS[name]
                self.assertEqual(metrics["shape"], expected["shape"])
                self.assertGreater(metrics["mean_abs_delta"], 1e-5)
                for key in NUMERIC_METRIC_KEYS:
                    self.assertAlmostEqual(metrics[key], expected[key], delta=5e-5, msg=key)


if __name__ == "__main__":
    unittest.main()

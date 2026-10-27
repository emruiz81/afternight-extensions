import json
import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

from afternight import ui  # noqa: E402
import veralux_curves_core as core  # noqa: E402
import veralux_curves_ui as curves_ui  # noqa: E402
from veralux_curves_adapter import VeraLuxCurvesExtension  # noqa: E402
from veralux_extension import VeraLuxCurvesExtension as SuiteCurvesExtension  # noqa: E402


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


class TypedFakeImage:
    """An image handle that keeps its samples' representation, as the host's buffers do."""

    def __init__(self, array):
        self.array = np.asarray(array)
        self.metadata = {}

    def to_numpy(self):
        return self.array

    def from_numpy(self, array):
        self.array = np.asarray(array, dtype=self.array.dtype)

    def set_metadata(self, key, value):
        self.metadata[str(key)] = str(value)


def scattered_rgb(height=48, width=64):
    """An RGB image in [0, 1) whose every pixel differs from its neighbours."""

    return np.random.default_rng(20261026).random((height, width, 3), dtype=np.float32)


def synthetic_rgb_gradient(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    gradient = (x + y) / float((size - 1) * 2)
    red = np.clip(gradient * 0.95 + 0.05, 0.0, 1.0)
    green = np.clip(gradient * 0.75 + 0.12, 0.0, 1.0)
    blue = np.clip(gradient * 0.45 + 0.20, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


class VeraLuxCurvesCoreTests(unittest.TestCase):
    def test_generate_lut_respects_endpoints_and_is_clipped(self):
        points = [(0.18, -0.15), (0.50, 0.72), (0.90, 1.15)]

        lut = core.generate_lut(points, size=512)

        self.assertEqual(lut.shape, (512,))
        self.assertGreaterEqual(float(lut.min()), 0.0)
        self.assertLessEqual(float(lut.max()), 1.0)
        self.assertAlmostEqual(float(lut[0]), 0.0, places=5)
        self.assertGreater(float(lut[256]), 0.62)
        self.assertAlmostEqual(float(lut[-1]), 1.0, places=5)

    def test_rgb_curve_brightens_midtones_and_preserves_layout(self):
        source = synthetic_rgb_gradient()
        operation = core.curve_operation(
            "RGB/K",
            points=core.curve_from_controls(midtone_input=0.50, midtone_output=0.68),
        )

        result = core.process_curves(source, [operation])

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreater(float(np.mean(result)), float(np.mean(source)))
        self.assertLessEqual(float(result.max()), 1.0)

    def test_luminance_range_limits_curve_to_selected_zone(self):
        source = synthetic_rgb_gradient()
        operation = core.curve_operation(
            "RGB/K",
            points=core.curve_from_controls(midtone_input=0.50, midtone_output=0.80),
            lum_range_enabled=True,
            lum_min=0.38,
            lum_max=0.62,
            feather=0.0,
        )

        result = core.process_curves(source, [operation])

        luminance = np.mean(source, axis=2)
        shadow_delta = float(np.mean(np.abs(result[luminance < 0.30] - source[luminance < 0.30])))
        midtone_delta = float(
            np.mean(
                np.abs(
                    result[(luminance > 0.43) & (luminance < 0.57)] - source[(luminance > 0.43) & (luminance < 0.57)]
                )
            )
        )
        highlight_delta = float(np.mean(np.abs(result[luminance > 0.72] - source[luminance > 0.72])))
        self.assertLess(shadow_delta, 1e-6)
        self.assertGreater(midtone_delta, 2e-2)
        self.assertLess(highlight_delta, 1e-6)


class VeraLuxCurvesAdapterTests(unittest.TestCase):
    def test_process_is_rt_preview_based_with_native_preview_defaults(self):
        self.assertTrue(issubclass(VeraLuxCurvesExtension, ui.RTPreviewProcess))

        defs = curves_ui.parameter_defs()
        by_id = {param["id"]: param for param in defs if "id" in param}

        self.assertTrue(by_id["window_meta"]["sub_area"])
        self.assertIs(by_id["window_meta"]["sub_area_default_enabled"], False)
        self.assertEqual(by_id["window_meta"]["sub_area_label"], "Preview: Curves")
        self.assertEqual(by_id["window_meta"]["window_size"], [1260, 760])
        self.assertEqual(by_id["window_meta"]["controls_panel_width"], 520)
        self.assertIs(by_id["window_meta"]["preview_hq_default"], False)
        self.assertIs(by_id["window_meta"]["header_progress"], False)

        section_labels = [param["label"] for param in defs if param.get("type") == "section"]
        self.assertEqual(
            section_labels,
            [
                "Curve Domain",
                "Curve",
                "Luminance Range",
            ],
        )

        self.assertEqual(by_id["curve_points"]["type"], "curve_editor")
        self.assertEqual(by_id["curve_points"]["default"], [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0]])
        self.assertEqual(by_id["curve_points"]["interpolation"], "akima")
        self.assertIs(by_id["curve_points"]["histogram"], True)
        self.assertIs(by_id["curve_points"]["grid"], True)
        self.assertIs(by_id["curve_points"]["guide"], True)

        for removed_id in (
            "black_point",
            "shadow_lift",
            "midtone_input",
            "midtone_output",
            "highlight_compression",
            "white_point",
        ):
            self.assertNotIn(removed_id, by_id)

        for param_id in (
            "lum_min",
            "lum_max",
            "feather",
        ):
            self.assertIs(by_id[param_id]["tracking"], False, param_id)

        for param in defs:
            if param.get("type") in {"float", "double", "int", "bool", "choice", "string"}:
                self.assertTrue(param.get("tooltip"), param["id"])

    def test_manifest_declares_curves_preview_capabilities(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        self.assertEqual(
            processes["curves"]["capabilities"],
            {"execute": True, "preview": True, "keep_open": True, "preview_scaling": "full_only"},
        )

    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_rgb_gradient())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxCurvesExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "domain": "RGB/K",
                "curve_points": [[0.0, 0.0], [0.50, 0.70], [1.0, 1.0]],
                "range_enabled": False,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(dst.array)), float(np.mean(src.array)))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_curves")
        self.assertEqual(dst.metadata["veralux.tool"], "Curves")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(dst.metadata["ANLIN"], "nonlinear")
        self.assertEqual(dst.metadata["ANBASIS"], "display-rgb")
        self.assertEqual(dst.metadata["ANASRC"], "process")
        self.assertEqual(dst.metadata["ANOP"], "veralux-curves")
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_writes_preview_image_without_provenance_metadata(self):
        src = FakeImage(synthetic_rgb_gradient())
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxCurvesExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "domain": "RGB/K",
                "curve_points": [[0.0, 0.0], [0.50, 0.70], [1.0, 1.0]],
                "range_enabled": False,
            },
            progress,
        )

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(preview.array)), float(np.mean(src.array)))
        self.assertEqual(preview.metadata, {})
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_curves_process(self):
        self.assertIs(SuiteCurvesExtension, VeraLuxCurvesExtension)


class VeraLuxCurvesPreviewScalingTests(unittest.TestCase):
    """Why the manifest keeps Curves at `full_only`. Within [0, 1] its preview at a pixel is a function of the pixel's
    value and the parameters alone, so a frame over a crop or any rearrangement of the image previews each pixel as the
    whole image's frame does. A floating-point image whose brightest sample passes one is the exception: Curves takes
    it as counts and divides the whole image down, while a reduced frame, each pixel the mean of a block, can average
    that sample below one and skip the division, so a drag would preview an exposure that neither the settled frame
    nor Apply gives. Floating-point samples above one are ordinary in AfterNight - a calibrated light, a Linear Match
    result - so Curves previews the whole image in every frame."""

    CURVE = [[0.0, 0.0], [0.25, 0.35], [0.6, 0.72], [1.0, 1.0]]
    CROP = (slice(10, 40), slice(5, 50))

    def preview_of(self, source, params):
        src = TypedFakeImage(np.ascontiguousarray(source))
        preview = TypedFakeImage(np.zeros_like(src.array))
        VeraLuxCurvesExtension(None).execute_preview(None, src, preview, params, FakeProgress())
        return preview.array

    def assert_same_pixels(self, part, whole_part):
        # Within the last unit of what a colour conversion rounds by where a pixel falls in a vector, which a crop
        # moves: a few units of a Float32 sample, one code of a sixteen-bit one - measured 2.3e-6 and one code in the
        # Lab domains. A preview that read the rest of the image would differ by orders of magnitude more.
        full_scale = float(np.iinfo(part.dtype).max) if np.issubdtype(part.dtype, np.integer) else 1.0
        np.testing.assert_allclose(
            part.astype(np.float64) / full_scale,
            whole_part.astype(np.float64) / full_scale,
            rtol=0.0,
            atol=2e-5,
        )

    def test_a_pixels_preview_reads_nothing_but_the_pixel(self):
        floating = scattered_rgb()
        sources = {"uint16": (floating * 65535.0).astype(np.uint16), "float32": floating}
        # Every third pixel each way and the image turned end to end.
        strided = (slice(None, None, 3), slice(None, None, 3))
        reversed_order = (slice(None, None, -1), slice(None, None, -1))
        for name, source in sources.items():
            for domain in core.CHANNELS:
                for range_enabled in (False, True):
                    with self.subTest(source=name, domain=domain, range_enabled=range_enabled):
                        params = {
                            "domain": domain,
                            "curve_points": self.CURVE,
                            "range_enabled": range_enabled,
                            "lum_min": 0.3,
                            "lum_max": 0.7,
                            "feather": 0.2,
                        }
                        whole = self.preview_of(source, params)
                        self.assertFalse(np.array_equal(whole, source), "the curve leaves the image as it was")
                        for picked in (self.CROP, strided, reversed_order):
                            self.assert_same_pixels(self.preview_of(source[picked], params), whole[picked])

    def test_a_floating_point_image_beyond_one_is_scaled_by_what_the_frame_holds(self):
        # The one value of the whole image Curves reads: a floating-point frame whose maximum passes one is taken as
        # counts and divided down, so a crop that leaves the bright pixel out previews differently.
        source = scattered_rgb()
        source[0, 0, :] = 2.0
        params = {"domain": "RGB/K", "curve_points": self.CURVE, "range_enabled": False}
        whole = self.preview_of(source, params)
        part = self.preview_of(source[self.CROP], params)
        self.assertFalse(np.allclose(part, whole[self.CROP], rtol=0.0, atol=2e-5))

    def test_a_reduced_frame_of_an_image_beyond_one_would_preview_another_exposure(self):
        # Each 2 x 2 block holds one sample at 2.0 and three at 0.5. The whole image passes one and is divided down to
        # near black, as Apply gives it; its block means, 0.875 everywhere, are read as they are and curved bright. A
        # `decimated` frame would show the second over the first while a person drags.
        source = np.full((48, 64, 3), 0.5, dtype=np.float32)
        source[::2, ::2, :] = 2.0
        reduced = source.reshape(24, 2, 32, 2, 3).mean(axis=(1, 3))
        params = {"domain": "RGB/K", "curve_points": self.CURVE, "range_enabled": False}

        self.assertLess(float(self.preview_of(source, params).max()), 0.01)
        self.assertGreater(float(self.preview_of(reduced, params).min()), 0.5)


if __name__ == "__main__":
    unittest.main()

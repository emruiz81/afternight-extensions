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
import hdr_multiscale_core as core  # noqa: E402
import hdr_multiscale_ui as hdr_ui  # noqa: E402
from hdr_multiscale_extension import HdrMultiscaleExtension, settings_from_params  # noqa: E402


class FakeImage:
    def __init__(self, array):
        self.array = np.asarray(array)
        self.metadata = {}

    def to_numpy(self):
        return self.array

    def from_numpy(self, array):
        self.array = np.asarray(array)

    def set_metadata(self, key, value):
        self.metadata[str(key)] = str(value)


class FakeProgress:
    def __init__(self):
        self.value = 0.0
        self.cancelled = False

    def set_text(self, text):
        self.text = str(text)

    def set_value(self, value):
        self.value = float(value)

    def is_cancelled(self):
        return self.cancelled


def stretched_rgb(size=64, seed=3):
    """A stretched galaxy-like field: dark sky with a black corner, a bright saturated core, a few stars."""

    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    core_glow = 0.85 * np.exp(-(((x - 36.0) ** 2) + ((y - 30.0) ** 2)) / (2.0 * 7.0**2))
    halo = 0.25 * np.exp(-(((x - 36.0) ** 2) + ((y - 30.0) ** 2)) / (2.0 * 18.0**2))
    stars = sum(
        0.6 * np.exp(-(((x - sx) ** 2) + ((y - sy) ** 2)) / (2.0 * 1.2**2)) for sx, sy in ((10, 12), (50, 52), (20, 48))
    )
    luminance = 0.08 + core_glow + halo + stars + rng.normal(0.0, 0.006, (size, size))
    rgb = np.stack([luminance * 1.02, luminance, luminance * 0.93], axis=-1)
    rgb[:6, :6] = 0.0
    return np.clip(rgb, 0.0, 1.0).astype(np.float32)


class HdrMultiscaleCoreTests(unittest.TestCase):
    def test_rgb_result_is_finite_in_range_and_compresses_the_core(self):
        source = stretched_rgb()

        result = core.apply_hdr_multiscale(source)

        self.assertEqual(result.shape, source.shape)
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.max(np.abs(result - source))), 1e-3)

    def test_black_pixels_keep_their_value_through_the_luminance_mask(self):
        source = stretched_rgb()

        result = core.apply_hdr_multiscale(source)

        np.testing.assert_array_equal(result[:6, :6], source[:6, :6])

    def test_mono_images_come_back_mono_as_the_mean_of_three_equal_channels(self):
        rgb = stretched_rgb()
        mono = rgb[..., 1]

        flat = core.apply_hdr_multiscale(mono)
        column = core.apply_hdr_multiscale(mono[..., None])
        expected = np.mean(core.apply_hdr_multiscale(np.repeat(mono[..., None], 3, axis=2)), axis=2)

        self.assertEqual(flat.shape, mono.shape)
        self.assertEqual(column.shape, mono.shape + (1,))
        np.testing.assert_allclose(flat, expected, atol=1e-6)
        np.testing.assert_array_equal(column[..., 0], flat)

    def test_mask_output_takes_the_source_shape_and_rises_with_lightness(self):
        source = stretched_rgb()

        mask = core.apply_hdr_multiscale(source, return_mask=True)
        mono_mask = core.apply_hdr_multiscale(source[..., 0], return_mask=True)

        self.assertEqual(mask.shape, source.shape)
        self.assertEqual(mono_mask.shape, source.shape[:2])
        self.assertGreater(float(mask[30, 36, 0]), float(mask[60, 5, 0]))
        np.testing.assert_array_equal(mask[..., 0], mask[..., 2])

    def test_more_scales_and_compression_change_the_result(self):
        source = stretched_rgb()

        baseline = core.apply_hdr_multiscale(source)
        more_scales = core.apply_hdr_multiscale(source, n_scales=7)
        stronger = core.apply_hdr_multiscale(source, compression_factor=3.0)

        self.assertGreater(float(np.max(np.abs(more_scales - baseline))), 1e-4)
        self.assertGreater(float(np.max(np.abs(stronger - baseline))), 1e-4)

    def test_many_scales_on_a_small_area_are_finite_and_repeatable(self):
        # At 10 scales the coarsest kernel has 2049 taps, far longer than this image; SciPy's convolve, which the
        # upstream script calls, returns different values from run to run here, NaN included.
        source = stretched_rgb(48)

        runs = [core.apply_hdr_multiscale(source, n_scales=10, compression_factor=2.0) for _ in range(3)]

        self.assertTrue(np.all(np.isfinite(runs[0])))
        np.testing.assert_array_equal(runs[0], runs[1])
        np.testing.assert_array_equal(runs[0], runs[2])

    def test_reflected_convolution_matches_a_direct_sum_over_the_reflected_signal(self):
        signal = np.arange(7, dtype=np.float32)[None, :]
        kernel = core._build_spaced_kernel(core._B3, 3)
        radius = len(kernel) // 2

        result = core._conv_sep_reflect(signal, kernel, axis=1)

        extended = signal[0, core._reflect_index(np.arange(-radius, 7 + radius), 7)]
        expected = [float(np.dot(extended[i : i + len(kernel)].astype(np.float64), kernel[::-1])) for i in range(7)]
        np.testing.assert_allclose(result[0], expected, rtol=1e-6)

    def test_unsupported_channel_count_is_refused(self):
        with self.assertRaisesRegex(ValueError, "mono or RGB"):
            core.apply_hdr_multiscale(np.zeros((8, 8, 4), dtype=np.float32))


class HdrMultiscaleAdapterTests(unittest.TestCase):
    def test_execute_matches_core_and_stamps_result(self):
        source = stretched_rgb()
        dst = FakeImage(source.copy())
        progress = FakeProgress()

        HdrMultiscaleExtension(None).execute("target", FakeImage(source), dst, {"n_scales": 4}, progress)

        np.testing.assert_allclose(dst.array, core.apply_hdr_multiscale(source, n_scales=4), atol=1e-6)
        self.assertEqual(progress.value, 100.0)
        self.assertEqual(dst.metadata["afternight.extension"], "hdr_multiscale")
        self.assertEqual(dst.metadata["hdr_multiscale.upstream_version"], core.UPSTREAM_VERSION)
        self.assertEqual(dst.metadata["ANBASIS"], "display-rgb")

    def test_uint16_mono_round_trips_in_its_sample_type_and_shape(self):
        source = (stretched_rgb()[..., 0] * 65535.0).astype(np.uint16)
        dst = FakeImage(source.copy())

        HdrMultiscaleExtension(None).execute("target", FakeImage(source), dst, {}, FakeProgress())

        expected = core.apply_hdr_multiscale(source.astype(np.float32) / 65535.0)
        self.assertEqual(dst.array.dtype, np.uint16)
        self.assertEqual(dst.array.shape, source.shape)
        np.testing.assert_array_equal(dst.array, (expected * 65535.0).astype(np.uint16))
        self.assertEqual(dst.metadata["ANBASIS"], "monochrome")

    def test_channel_first_arrays_are_written_channel_first(self):
        source = stretched_rgb()
        planar = np.moveaxis(source, -1, 0).copy()
        dst = FakeImage(planar.copy())

        HdrMultiscaleExtension(None).execute("target", FakeImage(planar), dst, {}, FakeProgress())

        np.testing.assert_allclose(dst.array, np.moveaxis(core.apply_hdr_multiscale(source), -1, 0), atol=1e-6)

    def test_preview_can_show_the_mask_and_leaves_metadata_alone(self):
        source = stretched_rgb()
        preview = FakeImage(source.copy())

        HdrMultiscaleExtension(None).execute_preview(
            "target", FakeImage(source), preview, {"show_mask": True}, FakeProgress()
        )

        np.testing.assert_allclose(preview.array, core.apply_hdr_multiscale(source, return_mask=True), atol=1e-6)
        self.assertEqual(preview.metadata, {})

    def test_cancelled_run_raises_before_writing(self):
        source = stretched_rgb()
        dst = FakeImage(source.copy())
        progress = FakeProgress()
        progress.cancelled = True

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            HdrMultiscaleExtension(None).execute("target", FakeImage(source), dst, {}, progress)
        np.testing.assert_array_equal(dst.array, source)

    def test_settings_default_to_upstream_values_and_clamp_to_the_dialog_ranges(self):
        self.assertEqual(settings_from_params({}), (5, 1.5, 5.0, False))
        self.assertEqual(
            settings_from_params({"n_scales": 40, "compression": 0.0, "mask_gamma": 99.0}), (10, 0.1, 10.0, False)
        )


class HdrMultiscaleSchemaTests(unittest.TestCase):
    def test_schema_uses_the_upstream_ranges_and_defaults(self):
        by_id = {item["id"]: item for item in hdr_ui.parameter_defs()}

        self.assertEqual((by_id["n_scales"]["min"], by_id["n_scales"]["max"], by_id["n_scales"]["default"]), (2, 10, 5))
        self.assertEqual((by_id["compression"]["min"], by_id["compression"]["max"]), (0.1, 5.0))
        self.assertEqual(by_id["compression"]["default"], 1.5)
        self.assertEqual((by_id["mask_gamma"]["min"], by_id["mask_gamma"]["max"]), (0.1, 10.0))
        self.assertEqual(by_id["mask_gamma"]["default"], 5.0)
        self.assertEqual(by_id["window_meta"]["target_channel_filter"], [1, 3])

    def test_manifest_declares_the_process_class_and_full_image_preview(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        process = manifest["processes"][0]

        self.assertEqual(manifest["entry_point"], "hdr_multiscale_extension")
        self.assertEqual(process["class"], HdrMultiscaleExtension.__name__)
        self.assertEqual(process["capabilities"]["preview_scaling"], "full_only")
        self.assertTrue(issubclass(HdrMultiscaleExtension, ui.RTPreviewProcess))


if __name__ == "__main__":
    unittest.main()

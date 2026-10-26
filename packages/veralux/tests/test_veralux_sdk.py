import sys
import types
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_sdk as sdk  # noqa: E402


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


class PreservingFakeImage:
    def __init__(self, array):
        self.array = np.asarray(array)

    def to_numpy(self):
        return self.array

    def from_numpy(self, array):
        self.array = np.asarray(array)


class VeraLuxSdkTests(unittest.TestCase):
    def test_image_io_metadata_and_masks_use_shared_sdk_helpers(self):
        source = FakeImage(np.arange(27, dtype=np.float32).reshape(3, 3, 3))
        destination = FakeImage(np.zeros((3, 3, 3), dtype=np.float32))
        mask_handle = FakeImage(np.full((3, 3), 0.75, dtype=np.float32))

        read = sdk.read_image(source)
        sdk.write_image(destination, read * 0.5)
        mask = sdk.first_mask_array([mask_handle])
        dict_mask = sdk.first_mask_array({"protection": mask_handle})
        sdk.stamp_result(
            destination,
            extension_id="veralux_test",
            tool_name="Test Tool",
            upstream_version="1.2.3",
            attribution="Original VeraLux by Riccardo Paterniti.",
            extra_metadata={"veralux.test.value": 4.25},
        )

        self.assertEqual(read.shape, (3, 3, 3))
        self.assertEqual(destination.array.dtype, np.float32)
        self.assertTrue(np.allclose(destination.array, read * 0.5))
        self.assertTrue(np.allclose(mask, 0.75))
        self.assertTrue(np.allclose(dict_mask, 0.75))
        self.assertEqual(destination.metadata["afternight.extension"], "veralux_test")
        self.assertEqual(destination.metadata["veralux.tool"], "Test Tool")
        self.assertEqual(destination.metadata["veralux.upstream_version"], "1.2.3")
        self.assertEqual(destination.metadata["veralux.test.value"], "4.25")

    def test_write_image_scales_normalized_float_to_integer_destination(self):
        destination = PreservingFakeImage(np.zeros((2, 3), dtype=np.uint16))

        sdk.write_image(destination, np.asarray([[0.0, 0.5, 1.0], [0.25, 0.75, 2.0]], dtype=np.float32))

        self.assertEqual(destination.array.dtype, np.uint16)
        self.assertEqual(int(destination.array[0, 0]), 0)
        self.assertEqual(int(destination.array[0, 1]), 32767)
        self.assertEqual(int(destination.array[0, 2]), 65535)
        self.assertEqual(int(destination.array[1, 0]), 16383)
        self.assertEqual(int(destination.array[1, 1]), 49151)
        self.assertEqual(int(destination.array[1, 2]), 65535)

    def test_mark_result_nonlinear_writes_afterNight_processing_state(self):
        rgb = FakeImage(np.zeros((4, 5, 3), dtype=np.float32))
        rgb.metadata["ANBASIS"] = "linear-rgb"

        sdk.mark_result_nonlinear(rgb, "veralux-test-stretch")

        self.assertEqual(rgb.metadata["ANSTVER"], "1")
        self.assertEqual(rgb.metadata["ANLIN"], "nonlinear")
        self.assertEqual(rgb.metadata["ANBASIS"], "display-rgb")
        self.assertEqual(rgb.metadata["ANASRC"], "process")
        self.assertEqual(rgb.metadata["ANOP"], "veralux-test-stretch")

        mono = FakeImage(np.zeros((4, 5), dtype=np.float32))
        sdk.mark_result_nonlinear(mono, "veralux-test-mono")

        self.assertEqual(mono.metadata["ANLIN"], "nonlinear")
        self.assertEqual(mono.metadata["ANBASIS"], "monochrome")

    def test_settings_migration_and_preview_helpers_are_deterministic(self):
        params = {"old_gain": 0.8, "enabled": False}

        migrated = sdk.migrate_settings(
            params,
            defaults={"gain": 1.0, "enabled": True, "mode": "linear"},
            aliases={"gain": ("old_gain",)},
        )
        preview = sdk.downsample_for_preview(
            np.arange(4 * 6 * 3, dtype=np.float32).reshape(4, 6, 3),
            max_dimension=3,
        )
        stretched = sdk.autostretch_preview(np.linspace(0.1, 0.9, 16, dtype=np.float32).reshape(4, 4))

        self.assertEqual(migrated, {"gain": 0.8, "enabled": False, "mode": "linear"})
        self.assertEqual(preview.shape, (2, 3, 3))
        self.assertGreaterEqual(float(stretched.min()), 0.0)
        self.assertLessEqual(float(stretched.max()), 1.0)
        self.assertGreater(float(stretched[-1, -1]), float(stretched[0, 0]))

    def test_content_key_follows_content_not_the_buffer(self):
        rng = np.random.default_rng(3)
        image = rng.random((24, 32, 3), dtype=np.float32)
        key = sdk.content_key(image)

        self.assertEqual(sdk.content_key(image.copy()), key)

        one_pixel = image.copy()
        one_pixel[17, 29, 1] += 0.001
        self.assertNotEqual(sdk.content_key(one_pixel), key)
        self.assertNotEqual(sdk.content_key(image.astype(np.float64)), key)
        self.assertNotEqual(sdk.content_key(image[:, :-1]), key)
        self.assertNotEqual(sdk.content_key(np.moveaxis(image, -1, 0)), key)

    def test_content_key_samples_a_large_image_on_a_fixed_grid(self):
        image = np.zeros((40, 64), dtype=np.float32)
        key = sdk.content_key(image, sample_pixels=160)
        stride = key[2]

        self.assertEqual(stride, 4)
        sampled = image.copy()
        sampled[stride * 3, stride * 5] = 1.0
        self.assertNotEqual(sdk.content_key(sampled, sample_pixels=160), key)
        between = image.copy()
        between[1, 1] = 1.0
        self.assertEqual(sdk.content_key(between, sample_pixels=160), key)
        mono_chw = np.zeros((1, 40, 64), dtype=np.float32)
        self.assertEqual(sdk.content_key(mono_chw, sample_pixels=160)[2], 4)

    def test_frame_placement_reads_the_frame_properties(self):
        frame = types.SimpleNamespace(
            properties={"offset_x": 8, "offset_y": 7, "source_width": 24, "source_height": 20, "width": 6}
        )

        self.assertEqual(sdk.frame_placement(frame), (8, 7, 24, 20))
        self.assertIsNone(sdk.frame_placement(types.SimpleNamespace(properties={"offset_x": 8, "offset_y": 7})))
        self.assertIsNone(sdk.frame_placement(FakeImage(np.zeros((2, 2), dtype=np.float32))))

    def test_cut_to_frame_cuts_whole_image_arrays_in_every_layout(self):
        frame = types.SimpleNamespace(
            properties={"offset_x": 8, "offset_y": 7, "source_width": 24, "source_height": 20}
        )
        whole = np.arange(20 * 24, dtype=np.float32).reshape(20, 24)
        expected = whole[7:12, 8:14]

        self.assertTrue(np.array_equal(sdk.cut_to_frame(whole, frame, (5, 6)), expected))
        hwc = np.repeat(whole[..., np.newaxis], 3, axis=-1)
        self.assertTrue(np.array_equal(sdk.cut_to_frame(hwc, frame, (5, 6)), hwc[7:12, 8:14, :]))
        chw = np.moveaxis(hwc, -1, 0)
        self.assertTrue(np.array_equal(sdk.cut_to_frame(chw, frame, (5, 6)), chw[:, 7:12, 8:14]))

        frame_sized = np.ones((5, 6), dtype=np.float32)
        self.assertIs(sdk.cut_to_frame(frame_sized, frame, (5, 6)), frame_sized)
        other_resolution = np.ones((10, 12), dtype=np.float32)
        self.assertIs(sdk.cut_to_frame(other_resolution, frame, (5, 6)), other_resolution)
        self.assertIs(sdk.cut_to_frame(whole, types.SimpleNamespace(properties={}), (5, 6)), whole)
        outside = types.SimpleNamespace(
            properties={"offset_x": 20, "offset_y": 7, "source_width": 24, "source_height": 20}
        )
        self.assertIs(sdk.cut_to_frame(whole, outside, (5, 6)), whole)

    def test_star_mask_from_find_stars_uses_engine_star_positions(self):
        image = FakeImage(np.zeros((40, 48, 3), dtype=np.float32))
        calls = []

        def fake_find_stars(handle, **kwargs):
            calls.append((handle, kwargs))
            return [
                {"x": 12.0, "y": 16.0, "fwhm": 4.0},
                {"x": 35.0, "y": 26.0, "fwhm": 5.5},
            ]

        mask = sdk.star_mask_from_find_stars(
            image,
            finder=fake_find_stars,
            max_stars=7,
            radius_scale=1.5,
            min_radius=2.0,
            max_radius=9.0,
            params={"sensitivity": 0.7},
        )

        self.assertEqual(mask.shape, (40, 48))
        self.assertEqual(calls[0][0], image)
        self.assertEqual(calls[0][1]["max_stars"], 7)
        self.assertEqual(calls[0][1]["params"], {"sensitivity": 0.7})
        self.assertGreater(float(mask[16, 12]), 0.9)
        self.assertGreater(float(mask[26, 35]), 0.9)
        self.assertLess(float(mask[0, 0]), 0.05)

    def test_nox_star_mask_helper_returns_mask_and_median_fwhm(self):
        image = FakeImage(np.zeros((40, 48, 3), dtype=np.float32))
        calls = []

        def fake_find_stars(handle, **kwargs):
            calls.append((handle, kwargs))
            return [
                {"x": 12.0, "y": 16.0, "fwhm": 4.0},
                {"x": 35.0, "y": 26.0, "fwhm": 5.5},
            ]

        mask, median_fwhm = sdk.star_mask_and_median_fwhm_from_find_stars(
            image,
            finder=fake_find_stars,
            max_stars=9,
            radius_scale=1.8,
            min_radius=3.0,
            max_radius=24.0,
            params={"sensitivity": 0.5},
        )

        self.assertEqual(mask.shape, (40, 48))
        self.assertAlmostEqual(median_fwhm, 4.75)
        self.assertEqual(calls[0][0], image)
        self.assertEqual(calls[0][1]["max_stars"], 9)
        self.assertEqual(calls[0][1]["params"], {"sensitivity": 0.5})
        self.assertGreater(float(mask[16, 12]), 0.9)
        self.assertGreater(float(mask[26, 35]), 0.9)
        self.assertLess(float(mask[0, 0]), 0.05)


if __name__ == "__main__":
    unittest.main()

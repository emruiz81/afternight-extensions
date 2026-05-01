import sys
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


class VeraLuxSdkTests(unittest.TestCase):
    def test_image_io_metadata_and_masks_use_shared_sdk_helpers(self):
        source = FakeImage(np.arange(27, dtype=np.float32).reshape(3, 3, 3))
        destination = FakeImage(np.zeros((3, 3, 3), dtype=np.float32))
        mask_handle = FakeImage(np.full((3, 3), 0.75, dtype=np.float32))

        read = sdk.read_image(source)
        sdk.write_image(destination, read * 0.5)
        mask = sdk.first_mask_array([mask_handle])
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
        self.assertEqual(destination.metadata["afternight.extension"], "veralux_test")
        self.assertEqual(destination.metadata["veralux.tool"], "Test Tool")
        self.assertEqual(destination.metadata["veralux.upstream_version"], "1.2.3")
        self.assertEqual(destination.metadata["veralux.test.value"], "4.25")

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


if __name__ == "__main__":
    unittest.main()

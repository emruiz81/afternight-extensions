import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

try:
    import astropy  # noqa: F401
except ImportError:  # pragma: no cover - the package's tests/requirements.txt installs it
    raise unittest.SkipTest("Astropy is required: pip install -r packages/gaia_glow_subtraction/tests/requirements.txt")

import gaia_glow_subtraction_io as ggs_io  # noqa: E402
import synthetic_field  # noqa: E402


class FakeImage:
    def __init__(self, array, metadata=None):
        self.array = np.asarray(array)
        self.metadata = dict(metadata or {})

    def to_numpy(self):
        return self.array


class HeaderTests(unittest.TestCase):
    def test_raw_records_give_a_typed_header_with_every_history_card(self):
        cards = synthetic_field.wcs_cards()
        cards.append({"key": "HISTORY", "value": "Background extraction", "raw": "HISTORY Background extraction"})

        header = ggs_io.fits_header({"fits_cards": cards})

        self.assertEqual(header["CTYPE1"], "RA---TAN")
        self.assertIsInstance(header["CRPIX1"], float)
        self.assertIsInstance(header["STACKCNT"], int)
        self.assertEqual(ggs_io.history_from_header(header), ["Stacked in AfterNight", "Background extraction"])

    def test_cards_sent_as_json_text_are_read_too(self):
        header = ggs_io.fits_header({"fits_cards": json.dumps(synthetic_field.wcs_cards())})

        self.assertAlmostEqual(header["CD2_2"], 2.0 / 3600.0)

    def test_value_text_is_typed_when_no_raw_record_is_given(self):
        header = ggs_io.fits_header({"fits_header": {"CRPIX1": "384.5", "NAXIS": "2", "OBJECT": "'M42'", "X": "T"}})

        self.assertEqual(header["CRPIX1"], 384.5)
        self.assertEqual(header["NAXIS"], 2)
        self.assertEqual(header["OBJECT"], "M42")
        self.assertIs(header["X"], True)

    def test_an_image_without_cards_has_no_header(self):
        self.assertIsNone(ggs_io.fits_header({"FILENAME": "a.png"}))

    def test_keywords_follow_the_fits_cards(self):
        keywords = ggs_io.keywords_from_header(ggs_io.fits_header({"fits_cards": synthetic_field.wcs_cards()}))

        self.assertEqual(keywords.stackcnt, 40)
        self.assertEqual(keywords.exposure, 120.0)
        self.assertEqual(keywords.livetime, 4800.0)
        self.assertEqual(keywords.image_type, "Light")
        self.assertEqual(keywords.date_obs, datetime(2025, 12, 1, 21, 30))
        self.assertEqual(keywords.bayer_pattern, "")
        self.assertEqual(ggs_io.parse_date_obs("2025-12-01T21:30:00.250").microsecond, 250000)
        self.assertIsNone(ggs_io.parse_date_obs("tonight"))


class LayoutAndDetectionTests(unittest.TestCase):
    def test_planes_round_trip_mono_and_colour(self):
        mono = np.arange(12, dtype=np.float32).reshape(3, 4)
        colour = np.arange(36, dtype=np.float32).reshape(3, 4, 3)

        self.assertEqual(ggs_io.to_planes(mono).shape, (1, 3, 4))
        self.assertEqual(ggs_io.to_planes(colour).shape, (3, 3, 4))
        np.testing.assert_array_equal(ggs_io.from_planes(ggs_io.to_planes(mono), mono), mono)
        np.testing.assert_array_equal(ggs_io.from_planes(ggs_io.to_planes(colour), colour), colour)

    def test_detections_take_the_half_pixel_origin_off_without_a_flip(self):
        star = {"x": 10.5, "y": 20.5, "fwhm_x": 3.0, "fwhm_y": 4.0, "amplitude": 6553.5, "saturated": True}
        star["saturation"] = 65535.0

        detection = ggs_io.detection_from_star(star, 1.0 / 65535.0, 2)

        self.assertEqual((detection.x, detection.y), (10.0, 20.0))
        self.assertAlmostEqual(detection.fwhm, 3.5)
        self.assertAlmostEqual(detection.roundness, 0.75)
        self.assertAlmostEqual(detection.peak, 0.1)
        self.assertAlmostEqual(detection.sat, 1.0)
        self.assertTrue(detection.saturated)
        self.assertEqual(detection.channel, 2)

    def test_detections_ask_each_channel_of_a_colour_image(self):
        calls = []

        def finder(image, *, channel, max_stars):
            calls.append((channel, max_stars))
            return [{"x": 1.5, "y": 1.5, "fwhm_x": 3.0, "fwhm_y": 3.0, "amplitude": 0.2}]

        io = ggs_io.AfterNightIO(FakeImage(np.zeros((8, 8, 3))), log_fn=lambda *a: None, finder=finder)

        found = [io.detections(c, 1.0, 3, 8) for c in range(3)]

        self.assertEqual([channel for channel, _ in calls], [0, 1, 2])
        self.assertTrue(all(len(d) == 1 for d in found))
        self.assertTrue(io.findstar_ran)


class ConfigurationTests(unittest.TestCase):
    def test_config_maps_the_siril_catalogue_settings_and_nothing_else(self):
        io = ggs_io.AfterNightIO(
            FakeImage(np.zeros((4, 4))),
            log_fn=lambda *a: None,
            settings={"siril_astro_catalogue": "astro.dat", "siril_xp_catalogue_dir": "xp"},
        )

        self.assertEqual(io.config("core", "catalogue_gaia_astro"), "astro.dat")
        self.assertEqual(io.config("core", "catalogue_gaia_photo"), "xp")
        self.assertIsNone(io.config("photometry", "oscsensorpref"))
        self.assertIsNone(io.systemdatadir())

    def test_data_dir_setting_holds_the_cache_and_the_last_output_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            io = ggs_io.AfterNightIO(FakeImage(np.zeros((4, 4))), log_fn=lambda *a: None, settings={"data_dir": tmp})

            self.assertEqual(io.userdatadir(), tmp)
            self.assertIsNone(io.load_last_fingerprint())
            io.save_last_fingerprint({"amount": 0.5})
            self.assertEqual(io.load_last_fingerprint(), {"amount": 0.5})

    def test_default_data_dir_is_a_per_user_cache_folder(self):
        path = ggs_io.default_data_dir()

        self.assertTrue(path.endswith("gaia_glow_subtraction"))
        self.assertIn("extensions", path)

    def test_image_info_reports_bit_depth_channels_and_file(self):
        metadata = {"fits_cards": synthetic_field.wcs_cards(), "FILENAME": "/data/m42.fits"}
        io = ggs_io.AfterNightIO(FakeImage(np.zeros((8, 8, 3), np.uint16), metadata), log_fn=lambda *a: None)

        info = io.image_info()

        self.assertEqual((info["nc"], info["orig_bitpix"], info["filename"]), (3, 16, "/data/m42.fits"))
        self.assertEqual(info["stats"], [None, None, None])
        self.assertIn("CTYPE1", info["header"])


if __name__ == "__main__":
    unittest.main()

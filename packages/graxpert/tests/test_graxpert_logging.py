import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import afternight  # noqa: E402
from graxpert_extension import (  # noqa: E402
    GraXpertBackgroundExtension,
    GraXpertDeconvolutionExtension,
    GraXpertDenoiseExtension,
    _metadata_snapshot,
    _restore_original_metadata,
)


class FakeImage:
    def __init__(self, metadata=None):
        self.metadata = dict(metadata or {})

    def set_metadata(self, key, value):
        self.metadata[str(key)] = str(value)


class GraXpertLoggingTests(unittest.TestCase):
    def setUp(self):
        self._original_log_info = afternight.log_info
        self.messages = []

        def capture_info(message, component="extension"):
            self.messages.append((str(component), str(message)))

        afternight.log_info = capture_info

    def tearDown(self):
        afternight.log_info = self._original_log_info

    def log_text(self):
        return "\n".join(message for _component, message in self.messages)

    def test_each_process_launch_hook_emits_banner_with_credits(self):
        cases = [
            (GraXpertBackgroundExtension, "GraXpert AI - Background Extraction"),
            (GraXpertDenoiseExtension, "GraXpert AI - Denoise"),
            (GraXpertDeconvolutionExtension, "GraXpert AI - Deconvolution"),
        ]

        for extension_class, title in cases:
            with self.subTest(title=title):
                self.messages.clear()
                extension_class(None).on_process_launch()
                text = self.log_text()
                self.assertIn("##############################################", text)
                self.assertIn(title, text)
                self.assertIn("Wrapped process authors: GraXpert Development Team", text)
                self.assertIn("AfterNight extension maintainer: Ezequiel Ruiz", text)
                self.assertIn("https://github.com/Steffenhir/GraXpert", text)

    def test_each_process_window_meta_uses_process_specific_header(self):
        cases = [
            (GraXpertBackgroundExtension, "GraXpert AI - Background Extraction", "background-model artifact"),
            (GraXpertDenoiseExtension, "GraXpert AI - Denoise", "strength"),
            (GraXpertDeconvolutionExtension, "GraXpert AI - Deconvolution", "FWHM controls"),
        ]

        for extension_class, title, detail in cases:
            with self.subTest(title=title):
                params = extension_class(None).get_params()
                meta = params[0]

                self.assertEqual(meta["id"], "window_meta")
                self.assertIn(title, meta["header_description"])
                self.assertIn(detail, meta["header_description"])
                self.assertIn("shared GraXpert environment", meta["header_description"])

    def test_gpu_override_is_not_exposed_for_background_extraction(self):
        process_params = {
            extension_class.__name__: {param.get("id") for param in extension_class(None).get_params()}
            for extension_class in (
                GraXpertBackgroundExtension,
                GraXpertDenoiseExtension,
                GraXpertDeconvolutionExtension,
            )
        }

        self.assertNotIn("gpu_enabled", process_params["GraXpertBackgroundExtension"])
        self.assertIn("gpu_enabled", process_params["GraXpertDenoiseExtension"])
        self.assertIn("gpu_enabled", process_params["GraXpertDeconvolutionExtension"])

        settings_params = {
            extension_class.__name__: {param.get("id") for param in extension_class(None).get_settings_params()}
            for extension_class in (
                GraXpertBackgroundExtension,
                GraXpertDenoiseExtension,
                GraXpertDeconvolutionExtension,
            )
        }

        self.assertNotIn("gpu_enabled", settings_params["GraXpertBackgroundExtension"])
        self.assertIn("gpu_enabled", settings_params["GraXpertDenoiseExtension"])
        self.assertIn("gpu_enabled", settings_params["GraXpertDeconvolutionExtension"])

    def test_metadata_restore_preserves_original_science_keys_only(self):
        source = FakeImage(
            {
                "FILENAME": "original-light.fit",
                "FILTER": "Ha",
                "EXPTIME": 300.0,
                "CRVAL1": "187.5",
                "CRVAL2": "-45.5",
                "BITPIX": "-32",
                "NAXIS1": "640",
                "fits_header": {
                    "TELESCOP": "Esprit 100",
                    "NAXIS2": "480",
                },
                "fits_cards": [{"key": "OBJECT", "value": "M31"}],
                "astrometry": {"solver": "synthetic"},
            }
        )
        destination = FakeImage({"FILTER": "GraXpert"})

        snapshot = _metadata_snapshot(source)
        source.metadata["FILENAME"] = "temporary.fits"
        _restore_original_metadata(destination, snapshot, component="test.graxpert")

        self.assertEqual(destination.metadata["FILENAME"], "original-light.fit")
        self.assertEqual(destination.metadata["FILTER"], "Ha")
        self.assertEqual(destination.metadata["EXPTIME"], "300.0")
        self.assertEqual(destination.metadata["CRVAL1"], "187.5")
        self.assertEqual(destination.metadata["CRVAL2"], "-45.5")
        self.assertEqual(destination.metadata["TELESCOP"], "Esprit 100")
        self.assertEqual(destination.metadata["OBJECT"], "M31")
        self.assertNotIn("BITPIX", destination.metadata)
        self.assertNotIn("NAXIS1", destination.metadata)
        self.assertNotIn("NAXIS2", destination.metadata)
        self.assertNotIn("astrometry", destination.metadata)


if __name__ == "__main__":
    unittest.main()

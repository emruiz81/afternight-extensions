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
)


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


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import afternight  # noqa: E402
from cosmic_clarity_extension import (  # noqa: E402
    CosmicClarityDarkStarExtension,
    CosmicClarityDenoiseExtension,
    CosmicClaritySharpeningExtension,
    CosmicClaritySuperResExtension,
)


class CosmicClarityLoggingTests(unittest.TestCase):
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
            (CosmicClarityDenoiseExtension, "Cosmic Clarity - Denoise"),
            (CosmicClarityDarkStarExtension, "Cosmic Clarity - Dark Star"),
            (CosmicClaritySharpeningExtension, "Cosmic Clarity - Sharpening"),
            (CosmicClaritySuperResExtension, "Cosmic Clarity - Super Resolution"),
        ]

        for extension_class, title in cases:
            with self.subTest(title=title):
                self.messages.clear()
                extension_class(None).on_process_launch()
                text = self.log_text()
                self.assertIn("##############################################", text)
                self.assertIn(title, text)
                self.assertIn("Wrapped process author: Seti Astro", text)
                self.assertIn("AfterNight extension maintainer: Ezequiel Ruiz", text)
                self.assertIn("https://github.com/setiastro/cosmicclarity", text)

    def test_each_process_window_meta_uses_process_specific_header(self):
        cases = [
            (CosmicClarityDenoiseExtension, "Seti Astro Cosmic Clarity - Denoise", "full-image noise"),
            (CosmicClarityDarkStarExtension, "Seti Astro Cosmic Clarity - Dark Star", "starless result"),
            (CosmicClaritySharpeningExtension, "Seti Astro Cosmic Clarity - Sharpening", "PSF detection"),
            (CosmicClaritySuperResExtension, "Seti Astro Cosmic Clarity - Super Resolution", "Upscale"),
        ]

        for extension_class, title, detail in cases:
            with self.subTest(title=title):
                params = extension_class(None).get_params()
                meta = params[0]

                self.assertEqual(meta["id"], "window_meta")
                self.assertIn(title, meta["header_description"])
                self.assertIn(detail, meta["header_description"])
                self.assertIn("external suite folder", meta["header_description"])


if __name__ == "__main__":
    unittest.main()

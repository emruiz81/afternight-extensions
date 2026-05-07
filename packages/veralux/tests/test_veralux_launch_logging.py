import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_sdk as sdk  # noqa: E402
from veralux_alchemy_adapter import VeraLuxAlchemyExtension  # noqa: E402
from veralux_curves_adapter import VeraLuxCurvesExtension  # noqa: E402
from veralux_hypermetric_stretch_adapter import VeraLuxHyperMetricStretchExtension  # noqa: E402
from veralux_nox_adapter import VeraLuxNoxExtension  # noqa: E402
from veralux_revela_adapter import VeraLuxRevelaExtension  # noqa: E402
from veralux_silentium_adapter import VeraLuxSilentiumExtension  # noqa: E402
from veralux_starcomposer_adapter import VeraLuxStarComposerExtension  # noqa: E402
from veralux_vectra_adapter import VeraLuxVectraExtension  # noqa: E402


class VeraLuxLaunchLoggingTests(unittest.TestCase):
    def setUp(self):
        self._original_log_info = sdk.log_info
        self.messages = []

        def capture_info(message, *, component):
            self.messages.append((str(component), str(message)))

        sdk.log_info = capture_info

    def tearDown(self):
        sdk.log_info = self._original_log_info

    def log_text(self):
        return "\n".join(message for _component, message in self.messages)

    def test_each_native_process_launch_hook_emits_original_style_banner(self):
        cases = [
            (VeraLuxAlchemyExtension, "VeraLux - Alchemy", "Linear-Phase Narrowband Normalization & Mixing"),
            (VeraLuxHyperMetricStretchExtension, "VeraLux - HyperMetric Stretch", "Photometric Hyperbolic Stretch Engine"),
            (VeraLuxCurvesExtension, "VeraLux - Curves", "Spline-Based Photometric Sculpting Engine"),
            (VeraLuxRevelaExtension, "VeraLux - Revela", "Photometric Local Contrast & Texture Engine"),
            (VeraLuxVectraExtension, "VeraLux - Vectra", "Vector Color Grading Engine"),
            (VeraLuxSilentiumExtension, "VeraLux - Silentium", "Linear-Phase Noise Suppression Engine"),
            (VeraLuxNoxExtension, "VeraLux - Nox", "Physically-Faithful Photometric Gradient Reduction"),
            (VeraLuxStarComposerExtension, "VeraLux - StarComposer", "High-Fidelity Star Reconstruction Engine"),
        ]

        for extension_class, title, subtitle in cases:
            with self.subTest(title=title):
                self.messages.clear()
                extension_class(None).on_process_launch()
                text = self.log_text()
                self.assertIn("##############################################", text)
                self.assertIn(title, text)
                self.assertIn(subtitle, text)
                self.assertIn("Author: Riccardo Paterniti (2025)", text)


if __name__ == "__main__":
    unittest.main()

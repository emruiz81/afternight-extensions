import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import veralux_alchemy_core as alchemy_core  # noqa: E402
import veralux_alchemy_ui as alchemy_ui  # noqa: E402
import veralux_curves_core as curves_core  # noqa: E402
import veralux_curves_ui as curves_ui  # noqa: E402
import veralux_hypermetric_stretch_core as hms_core  # noqa: E402
import veralux_hypermetric_stretch_ui as hms_ui  # noqa: E402
import veralux_nox_core as nox_core  # noqa: E402
import veralux_nox_ui as nox_ui  # noqa: E402
import veralux_revela_core as revela_core  # noqa: E402
import veralux_revela_ui as revela_ui  # noqa: E402
import veralux_silentium_core as silentium_core  # noqa: E402
import veralux_silentium_ui as silentium_ui  # noqa: E402
import veralux_starcomposer_core as starcomposer_core  # noqa: E402
import veralux_starcomposer_ui as starcomposer_ui  # noqa: E402
import veralux_vectra_core as vectra_core  # noqa: E402
import veralux_vectra_ui as vectra_ui  # noqa: E402


class VeraLuxAttributionTests(unittest.TestCase):
    def test_ui_attribution_includes_source_version_for_each_port(self):
        cases = [
            ("Alchemy", alchemy_core.UPSTREAM_VERSION, alchemy_ui),
            ("Curves", curves_core.UPSTREAM_VERSION, curves_ui),
            ("HyperMetric Stretch", hms_core.UPSTREAM_VERSION, hms_ui),
            ("Nox", nox_core.UPSTREAM_VERSION, nox_ui),
            ("Revela", revela_core.UPSTREAM_VERSION, revela_ui),
            ("Silentium", silentium_core.UPSTREAM_VERSION, silentium_ui),
            ("StarComposer", starcomposer_core.UPSTREAM_VERSION, starcomposer_ui),
            ("Vectra", vectra_core.UPSTREAM_VERSION, vectra_ui),
        ]

        for tool_name, upstream_version, ui_module in cases:
            with self.subTest(tool_name=tool_name):
                text = ui_module.ATTRIBUTION_TEXT
                self.assertIn(f"VeraLux {tool_name}", text)
                self.assertIn(f"source version {upstream_version}", text)
                self.assertIn("Riccardo Paterniti", text)
                defs = ui_module.parameter_defs()
                by_id = {item.get("id"): item for item in defs if isinstance(item, dict)}
                self.assertEqual(by_id["attribution"]["text"], text)


if __name__ == "__main__":
    unittest.main()

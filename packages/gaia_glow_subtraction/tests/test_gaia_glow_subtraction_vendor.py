"""The vendored core is the upstream script's sections 0 to 13, with only its sirilpy import block replaced."""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = TEST_ROOT.parent / "package"
REPO_ROOT = TEST_ROOT.parents[2]
CORE = PACKAGE_ROOT / "gaia_glow_subtraction_core.py"
MARKER = "# --- vendored upstream text below ---"
VENDORED_LINES = 7400
IMPORT_BLOCK = (122, 127)


def upstream_text(upstream):
    checkout = Path(os.environ.get("SIRIL_SCRIPTS_CHECKOUT", REPO_ROOT.parent / "siril-scripts"))
    if shutil.which("git") is None or not (checkout / ".git").exists():
        raise unittest.SkipTest(f"Missing siril-scripts checkout: {checkout}; set SIRIL_SCRIPTS_CHECKOUT")
    source = upstream["sources"][0]
    result = subprocess.run(
        ["git", "-C", str(checkout), "show", f"{upstream['upstream_commit']}:{source['original_path']}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise unittest.SkipTest(f"The checkout lacks {upstream['upstream_commit']}: fetch it to run this test")
    return result.stdout.decode("utf-8")


class GaiaGlowVendorTests(unittest.TestCase):
    def test_vendored_core_is_the_upstream_text(self):
        upstream = json.loads((PACKAGE_ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
        original = upstream_text(upstream).split("\n")
        vendored = CORE.read_text(encoding="utf-8").split("\n")
        body = vendored[vendored.index(MARKER) + 1 :]

        start, end = IMPORT_BLOCK
        self.assertEqual(original[start - 1], "import sirilpy as s")
        self.assertEqual(original[VENDORED_LINES], "# " + "=" * 75)
        replaced = [line for line in body if line.startswith("# AfterNight port:") or line.startswith("# called s.")]
        self.assertEqual(len(replaced), 2)
        kept = body[: start - 1] + body[start - 1 + 3 :]
        self.assertEqual(kept[:-1], original[: start - 1] + original[end:VENDORED_LINES])

    def test_vendored_core_does_not_import_sirilpy_or_qt(self):
        text = CORE.read_text(encoding="utf-8")
        body = text[text.index(MARKER) :]

        for name in ("import sirilpy", "from sirilpy", "PyQt6", "ensure_installed("):
            self.assertNotIn(f"\n{name}", body.replace("    ", ""))


if __name__ == "__main__":
    unittest.main()

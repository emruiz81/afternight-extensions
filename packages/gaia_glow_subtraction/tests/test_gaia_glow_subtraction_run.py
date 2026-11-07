"""End-to-end runs of the vendored pipeline through the AfterNight adapter, on synthetic fields, with no network."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


TEST_ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = TEST_ROOT.parent / "package"
APP_REPO = TEST_ROOT.parents[3] / "afternight"
sys.path.insert(0, str(TEST_ROOT))
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

try:
    import astropy  # noqa: F401
    import astropy_healpix  # noqa: F401
except ImportError:  # pragma: no cover - the package's tests/requirements.txt installs them
    raise unittest.SkipTest("Astropy is required: pip install -r packages/gaia_glow_subtraction/tests/requirements.txt")

from afternight import registration, ui  # noqa: E402
import gaia_glow_subtraction_core as core  # noqa: E402
import gaia_glow_subtraction_ui as ggs_ui  # noqa: E402
import synthetic_field as field  # noqa: E402
from gaia_glow_subtraction_extension import (  # noqa: E402
    GaiaGlowSubtractionExtension,
    glow_params_from,
    output_array,
)


class FakeImage:
    def __init__(self, array, metadata=None):
        self.array = np.asarray(array)
        self.metadata = dict(metadata or {})

    def to_numpy(self):
        return self.array

    def from_numpy(self, array):
        self.array = np.asarray(array)

    def set_metadata(self, key, value):
        self.metadata[str(key)] = str(value)


class FakeProgress:
    def __init__(self, cancelled=False):
        self.value = 0.0
        self.cancelled = cancelled

    def set_text(self, text):
        self.text = str(text)

    def set_value(self, value):
        self.value = float(value)

    def is_cancelled(self):
        return self.cancelled


class UnreachableRemote:
    """The remote Gaia mirror, as the core sees it when it cannot be reached."""

    def __init__(self, *args, **kwargs):
        self.unreachable = True


class FieldCatalogue:
    """A catalogue holding exactly the synthetic field's stars, with temperatures instead of XP spectra."""

    def __init__(self, ctx, astro_path, photo_dir, cache_dir, catsource="auto"):
        self.supplement = core.BrightStarSupplement()
        self.sources_used = {"positions": {"synthetic field"}, "spectra": set()}
        self.position_source = "A"

    def summary(self):
        return "synthetic field", "none"

    def positions(self, ra_c, dec_c, radius_deg, epoch):
        ra, dec, g = field.catalogue()
        return core.StarTable(ra=ra, dec=dec, g=g, teff=np.full(g.size, 5800.0), src=np.full(g.size, "A"))

    def attach_spectra(self, table, need):
        return table

    def add_supplement(self, table, *args):
        return table, {"cone": 0, "matched": 0, "route_b": 0, "added": 0, "dropped": 0}


def glow_left(result, clean, region):
    return float(np.mean(np.abs(np.asarray(result, np.float32) - clean)[region]))


class GaiaGlowRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = field.render()
        cls.clean = field.render(glow=False)
        cls.region = field.glow_region()
        cls.metadata = {"fits_cards": field.wcs_cards(), "FILENAME": ""}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logs = []
        patches = [
            mock.patch.object(core, "RemoteXpSource", UnreachableRemote),
            mock.patch.object(core, "load_bright_table", lambda *args, **kwargs: []),
            mock.patch.object(registration, "find_stars", field.find_stars),
            mock.patch("afternight.log_info", lambda message, component="": self.logs.append(("info", message))),
            mock.patch("afternight.log_warning", lambda message, component="": self.logs.append(("warn", message))),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_extension(self, image, params, *, metadata=None, progress=None):
        extension = GaiaGlowSubtractionExtension(None)
        extension.settings.set("data_dir", self.tmp.name)
        dst = FakeImage(np.zeros_like(image))
        extension.execute(
            "target",
            FakeImage(image, self.metadata if metadata is None else metadata),
            dst,
            params,
            progress or FakeProgress(),
        )
        return dst

    def test_offline_run_removes_most_of_the_glow_around_bright_stars(self):
        dst = self.run_extension(self.image, {"offline_ok": True})

        self.assertEqual(dst.array.dtype, np.float32)
        self.assertEqual(dst.array.shape, self.image.shape)
        before = glow_left(self.image, self.clean, self.region)
        self.assertLess(glow_left(dst.array, self.clean, self.region), 0.75 * before)
        self.assertEqual(dst.metadata["afternight.extension"], "gaia_glow_subtraction")
        self.assertTrue(dst.metadata["gaia_glow_subtraction.label"].startswith("GaiaGlowSub"))
        self.assertTrue((Path(self.tmp.name) / "last_output.json").is_file())
        self.assertTrue(any("IN-FRAME STARS ONLY" in message for _, message in self.logs))

    def test_offline_run_needs_continue_without_a_catalogue(self):
        with self.assertRaisesRegex(RuntimeError, "No Gaia catalogue"):
            self.run_extension(self.image, {})

    def test_catalogue_run_matches_the_stars_and_calibrates_on_them(self):
        with mock.patch.object(core, "CatalogueService", FieldCatalogue):
            dst = self.run_extension(self.image, {})

        before = glow_left(self.image, self.clean, self.region)
        self.assertLess(glow_left(dst.array, self.clean, self.region), 0.75 * before)
        positions = next(message for _, message in self.logs if message.startswith("Star positions:"))
        self.assertRegex(positions, r"RMS 0\.[0-4]\d px")

    def test_uint16_images_come_back_in_their_sample_type(self):
        source = (self.image * 65535.0).astype(np.uint16)

        dst = self.run_extension(source, {"offline_ok": True})

        self.assertEqual(dst.array.dtype, np.uint16)
        self.assertEqual(dst.array.shape, source.shape)

    def test_running_again_on_the_output_is_refused_unless_forced(self):
        first = self.run_extension(self.image, {"offline_ok": True})

        with self.assertRaisesRegex(RuntimeError, "subtracts the glow twice"):
            self.run_extension(first.array, {"offline_ok": True})
        self.run_extension(first.array, {"offline_ok": True, "force": True})
        self.assertTrue(any("proceeding despite" in message for _, message in self.logs))

    def test_unsolved_images_are_refused(self):
        metadata = {"fits_cards": field.wcs_cards(solved=False)}

        with self.assertRaisesRegex(RuntimeError, "not plate solved"):
            self.run_extension(self.image, {"offline_ok": True}, metadata=metadata)

    def test_cancel_ends_the_run(self):
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.run_extension(self.image, {"offline_ok": True}, progress=FakeProgress(cancelled=True))

    def test_glow_model_opens_and_measured_psf_is_saved(self):
        psf_path = os.path.join(self.tmp.name, "field.ggspsf")
        with mock.patch.object(ui, "open_image") as open_image:
            dst = self.run_extension(self.image, {"offline_ok": True, "glowimage": True, "savepsf": psf_path})

        glow = open_image.call_args.args[0]
        self.assertEqual(open_image.call_args.kwargs["title"], "Gaia Glow Model")
        self.assertEqual(glow.shape, self.image.shape)
        np.testing.assert_allclose(dst.array + glow, self.image, atol=2e-6)
        saved = json.loads(Path(psf_path).read_text(encoding="utf-8"))
        self.assertEqual(saved["generator"], f"GaiaGlowSubtraction {core.VERSION}")
        self.assertEqual(len(saved["channels"]), 1)

        with self.assertRaisesRegex(RuntimeError, "already exists"):
            self.run_extension(self.image, {"offline_ok": True, "savepsf": psf_path, "force": True})


class GaiaGlowParameterTests(unittest.TestCase):
    def test_defaults_are_the_upstream_command_line_defaults(self):
        self.assertEqual(glow_params_from({}), core.GlowParams())

    def test_values_are_held_to_the_upstream_ranges(self):
        params = glow_params_from(
            {"amount": 3, "protect": 0, "bgorder": 9, "maxradius": 1, "faintG": 40, "download_limit_auto": False}
        )

        self.assertEqual((params.amount, params.protect, params.bgorder, params.maxradius), (1.0, 1e-4, 3, 5.0))
        self.assertEqual((params.faintG, params.maxdownload), (16.0, 500.0))

    def test_psf_file_mode_needs_a_path_and_drops_the_save_path(self):
        with self.assertRaisesRegex(ValueError, "PSF file"):
            glow_params_from({"psf_mode": "file"})
        params = glow_params_from({"psf_mode": "file", "psf_file": "clean.ggspsf", "savepsf": "x.ggspsf"})
        self.assertEqual((params.psf, params.savepsf), ("clean.ggspsf", ""))

    def test_unknown_choices_are_refused(self):
        with self.assertRaisesRegex(ValueError, "passes"):
            glow_params_from({"passes": "3"})
        with self.assertRaisesRegex(ValueError, "catalogue source"):
            glow_params_from({"catsource": "web"})

    def test_output_keeps_integer_sample_types(self):
        planes = np.array([[[0.0, 0.5, 1.2]]], np.float32)

        self.assertEqual(output_array(planes, np.uint16, 1.0).tolist(), [[[0, 32768, 65535]]])
        np.testing.assert_allclose(output_array(planes, np.float32, 2.0), planes * 2.0)


class GaiaGlowSchemaTests(unittest.TestCase):
    def test_schema_offers_every_parameter_with_its_upstream_range(self):
        by_id = {item["id"]: item for item in ggs_ui.parameter_defs()}
        defaults = core.GlowParams()

        for name in ("amount", "tolerance", "protect", "brightprotect", "faintG", "maxradius"):
            with self.subTest(param=name):
                self.assertEqual(by_id[name]["default"], getattr(defaults, name))
        self.assertEqual((by_id["protect"]["min"], by_id["protect"]["max"]), (1e-4, 1.0))
        self.assertEqual((by_id["bgorder"]["min"], by_id["bgorder"]["max"]), (1, 3))
        self.assertEqual(by_id["faintG"]["enabled_when"], {"param": "auto", "equals": False})
        self.assertFalse(by_id["window_meta"]["preview_area"])
        self.assertEqual(
            [item["id"] for item in ggs_ui.settings_defs()],
            ["data_dir", "siril_astro_catalogue", "siril_xp_catalogue_dir"],
        )

    def test_manifest_declares_an_apply_only_process_with_a_locked_environment(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        process = manifest["processes"][0]

        self.assertEqual(process["class"], GaiaGlowSubtractionExtension.__name__)
        self.assertNotIn("preview", process["capabilities"])
        self.assertEqual(manifest["dependencies"]["requirements_file"], "requirements.lock")
        self.assertEqual(manifest["dependencies"]["bundled_runtime_packages"], ["numpy", "scipy"])
        self.assertTrue(issubclass(GaiaGlowSubtractionExtension, ui.ProcessWindow))


if __name__ == "__main__":
    unittest.main()

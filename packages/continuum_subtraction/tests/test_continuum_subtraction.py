import json
import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

from afternight import ui  # noqa: E402
import continuum_subtraction_core as core  # noqa: E402
import continuum_subtraction_ui as cs_ui  # noqa: E402
from continuum_subtraction_extension import (  # noqa: E402
    ContinuumBlendExtension,
    ContinuumSubtractionExtension,
    blend_weights,
)


class FakeImage:
    def __init__(self, array):
        self.array = np.asarray(array)
        self.metadata = {}

    def to_numpy(self):
        return self.array

    def from_numpy(self, array):
        self.array = np.asarray(array)

    def set_metadata(self, key, value):
        self.metadata[str(key)] = str(value)


class FakeProgress:
    def __init__(self):
        self.value = 0.0
        self.cancelled = False

    def set_text(self, text):
        self.text = str(text)

    def set_value(self, value):
        self.value = float(value)

    def is_cancelled(self):
        return self.cancelled


TRUE_C = 0.3


def synthetic_pair(size=96, true_c=TRUE_C, seed=11, hii_on_galaxy=True):
    """A linear Ha frame holding emission plus ``true_c`` times the continuum, and the continuum frame itself.

    With ``hii_on_galaxy`` the HII regions sit on the galaxy, so they correlate with the continuum.
    """

    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    galaxy = 0.20 * np.exp(-(((x - 48.0) ** 2) / (2.0 * 22.0**2) + ((y - 48.0) ** 2) / (2.0 * 12.0**2)))
    stars = sum(
        0.5 * np.exp(-(((x - sx) ** 2) + ((y - sy) ** 2)) / (2.0 * 1.4**2))
        for sx, sy in ((12, 15), (80, 22), (30, 70), (70, 84), (55, 40))
    )
    continuum = 0.05 + galaxy + stars + rng.normal(0.0, 0.002, (size, size))
    hii_centres = ((40, 44), (58, 52), (47, 58)) if hii_on_galaxy else ((10, 50), (85, 60), (50, 8))
    hii = sum(0.08 * np.exp(-(((x - hx) ** 2) + ((y - hy) ** 2)) / (2.0 * 2.5**2)) for hx, hy in hii_centres)
    emission = 0.02 + hii + true_c * continuum + rng.normal(0.0, 0.002, (size, size))
    return emission.astype(np.float32), continuum.astype(np.float32)


def galaxy_region(size=96):
    region = np.zeros((size, size), dtype=bool)
    region[24:72, 16:80] = True
    return region


class ContinuumSubtractionCoreTests(unittest.TestCase):
    def test_estimate_recovers_the_continuum_factor_when_emission_is_independent_of_it(self):
        emission, continuum = synthetic_pair(hii_on_galaxy=False)

        c, details = core.compute_c(emission, continuum, selection=galaxy_region())

        self.assertAlmostEqual(c, TRUE_C, delta=0.005)
        self.assertFalse(details["fit_failed"])
        self.assertEqual(len(details["scale_factors"]), 40)

    def test_emission_that_follows_the_continuum_is_partly_subtracted_with_it(self):
        # Minimizing the AAD also flattens emission lying on continuum structure, so c comes out high; this is the
        # method's assumption, kept from upstream, and why the region should hold the subject's continuum.
        emission, continuum = synthetic_pair(hii_on_galaxy=True)

        c, _ = core.compute_c(emission, continuum, selection=galaxy_region())

        self.assertGreater(c, TRUE_C + 0.03)

    def test_rectangle_and_matching_mask_select_the_same_pixels(self):
        emission, continuum = synthetic_pair()

        by_rectangle, _ = core.compute_c(emission, continuum, selection=(16, 24, 64, 48))
        by_mask, _ = core.compute_c(emission, continuum, selection=galaxy_region())

        self.assertAlmostEqual(by_rectangle, by_mask, places=6)

    def test_negative_correlation_falls_back_to_zero_instead_of_failing(self):
        emission, continuum = synthetic_pair(true_c=-0.9)

        c, details = core.compute_c(emission, continuum)

        self.assertTrue(details["fit_failed"])
        self.assertEqual(c, 0.0)

    def test_subtract_and_blend_follow_the_upstream_formulas(self):
        emission, continuum = synthetic_pair(32)
        rgb = np.stack([continuum, continuum * 0.9, continuum * 0.8], axis=-1)

        cs = core.subtract_continuum(emission, continuum, 0.25)
        blended = core.blend_into_rgb(rgb, cs, 2.0, (1.0, 0.5, 0.0))

        np.testing.assert_allclose(cs, emission - np.float32(0.25) * continuum, rtol=1e-6)
        centred = cs - np.median(cs)
        np.testing.assert_allclose(blended[..., 0], rgb[..., 0] + centred * 2.0, rtol=1e-5, atol=1e-7)
        np.testing.assert_allclose(blended[..., 1], rgb[..., 1] + centred * 2.0 * 0.5, rtol=1e-5, atol=1e-7)
        np.testing.assert_array_equal(blended[..., 2], rgb[..., 2])


class ContinuumSubtractionAdapterTests(unittest.TestCase):
    def run_subtraction(self, emission, continuum, params, *, masks=None, extension=None, preview=False):
        extension = extension or ContinuumSubtractionExtension(None)
        dst = FakeImage(np.zeros_like(emission))
        settings = {"_continuum_image": FakeImage(continuum), **params}
        if preview:
            extension.execute_preview("target", FakeImage(emission), dst, settings, FakeProgress(), masks=masks)
        else:
            extension.execute("target", FakeImage(emission), dst, settings, FakeProgress(), masks=masks)
        return dst

    def test_estimated_c_is_applied_and_recorded(self):
        emission, continuum = synthetic_pair()

        dst = self.run_subtraction(emission, continuum, {"estimate_c": True})

        c, _ = core.compute_c(emission, continuum)
        np.testing.assert_allclose(dst.array, core.subtract_continuum(emission, continuum, c), atol=1e-7)
        self.assertEqual(dst.metadata["continuum_subtraction.c"], f"{c:.6f}")
        self.assertEqual(dst.metadata["afternight.extension"], "continuum_subtraction")

    def test_painted_region_drives_the_estimate(self):
        emission, continuum = synthetic_pair()
        region = galaxy_region()
        params = {"estimate_c": True, "use_region_mask": True}

        dst = self.run_subtraction(emission, continuum, params, masks=[region.astype(np.float32)])

        c, _ = core.compute_c(emission, continuum, selection=region)
        self.assertEqual(dst.metadata["continuum_subtraction.c"], f"{c:.6f}")

    def test_region_is_ignored_until_it_is_switched_on(self):
        emission, continuum = synthetic_pair()

        dst = self.run_subtraction(emission, continuum, {"estimate_c": True}, masks=[galaxy_region()])

        c, _ = core.compute_c(emission, continuum)
        self.assertEqual(dst.metadata["continuum_subtraction.c"], f"{c:.6f}")

    def test_manual_c_skips_the_estimate(self):
        emission, continuum = synthetic_pair()

        with mock.patch.object(core, "compute_c", side_effect=AssertionError("estimated")):
            dst = self.run_subtraction(emission, continuum, {"estimate_c": False, "c": 0.4})

        np.testing.assert_allclose(dst.array, core.subtract_continuum(emission, continuum, 0.4), atol=1e-7)

    def test_previews_of_unchanged_images_reuse_the_estimate(self):
        emission, continuum = synthetic_pair()
        extension = ContinuumSubtractionExtension(None)

        with mock.patch.object(core, "compute_c", wraps=core.compute_c) as estimate:
            for _ in range(3):
                self.run_subtraction(emission, continuum, {"estimate_c": True}, extension=extension, preview=True)
            self.assertEqual(estimate.call_count, 1)
            self.run_subtraction(emission * 1.01, continuum, {"estimate_c": True}, extension=extension, preview=True)
            self.assertEqual(estimate.call_count, 2)

    def test_uint16_emission_is_clipped_into_its_sample_type(self):
        emission, continuum = synthetic_pair()
        source = (emission * 65535.0).astype(np.uint16)

        dst = self.run_subtraction(source, continuum, {"estimate_c": False, "c": 1.0})

        self.assertEqual(dst.array.dtype, np.uint16)
        expected = core.subtract_continuum(source.astype(np.float32) / 65535.0, continuum, 1.0)
        np.testing.assert_array_equal(dst.array, (np.clip(expected, 0.0, 1.0) * 65535.0).astype(np.uint16))

    def test_mismatched_or_missing_continuum_is_refused(self):
        emission, continuum = synthetic_pair()

        with self.assertRaisesRegex(ValueError, "size"):
            self.run_subtraction(emission, continuum[:-2], {"estimate_c": False})
        with self.assertRaisesRegex(RuntimeError, "continuum"):
            ContinuumSubtractionExtension(None).execute(
                "target", FakeImage(emission), FakeImage(emission), {"continuum_view": ""}, FakeProgress()
            )


class ContinuumBlendAdapterTests(unittest.TestCase):
    def test_presets_and_custom_weights(self):
        self.assertEqual(blend_weights({"preset": "OIII"}), (0.0, 0.0, 1.0))
        self.assertEqual(blend_weights({}), (1.0, 0.0, 0.0))
        self.assertEqual(
            blend_weights({"preset": "Custom", "red_weight": 50, "green_weight": 25, "blue_weight": 150}),
            (0.5, 0.25, 1.0),
        )

    def test_blend_adds_the_line_into_the_rgb_target(self):
        emission, continuum = synthetic_pair(48)
        rgb = np.stack([continuum, continuum * 0.9, continuum * 0.8], axis=-1)
        cs = core.subtract_continuum(emission, continuum, 0.3)
        dst = FakeImage(rgb.copy())

        ContinuumBlendExtension(None).execute(
            "target",
            FakeImage(rgb),
            dst,
            {"_line_image": FakeImage(cs), "preset": "SII", "strength": 3.0},
            FakeProgress(),
        )

        np.testing.assert_allclose(dst.array, core.blend_into_rgb(rgb, cs, 3.0, (0.0, 1.0, 0.0)), atol=1e-7)
        self.assertEqual(dst.metadata["continuum_subtraction.blend_weights"], "0.0000,1.0000,0.0000")

    def test_blend_keeps_a_channel_first_layout(self):
        emission, continuum = synthetic_pair(48)
        rgb = np.stack([continuum, continuum, continuum], axis=-1)
        planar = np.moveaxis(rgb, -1, 0).copy()
        dst = FakeImage(planar.copy())

        ContinuumBlendExtension(None).execute(
            "target", FakeImage(planar), dst, {"_line_image": FakeImage(emission)}, FakeProgress()
        )

        expected = np.moveaxis(core.blend_into_rgb(rgb, emission, 2.0, (1.0, 0.0, 0.0)), -1, 0)
        np.testing.assert_allclose(dst.array, expected, atol=1e-7)

    def test_mono_target_is_refused(self):
        emission, continuum = synthetic_pair(32)

        with self.assertRaisesRegex(ValueError, "RGB"):
            ContinuumBlendExtension(None).execute(
                "target",
                FakeImage(continuum),
                FakeImage(continuum),
                {"_line_image": FakeImage(emission)},
                FakeProgress(),
            )


class ContinuumSubtractionSchemaTests(unittest.TestCase):
    def test_subtraction_schema(self):
        by_id = {item["id"]: item for item in cs_ui.subtraction_parameter_defs()}

        self.assertEqual(by_id["window_meta"]["target_channel_filter"], [1])
        self.assertEqual(by_id["continuum_view"]["type"], "view_selector")
        self.assertTrue(by_id["continuum_view"]["match_target_geometry"])
        self.assertEqual(by_id["c"]["enabled_when"], {"param": "estimate_c", "equals": False})
        self.assertEqual((by_id["c"]["min"], by_id["c"]["max"], by_id["c"]["default"]), (0.0, 1.0, 0.2))
        self.assertEqual(by_id["region_mask"]["type"], "manual_mask_editor")
        self.assertEqual(by_id["region_mask"]["use_param"], "use_region_mask")

    def test_blend_schema(self):
        by_id = {item["id"]: item for item in cs_ui.blend_parameter_defs()}

        self.assertEqual(by_id["window_meta"]["target_channel_filter"], [3])
        self.assertEqual((by_id["strength"]["min"], by_id["strength"]["max"], by_id["strength"]["default"]), (0, 12, 2))
        self.assertEqual(by_id["red_weight"]["enabled_when"], {"param": "preset", "equals": "Custom"})

    def test_manifest_declares_both_processes(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        self.assertEqual(manifest["license"], "GPL-3.0-only")
        self.assertEqual(processes["subtract"]["class"], ContinuumSubtractionExtension.__name__)
        self.assertEqual(processes["subtract"]["capabilities"]["masks"], {"input": True})
        self.assertEqual(processes["blend"]["class"], ContinuumBlendExtension.__name__)
        for process in processes.values():
            self.assertEqual(process["capabilities"]["preview_scaling"], "full_only")
        self.assertTrue(issubclass(ContinuumSubtractionExtension, ui.RTPreviewProcess))


if __name__ == "__main__":
    unittest.main()

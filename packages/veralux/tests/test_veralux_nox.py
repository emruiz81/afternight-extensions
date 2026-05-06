import json
import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

from afternight import ui  # noqa: E402
import veralux_nox_adapter as nox_adapter  # noqa: E402
import veralux_nox_core as core  # noqa: E402
import veralux_nox_ui as nox_ui  # noqa: E402
from veralux_extension import VeraLuxNoxExtension as SuiteNoxExtension  # noqa: E402
from veralux_nox_adapter import VeraLuxNoxExtension  # noqa: E402


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


class FakeProgress:
    def __init__(self):
        self.text = ""
        self.value = 0.0
        self.cancelled = False

    def set_text(self, text):
        self.text = str(text)

    def set_value(self, value):
        self.value = float(value)

    def is_cancelled(self):
        return self.cancelled


def synthetic_gradient_field(size=96, seed=9):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    x_norm = x / float(size - 1)
    y_norm = y / float(size - 1)
    gradient = 0.075 + 0.135 * x_norm + 0.050 * y_norm
    nebula = 0.26 * np.exp(-(((x - 54.0) ** 2) + ((y - 48.0) ** 2)) / (2.0 * 11.0**2))
    star = 0.68 * np.exp(-(((x - 24.0) ** 2) + ((y - 23.0) ** 2)) / (2.0 * 1.7**2))
    noise = rng.normal(0.0, 0.004, size=(size, size)).astype(np.float32)
    red = np.clip(gradient * 1.08 + nebula * 1.10 + star + noise, 0.0, 1.0)
    green = np.clip(gradient * 0.98 + nebula * 0.82 + star + noise * 0.8, 0.0, 1.0)
    blue = np.clip(gradient * 0.88 + nebula * 0.55 + star + noise * 0.6, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def corner_medians(image):
    luminance = core.luminance(np.asarray(image, dtype=np.float32))
    patches = [
        luminance[:18, :18],
        luminance[:18, -18:],
        luminance[-18:, :18],
        luminance[-18:, -18:],
    ]
    return np.asarray([np.median(patch) for patch in patches], dtype=np.float32)


class VeraLuxNoxCoreTests(unittest.TestCase):
    def test_gradient_reduction_flattens_background_and_preserves_signal(self):
        source = synthetic_gradient_field()

        result = core.process_gradient_reduction(
            source,
            stiffness=1.0,
            rejection_power=62.0,
            auto_mask=True,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)

        source_spread = float(np.ptp(corner_medians(source)))
        result_spread = float(np.ptp(corner_medians(result)))
        self.assertLess(result_spread, source_spread * 0.42)

        before_contrast = float(source[48, 54, 0] - np.median(source[:18, :18, 0]))
        after_contrast = float(result[48, 54, 0] - np.median(result[:18, :18, 0]))
        self.assertGreater(after_contrast, before_contrast * 0.75)

    def test_auto_mask_reduces_background_model_pull_from_bright_signal(self):
        source = synthetic_gradient_field()

        open_model = core.estimate_background_model(
            source[..., 0],
            auto_mask=False,
            stiffness=1.8,
        )
        protected_model = core.estimate_background_model(
            source[..., 0],
            auto_mask=True,
            stiffness=1.8,
        )

        self.assertLess(float(protected_model[48, 54]), float(open_model[48, 54]) * 0.88)

    def test_auto_tune_returns_bounded_physics_parameters(self):
        stiffness, rejection_power = core.calculate_heuristics(synthetic_gradient_field())

        self.assertGreaterEqual(stiffness, 1.0)
        self.assertLessEqual(stiffness, 4.0)
        self.assertGreaterEqual(rejection_power, 25.0)
        self.assertLessEqual(rejection_power, 72.0)

    def test_manual_protection_mask_matches_original_micro_seal(self):
        mask = np.zeros((7, 7), dtype=np.float32)
        mask[3, 3] = 1.0

        sky = core._protection_to_sky_mask(mask, mask.shape)

        self.assertTrue(sky.dtype == bool)
        self.assertFalse(np.any(sky[2:5, 2:5]))
        self.assertTrue(sky[0, 0])


class VeraLuxNoxAdapterTests(unittest.TestCase):
    def test_process_is_rt_preview_based_with_manual_refresh_controls(self):
        self.assertTrue(issubclass(VeraLuxNoxExtension, ui.RTPreviewProcess))

        defs = nox_ui.parameter_defs()
        by_id = {item.get("id"): item for item in defs if isinstance(item, dict)}
        meta = by_id["window_meta"]

        self.assertEqual(meta["window_size"], [1260, 760])
        self.assertNotIn("sub_area", meta)
        self.assertNotIn("sub_area_default_enabled", meta)
        self.assertNotIn("sub_area_size", meta)
        self.assertNotIn("sub_area_label", meta)
        self.assertEqual(meta["controls_panel_width"], 520)
        self.assertIs(meta["preview_hq_default"], True)
        self.assertIs(meta["preview_autostretch"], True)
        self.assertIs(meta["preview_autostretch_default"], True)
        self.assertIs(meta["preview_area"], False)
        self.assertIs(meta["header_progress"], False)
        self.assertIs(meta["target_selector"], True)
        self.assertEqual(meta["target_channel_filter"], [1, 3])
        self.assertIn(f"source version {core.UPSTREAM_VERSION}", by_id["attribution"]["text"])
        self.assertNotIn("upstream_version", by_id)

        self.assertEqual(by_id["preview_mode"]["type"], "choice")
        self.assertEqual(by_id["preview_mode"]["default"], nox_ui.PREVIEW_CORRECTED)
        self.assertEqual(
            by_id["preview_mode"]["options"],
            [
                ["Processed Image", nox_ui.PREVIEW_CORRECTED],
                ["Extracted Gradient", nox_ui.PREVIEW_BACKGROUND],
                ["Protection Mask", nox_ui.PREVIEW_PROTECTION_MASK],
            ],
        )
        self.assertEqual(by_id["preview_mode"]["inline_actions"][0]["id"], "refresh_preview")
        self.assertEqual(by_id["preview_mode"]["inline_actions"][0]["type"], "button")
        self.assertEqual(by_id["preview_mode"]["inline_actions"][0]["button_role"], "primary")
        self.assertIs(by_id["preview_mode"]["inline_actions"][0]["preview_refresh_role"], True)
        self.assertEqual(by_id["preview_status"]["type"], "info")
        self.assertIs(by_id["preview_status"]["preview_status"], True)
        self.assertEqual(by_id["preview_status"]["tone"], "warning")
        self.assertEqual(by_id["manual_mask"]["type"], "manual_mask_editor")
        self.assertEqual(by_id["manual_mask"]["label"], "Manual Protection Mask")
        self.assertEqual(by_id["manual_mask"]["use_param"], "use_manual_mask")
        self.assertEqual(by_id["manual_mask"]["use_label"], "Use manual protection mask")
        self.assertIs(by_id["manual_mask"]["use_default"], False)
        self.assertEqual(by_id["manual_mask"]["display_param"], "preview_mode")
        self.assertEqual(by_id["manual_mask"]["display_value"], nox_ui.PREVIEW_PROTECTION_MASK)
        self.assertEqual(by_id["manual_mask"]["brush_size"], 50)
        self.assertEqual(by_id["manual_mask"]["min_brush_size"], 10)
        self.assertEqual(by_id["manual_mask"]["max_brush_size"], 200)
        self.assertIs(by_id["manual_mask"]["preview_invalidates"], True)
        self.assertNotIn("preview_generation", by_id)
        self.assertIs(by_id["auto_mask"]["default"], True)
        self.assertIs(by_id["auto_mask"]["preview_invalidates"], True)
        self.assertEqual(by_id["rejection_power"]["type"], "int")
        self.assertEqual(by_id["rejection_power"]["label"], "Signal Rejection Power")
        self.assertEqual(by_id["rejection_power"]["min"], 0)
        self.assertEqual(by_id["rejection_power"]["max"], 100)
        self.assertIs(by_id["rejection_power"]["preview_invalidates"], True)
        self.assertEqual(by_id["rejection_power_readout"]["type"], "value_description_label")
        self.assertEqual(by_id["rejection_power_readout"]["text"], "50% - Balanced")
        self.assertEqual(by_id["stiffness"]["min"], 1.0)
        self.assertEqual(by_id["stiffness"]["max"], 4.0)
        self.assertIs(by_id["stiffness"]["preview_invalidates"], True)
        self.assertEqual(by_id["stiffness_readout"]["type"], "value_description_label")
        self.assertEqual(by_id["stiffness_readout"]["text"], "2.0")
        self.assertIs(by_id["save_gradient_model"]["default"], False)
        for param_id in ("rejection_power", "stiffness"):
            self.assertIs(by_id[param_id]["tracking"], False)
        for removed_id in ("output_model", "correction_strength", "model_grid", "auto_tune"):
            self.assertNotIn(removed_id, by_id)

    def test_refresh_action_is_the_preview_recompute_trigger(self):
        extension = VeraLuxNoxExtension(None)

        self.assertEqual(
            extension.handle_param_action(
                "refresh_preview",
                None,
                FakeImage(synthetic_gradient_field(size=24)),
                {},
            ),
            {},
        )
        self.assertIs(extension._preview_refresh_requested, True)

    def test_first_preview_refresh_computes_even_before_cache_exists(self):
        src = FakeImage(synthetic_gradient_field(size=24))
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)
        corrected = np.full_like(src.array, 0.25, dtype=np.float32)
        model = np.full_like(src.array, 0.75, dtype=np.float32)
        calls = []

        def fake_process(src_image, params, progress, masks=None):
            del src_image, progress, masks
            calls.append(dict(params))
            return corrected, model, None, 4.0

        extension._process = fake_process
        params = {
            "preview_mode": nox_ui.PREVIEW_BACKGROUND,
            "auto_mask": False,
            "stiffness": 2.0,
            "rejection_power": 50.0,
            "use_manual_mask": True,
        }

        extension.handle_param_action("refresh_preview", None, src, params)
        extension.execute_preview(None, src, preview, params, progress)

        self.assertEqual(len(calls), 1)
        self.assertTrue(np.allclose(preview.array, model))

    def test_auto_calculate_ignores_psf_auto_masking_and_returns_slider_values(self):
        src = FakeImage(synthetic_gradient_field(size=24))
        extension = VeraLuxNoxExtension(None)

        def fake_star_mask(src_image, **kwargs):
            del src_image, kwargs
            raise AssertionError("Auto-Calculate should not invoke PSF auto-masking")

        def fake_heuristics(source, star_mask=None, fwhm_val=3.0):
            del source
            self.assertIsNone(star_mask)
            self.assertEqual(fwhm_val, 3.0)
            return 1.24, 38.7

        original_star_mask = nox_adapter.sdk.star_mask_and_median_fwhm_from_find_stars
        original_heuristics = nox_adapter.core.calculate_heuristics
        try:
            nox_adapter.sdk.star_mask_and_median_fwhm_from_find_stars = fake_star_mask
            nox_adapter.core.calculate_heuristics = fake_heuristics

            updates = extension.handle_param_action(
                "auto_calculate",
                None,
                src,
                {"auto_mask": True},
            )
        finally:
            nox_adapter.sdk.star_mask_and_median_fwhm_from_find_stars = original_star_mask
            nox_adapter.core.calculate_heuristics = original_heuristics

        self.assertEqual(updates, {"stiffness": 1.2, "rejection_power": 39})

    def test_execute_preview_uses_cached_output_until_refresh_button_is_pressed(self):
        src = FakeImage(synthetic_gradient_field(size=24))
        preview = FakeImage(np.zeros_like(src.array))
        mask_array = np.zeros(src.array.shape[:2], dtype=np.float32)
        mask_array[5:12, 6:14] = 1.0
        mask = FakeImage(mask_array)
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)
        calls = []

        corrected = np.full_like(src.array, 0.25, dtype=np.float32)
        model = np.full_like(src.array, 0.75, dtype=np.float32)

        def fake_process(src_image, params, progress, masks=None):
            del src_image, progress, masks
            calls.append(dict(params))
            return corrected, model, None, 4.0

        extension._process = fake_process
        params = {
            "preview_mode": nox_ui.PREVIEW_BACKGROUND,
            "auto_mask": False,
            "stiffness": 2.0,
            "rejection_power": 50.0,
            "use_manual_mask": True,
        }

        extension.execute_preview(None, src, preview, params, progress, masks=[mask])

        self.assertEqual(calls, [])
        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertTrue(np.allclose(preview.array, 0.0))

        params["preview_mode"] = nox_ui.PREVIEW_CORRECTED
        extension.execute_preview(None, src, preview, params, progress, masks=[mask])

        self.assertEqual(calls, [])
        self.assertTrue(np.allclose(preview.array, src.array))

        params.update(extension.handle_param_action("refresh_preview", None, src, params))
        extension.execute_preview(None, src, preview, params, progress, masks=[mask])

        self.assertEqual(len(calls), 1)
        self.assertTrue(np.allclose(preview.array, corrected))

        params["preview_mode"] = nox_ui.PREVIEW_BACKGROUND
        extension.execute_preview(None, src, preview, params, progress, masks=[mask])

        self.assertEqual(len(calls), 1)
        self.assertTrue(np.allclose(preview.array, model))

        params["preview_mode"] = nox_ui.PREVIEW_PROTECTION_MASK
        extension.execute_preview(None, src, preview, params, progress, masks=[mask])

        self.assertEqual(len(calls), 1)
        self.assertGreater(float(preview.array[8, 8, 0]), float(src.array[8, 8, 0]))

        params.update(extension.handle_param_action("refresh_preview", None, src, params))
        params["preview_mode"] = nox_ui.PREVIEW_BACKGROUND
        extension.execute_preview(None, src, preview, params, progress, masks=[mask])

        self.assertEqual(len(calls), 2)
        self.assertTrue(np.allclose(preview.array, model))
        self.assertEqual(progress.value, 100.0)

    def test_manual_mask_is_ignored_until_enabled(self):
        src = FakeImage(synthetic_gradient_field(size=18))
        preview = FakeImage(np.zeros_like(src.array))
        mask_array = np.zeros(src.array.shape[:2], dtype=np.float32)
        mask_array[5:10, 5:10] = 1.0
        mask = FakeImage(mask_array)
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)

        params = {
            "preview_mode": nox_ui.PREVIEW_PROTECTION_MASK,
            "auto_mask": False,
            "stiffness": 2.0,
            "rejection_power": 50.0,
            "use_manual_mask": False,
        }

        extension.execute_preview(None, src, preview, params, progress, masks=[mask])
        self.assertTrue(np.allclose(preview.array, src.array))

        params["use_manual_mask"] = True
        extension.execute_preview(None, src, preview, params, progress, masks=[mask])
        self.assertGreater(float(preview.array[7, 7, 0]), float(src.array[7, 7, 0]))

    def test_protection_mask_view_reflects_current_mask_without_preview_refresh(self):
        src = FakeImage(synthetic_gradient_field(size=18))
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)

        params = {
            "preview_mode": nox_ui.PREVIEW_PROTECTION_MASK,
            "auto_mask": False,
            "stiffness": 2.0,
            "rejection_power": 50.0,
            "use_manual_mask": True,
        }

        empty_mask = FakeImage(np.zeros(src.array.shape[:2], dtype=np.float32))
        extension.execute_preview(None, src, preview, params, progress, masks=[empty_mask])
        self.assertTrue(np.allclose(preview.array, src.array))

        painted_mask_array = np.zeros(src.array.shape[:2], dtype=np.float32)
        painted_mask_array[5:10, 5:10] = 1.0
        painted_mask = FakeImage(painted_mask_array)
        extension.execute_preview(None, src, preview, params, progress, masks=[painted_mask])

        self.assertGreater(float(preview.array[7, 7, 0]), float(src.array[7, 7, 0]))

    def test_protection_mask_view_preserves_mono_source_shape(self):
        source_array = core.luminance(synthetic_gradient_field(size=18))
        src = FakeImage(source_array)
        preview = FakeImage(np.zeros_like(src.array))
        mask_array = np.zeros(src.array.shape[:2], dtype=np.float32)
        mask_array[5:10, 5:10] = 1.0
        mask = FakeImage(mask_array)
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "preview_mode": nox_ui.PREVIEW_PROTECTION_MASK,
                "auto_mask": False,
                "stiffness": 2.0,
                "rejection_power": 50.0,
                "use_manual_mask": True,
            },
            progress,
            masks=[mask],
        )

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(preview.array[7, 7]), float(src.array[7, 7]))

    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_gradient_field())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "stiffness": 1.0,
                "rejection_power": 60.0,
                "auto_mask": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertLess(float(np.ptp(corner_medians(dst.array))), float(np.ptp(corner_medians(src.array))))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_nox")
        self.assertEqual(dst.metadata["veralux.tool"], "Nox")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_execute_always_writes_corrected_source_and_opens_model_as_separate_image(self):
        src = FakeImage(synthetic_gradient_field(size=20))
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxNoxExtension(None)
        corrected = np.full_like(src.array, 0.22, dtype=np.float32)
        model = np.full_like(src.array, 0.66, dtype=np.float32)
        opened = []

        def fake_process(src_image, params, progress, masks=None):
            del src_image, params, progress, masks
            return corrected, model, None, 4.5

        def fake_open_image(array, title="Extension Image", metadata=None):
            opened.append((np.asarray(array, dtype=np.float32), title, dict(metadata or {})))
            return True

        original_open_image = nox_adapter.ui.open_image
        try:
            extension._process = fake_process
            nox_adapter.ui.open_image = fake_open_image
            extension.execute(
                None,
                src,
                dst,
                {
                    "stiffness": 2.0,
                    "rejection_power": 50.0,
                    "auto_mask": False,
                    "save_gradient_model": True,
                },
                progress,
            )
        finally:
            nox_adapter.ui.open_image = original_open_image

        self.assertTrue(np.allclose(dst.array, corrected))
        self.assertEqual(len(opened), 1)
        self.assertTrue(np.allclose(opened[0][0], model))
        self.assertEqual(opened[0][1], "VeraLux Nox Gradient Model")
        self.assertEqual(opened[0][2]["veralux.tool"], "Nox Gradient Model")
        self.assertEqual(progress.value, 100.0)

    def test_manifest_declares_nox_preview_and_mask_capabilities(self):
        with (PACKAGE_ROOT / "extension.json").open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        nox = next(process for process in manifest["processes"] if process["id_suffix"] == "nox")
        self.assertEqual(
            nox["capabilities"],
            {
                "execute": True,
                "preview": True,
                "keep_open": True,
                "masks": {"input": True},
            },
        )

    def test_suite_entry_point_exports_nox_process(self):
        self.assertIs(SuiteNoxExtension, VeraLuxNoxExtension)


if __name__ == "__main__":
    unittest.main()

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
import veralux_silentium_core as core  # noqa: E402
import veralux_silentium_adapter as silentium_adapter  # noqa: E402
import veralux_silentium_ui as silentium_ui  # noqa: E402
from veralux_extension import VeraLuxSilentiumExtension as SuiteSilentiumExtension  # noqa: E402
from veralux_silentium_adapter import VeraLuxSilentiumExtension  # noqa: E402


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


def synthetic_noisy_linear_rgb(size=80, seed=42):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    background = 0.08 + 0.015 * (x / float(size - 1))
    nebula = 0.22 * np.exp(-(((x - 36.0) ** 2) + ((y - 42.0) ** 2)) / (2.0 * 13.0**2))
    star = 0.72 * np.exp(-(((x - 23.0) ** 2) + ((y - 20.0) ** 2)) / (2.0 * 1.8**2))
    luminance = np.clip(background + nebula + star, 0.0, 1.0)
    rgb = np.stack(
        [
            luminance * 1.04,
            luminance * 0.98,
            luminance * 0.88,
        ],
        axis=-1,
    )
    noise = rng.normal(0.0, 0.022, size=rgb.shape).astype(np.float32)
    chroma_noise = rng.normal(0.0, 0.016, size=rgb.shape).astype(np.float32)
    chroma_noise -= np.mean(chroma_noise, axis=-1, keepdims=True)
    return np.clip(rgb + noise + chroma_noise, 0.0, 1.0).astype(np.float32)


def robust_sigma(values):
    flat = np.asarray(values, dtype=np.float32).reshape(-1)
    median = float(np.median(flat))
    mad = float(np.median(np.abs(flat - median)))
    return 1.4826 * mad


def luminance(values):
    rgb = np.asarray(values, dtype=np.float32)
    return (0.2126 * rgb[..., 0]) + (0.7152 * rgb[..., 1]) + (0.0722 * rgb[..., 2])


class VeraLuxSilentiumCoreTests(unittest.TestCase):
    def test_noise_reduction_reduces_background_sigma_and_preserves_star_core(self):
        source = synthetic_noisy_linear_rgb()
        background = np.s_[0:18, 0:18, :]
        star_before = float(source[20, 23, 0])

        result = core.process_noise_reduction(
            source,
            intensity=1.44,
            detail_guard=70.0,
            adaptive_noise=True,
            enable_chroma=False,
            chroma_strength=0.0,
            shadow_smoothness=35.0,
            use_stars=False,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertLess(robust_sigma(luminance(result[background])), robust_sigma(luminance(source[background])) * 0.82)
        self.assertGreater(float(result[20, 23, 0]), star_before * 0.92)

    def test_chroma_noise_reduction_reduces_channel_spread(self):
        source = synthetic_noisy_linear_rgb(seed=7)

        result = core.process_noise_reduction(
            source,
            intensity=1.1,
            detail_guard=55.0,
            adaptive_noise=True,
            enable_chroma=True,
            chroma_strength=70.0,
            shadow_smoothness=10.0,
            use_stars=False,
        )

        source_spread = np.std(source - np.mean(source, axis=-1, keepdims=True), axis=-1)
        result_spread = np.std(result - np.mean(result, axis=-1, keepdims=True), axis=-1)
        self.assertLess(float(np.median(result_spread)), float(np.median(source_spread)))

    def test_noise_intensity_uses_original_zero_to_two_log_scale(self):
        source = synthetic_noisy_linear_rgb(seed=13)
        background = np.s_[0:18, 0:18, :]

        disabled = core.process_noise_reduction(
            source,
            intensity=0.0,
            enable_chroma=False,
            use_stars=False,
        )
        strong = core.process_noise_reduction(
            source,
            intensity=2.0,
            detail_guard=20.0,
            adaptive_noise=True,
            enable_chroma=True,
            chroma_strength=80.0,
            shadow_smoothness=80.0,
            use_stars=False,
        )

        self.assertLess(float(np.max(np.abs(disabled - source))), 1e-5)
        self.assertLess(robust_sigma(luminance(strong[background])), robust_sigma(luminance(source[background])) * 0.5)

    def test_shadow_report_summarizes_noise_and_pedestal(self):
        source = synthetic_noisy_linear_rgb(seed=11)
        result = core.process_noise_reduction(source, intensity=1.2, use_stars=False)

        report = core.calculate_shadow_report(source, result)

        self.assertIn("VERALUX SILENTIUM", report)
        self.assertIn("Noise Reduction", report)
        self.assertIn("Effective Integration", report)
        self.assertIn("Pedestal Shift", report)


class VeraLuxSilentiumAdapterTests(unittest.TestCase):
    def test_process_is_rt_preview_based_with_autostretch_controls(self):
        self.assertTrue(issubclass(VeraLuxSilentiumExtension, ui.RTPreviewProcess))

        defs = silentium_ui.parameter_defs()
        by_id = {item.get("id"): item for item in defs if isinstance(item, dict)}
        meta = by_id["window_meta"]

        self.assertEqual(meta["window_size"], [1260, 760])
        self.assertIs(meta["sub_area"], True)
        self.assertIs(meta["sub_area_default_enabled"], True)
        self.assertEqual(meta["sub_area_size"], [800, 600])
        self.assertEqual(meta["sub_area_label"], "Preview: Silentium")
        self.assertEqual(meta["controls_panel_width"], 520)
        self.assertIs(meta["preview_hq_default"], True)
        self.assertIs(meta["preview_autostretch"], True)
        self.assertIs(meta["preview_autostretch_default"], True)
        self.assertIs(meta["header_progress"], False)
        self.assertIn(f"source version {core.UPSTREAM_VERSION}", by_id["attribution"]["text"])
        self.assertNotIn("upstream_version", by_id)

        section_labels = [item["label"] for item in defs if item.get("type") == "section"]
        self.assertEqual(
            section_labels,
            [
                "Silentium Core",
                "Chrominance (Color Noise)",
                "Deep Space Smoothness (Shadows)",
                "Star Field Handling",
            ],
        )
        self.assertEqual(by_id["noise_intensity"]["label"], "Noise Intensity (Log S)")
        self.assertEqual(by_id["noise_intensity"]["default"], 0.5)
        self.assertEqual(by_id["noise_intensity"]["min"], 0.0)
        self.assertEqual(by_id["noise_intensity"]["max"], 2.0)
        self.assertEqual(by_id["noise_intensity"]["step"], 0.01)
        self.assertIs(by_id["use_stars"]["default"], True)
        self.assertIs(by_id["auto_starless"]["default"], True)
        self.assertNotIn("protect_highlights", by_id)
        for param_id in ("noise_intensity", "detail_guard", "shadow_smoothness", "chroma_strength"):
            self.assertIs(by_id[param_id]["tracking"], False)

    def test_execute_writes_denoised_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_noisy_linear_rgb())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxSilentiumExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "noise_intensity": 1.3,
                "detail_guard": 60.0,
                "adaptive_noise": True,
                "enable_chroma": True,
                "chroma_strength": 50.0,
                "shadow_smoothness": 20.0,
                "use_stars": False,
                "auto_starless": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertLess(robust_sigma(dst.array[:18, :18, :]), robust_sigma(src.array[:18, :18, :]))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_silentium")
        self.assertEqual(dst.metadata["veralux.tool"], "Silentium")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_writes_preview_image_without_provenance_metadata(self):
        src = FakeImage(synthetic_noisy_linear_rgb())
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxSilentiumExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "noise_intensity": 1.3,
                "detail_guard": 60.0,
                "adaptive_noise": True,
                "enable_chroma": True,
                "chroma_strength": 50.0,
                "shadow_smoothness": 20.0,
                "use_stars": False,
                "auto_starless": True,
            },
            progress,
        )

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertLess(robust_sigma(preview.array[:18, :18, :]), robust_sigma(src.array[:18, :18, :]))
        self.assertEqual(preview.metadata, {})
        self.assertEqual(progress.value, 100.0)

    def test_star_protection_does_not_make_preview_nearly_noop_when_fwhm_map_is_sparse(self):
        src = FakeImage(synthetic_noisy_linear_rgb(size=128, seed=21))
        preview = FakeImage(np.zeros_like(src.array))
        mask = np.zeros(src.array.shape[:2], dtype=np.float32)
        mask[32, 36] = 1.0
        collapsed_fwhm_map = np.full(src.array.shape[:2], 0.1, dtype=np.float32)
        original_builder = silentium_adapter.sdk.star_mask_and_fwhm_map_from_find_stars

        def fake_star_builder(*args, **kwargs):
            del args, kwargs
            return mask, collapsed_fwhm_map

        try:
            silentium_adapter.sdk.star_mask_and_fwhm_map_from_find_stars = fake_star_builder
            VeraLuxSilentiumExtension(None).execute_preview(
                None,
                src,
                preview,
                {
                    "noise_intensity": 0.5,
                    "detail_guard": 50.0,
                    "adaptive_noise": True,
                    "enable_chroma": True,
                    "chroma_strength": 30.0,
                    "shadow_smoothness": 10.0,
                    "use_stars": True,
                    "auto_starless": True,
                },
                FakeProgress(),
            )
        finally:
            silentium_adapter.sdk.star_mask_and_fwhm_map_from_find_stars = original_builder

        background = np.s_[0:32, 0:32, :]
        self.assertLess(
            robust_sigma(luminance(preview.array[background])),
            robust_sigma(luminance(src.array[background])) * 0.8,
        )
        self.assertGreater(float(np.mean(np.abs(preview.array - src.array))), 0.005)

    def test_manifest_declares_silentium_preview_capabilities(self):
        with (PACKAGE_ROOT / "extension.json").open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

        silentium = next(process for process in manifest["processes"] if process["id_suffix"] == "silentium")
        self.assertEqual(silentium["capabilities"], {"execute": True, "preview": True, "keep_open": True})

    def test_suite_entry_point_exports_silentium_process(self):
        self.assertIs(SuiteSilentiumExtension, VeraLuxSilentiumExtension)


if __name__ == "__main__":
    unittest.main()

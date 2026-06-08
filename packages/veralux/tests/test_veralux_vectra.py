import sys
import unittest
from pathlib import Path

import numpy as np


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

from afternight import ui  # noqa: E402
import veralux_vectra_core as core  # noqa: E402
from veralux_extension import VeraLuxVectraExtension as SuiteVectraExtension  # noqa: E402
from veralux_vectra_adapter import VeraLuxVectraExtension  # noqa: E402


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


def synthetic_stretched_rgb(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    background = 0.16 + (x / size) * 0.02
    red_nebula = 0.55 * np.exp(-(((x - 22.0) ** 2) + ((y - 31.0) ** 2)) / (2.0 * 10.0**2))
    blue_nebula = 0.42 * np.exp(-(((x - 43.0) ** 2) + ((y - 25.0) ** 2)) / (2.0 * 9.0**2))
    star = 0.72 * np.exp(-(((x - 32.0) ** 2) + ((y - 17.0) ** 2)) / (2.0 * 1.4**2))
    red = np.clip(background + red_nebula + star, 0.0, 1.0)
    green = np.clip(background * 0.94 + red_nebula * 0.20 + blue_nebula * 0.36 + star, 0.0, 1.0)
    blue = np.clip(background * 0.91 + blue_nebula + star, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


class VeraLuxVectraCoreTests(unittest.TestCase):
    def test_zero_vectors_preserve_rgb_input(self):
        source = synthetic_stretched_rgb()

        result = core.process_vectors(source, core.default_vectors(), shadow_auth=0.0, protect_stars=True)

        self.assertEqual(result.shape, source.shape)
        self.assertLess(float(np.max(np.abs(result - source))), 2e-4)

    def test_targeted_vector_shift_changes_chroma_without_large_luminance_shift(self):
        source = synthetic_stretched_rgb()
        vectors = core.default_vectors()
        vectors["R"] = (28.0, 0.45)

        result = core.process_vectors(source, vectors, shadow_auth=0.0, protect_stars=True)

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreater(float(np.mean(np.abs(result - source))), 1e-3)

        src_l = core.rgb_luminance(source)
        out_l = core.rgb_luminance(result)
        self.assertLess(float(np.mean(np.abs(out_l - src_l))), 2.5e-2)

    def test_chw_input_preserves_layout_and_matches_hwc_processing(self):
        source_hwc = synthetic_stretched_rgb()
        source_chw = np.moveaxis(source_hwc, -1, 0)
        vectors = core.default_vectors()
        vectors["R"] = (18.0, 0.35)
        vectors["B"] = (-12.0, 0.20)

        hwc_result = core.process_vectors(source_hwc, vectors, shadow_auth=20.0, protect_stars=True)
        chw_result = core.process_vectors(source_chw, vectors, shadow_auth=20.0, protect_stars=True)

        self.assertEqual(chw_result.shape, source_chw.shape)
        self.assertLess(float(np.max(np.abs(np.moveaxis(chw_result, 0, -1) - hwc_result))), 1e-6)

    def test_shadow_authority_reduces_background_tinting(self):
        source = synthetic_stretched_rgb()
        source[:12, :12, 2] = np.clip(source[:12, :12, 2] + 0.12, 0.0, 1.0)
        vectors = core.default_vectors()
        vectors["B"] = (-35.0, 0.65)

        open_result = core.process_vectors(source, vectors, shadow_auth=0.0, protect_stars=False)
        locked_result = core.process_vectors(source, vectors, shadow_auth=100.0, protect_stars=False)

        background = np.s_[0:12, 0:12, :]
        open_delta = float(np.mean(np.abs(open_result[background] - source[background])))
        locked_delta = float(np.mean(np.abs(locked_result[background] - source[background])))
        self.assertLess(locked_delta, open_delta)


class VeraLuxVectraAdapterTests(unittest.TestCase):
    def test_vectra_uses_rt_preview_native_window_with_upstream_tabs(self):
        extension = VeraLuxVectraExtension(None)

        self.assertTrue(issubclass(VeraLuxVectraExtension, ui.RTPreviewProcess))
        params = extension.get_params()
        meta = params[0]

        self.assertEqual(meta["type"], "meta")
        self.assertEqual(meta["window_size"], [1260, 760])
        self.assertTrue(meta["sub_area"])
        self.assertFalse(meta["sub_area_default_enabled"])
        self.assertEqual(meta["sub_area_label"], "Preview: Vectra")
        self.assertEqual(meta["controls_panel_width"], 520)
        self.assertTrue(meta["target_selector"])
        self.assertEqual(meta["target_channel_filter"], [3])
        self.assertFalse(meta["preview_hq_default"])
        self.assertFalse(meta["header_progress"])

        ids_by_type = [(param.get("id"), param.get("type"), param.get("label")) for param in params]
        self.assertIn(("vector_tabs", "tabs", None), ids_by_type)
        self.assertIn(("primary_vectors", "tab", "Primary Vectors"), ids_by_type)
        self.assertIn(("secondary_vectors", "tab", "Secondary Vectors"), ids_by_type)
        self.assertIn(("end_vector_tabs", "end_tabs", None), ids_by_type)

        primary_index = next(i for i, param in enumerate(params) if param.get("id") == "primary_vectors")
        secondary_index = next(i for i, param in enumerate(params) if param.get("id") == "secondary_vectors")
        protection_index = next(i for i, param in enumerate(params) if param.get("id") == "protection")
        protect_stars_index = next(i for i, param in enumerate(params) if param.get("id") == "protect_stars")
        vector_slope_index = next(i for i, param in enumerate(params) if param.get("id") == "vector_slope")
        self.assertLess(primary_index, secondary_index)
        self.assertLess(secondary_index, protection_index)
        self.assertLess(protect_stars_index, vector_slope_index)

        vector_slope = params[vector_slope_index]
        self.assertEqual(vector_slope["type"], "vector_slope")
        self.assertEqual(vector_slope["label"], "Vector Slope")
        self.assertEqual(vector_slope["height"], 220)

        saturation_params = {param["id"]: param for param in params if str(param.get("id", "")).endswith("_saturation")}
        self.assertEqual(
            set(saturation_params),
            {
                "red_saturation",
                "green_saturation",
                "blue_saturation",
                "yellow_saturation",
                "cyan_saturation",
                "magenta_saturation",
            },
        )
        for param in saturation_params.values():
            self.assertEqual(param["label"], "Saturation")
            self.assertEqual(param["min"], -100.0)
            self.assertEqual(param["max"], 100.0)
            self.assertEqual(param["step"], 1.0)
            self.assertFalse(param["tracking"])

    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_stretched_rgb())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxVectraExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "red_hue": 22.0,
                "red_saturation": 35.0,
                "blue_hue": -15.0,
                "blue_saturation": 20.0,
                "shadow_authority": 0.0,
                "protect_stars": True,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(dst.array - src.array))), 1e-3)
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_vectra")
        self.assertEqual(dst.metadata["veralux.tool"], "Vectra")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(dst.metadata["ANLIN"], "nonlinear")
        self.assertEqual(dst.metadata["ANBASIS"], "display-rgb")
        self.assertEqual(dst.metadata["ANASRC"], "process")
        self.assertEqual(dst.metadata["ANOP"], "veralux-vectra")
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_writes_result_without_provenance_metadata(self):
        src = FakeImage(synthetic_stretched_rgb())
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxVectraExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "yellow_hue": 18.0,
                "yellow_saturation": 45.0,
                "shadow_authority": 0.0,
                "protect_stars": True,
            },
            progress,
        )

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(preview.array - src.array))), 1e-3)
        self.assertNotIn("afternight.extension", preview.metadata)
        self.assertEqual(progress.value, 100.0)

    def test_suite_entry_point_exports_vectra_process(self):
        self.assertIs(SuiteVectraExtension, VeraLuxVectraExtension)


if __name__ == "__main__":
    unittest.main()

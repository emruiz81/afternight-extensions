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
import veralux_revela_core as core  # noqa: E402
import veralux_revela_ui as revela_ui  # noqa: E402
from veralux_revela_adapter import VeraLuxRevelaExtension  # noqa: E402


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


def synthetic_mono_image(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    gradient = 0.04 + (x / size) * 0.08
    nebula = 0.28 * np.exp(-(((x - 42.0) ** 2) + ((y - 32.0) ** 2)) / (2.0 * 12.0**2))
    texture = 0.018 * np.sin(x * 0.8) * np.cos(y * 0.55)
    star = 0.75 * np.exp(-(((x - 20.0) ** 2) + ((y - 22.0) ** 2)) / (2.0 * 1.5**2))
    return np.clip(gradient + nebula + texture + star, 0.0, 1.0).astype(np.float32)


class VeraLuxRevelaCoreTests(unittest.TestCase):
    def test_zero_strength_preserves_mono_input(self):
        source = synthetic_mono_image()

        result = core.process_structure(
            source,
            texture_amt=0.0,
            structure_amt=0.0,
            shadow_auth=33.0,
            protect_stars=True,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertLess(float(np.max(np.abs(result - source))), 2e-5)

    def test_enhancement_is_finite_clipped_and_changes_signal(self):
        source = synthetic_mono_image()

        result = core.process_structure(
            source,
            texture_amt=0.55,
            structure_amt=0.35,
            shadow_auth=33.0,
            protect_stars=True,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.mean(np.abs(result - source))), 1e-4)

    def test_mask_mode_returns_active_gate_with_star_core_protection(self):
        source = synthetic_mono_image()

        mask = core.process_structure(
            source,
            texture_amt=0.5,
            structure_amt=0.5,
            shadow_auth=33.0,
            protect_stars=True,
            return_mask=True,
        )

        self.assertEqual(mask.shape, source.shape)
        self.assertGreaterEqual(float(mask.min()), 0.0)
        self.assertLessEqual(float(mask.max()), 1.0)
        self.assertLess(float(mask[22, 20]), float(mask[32, 42]))


class VeraLuxRevelaAdapterTests(unittest.TestCase):
    def test_process_is_rt_preview_based_without_autostretch_controls(self):
        self.assertTrue(issubclass(VeraLuxRevelaExtension, ui.RTPreviewProcess))

        defs = revela_ui.parameter_defs()
        by_id = {param["id"]: param for param in defs if "id" in param}

        self.assertTrue(by_id["window_meta"]["sub_area"])
        self.assertIs(by_id["window_meta"]["sub_area_default_enabled"], False)
        self.assertEqual(by_id["window_meta"]["sub_area_label"], "Preview: Revela")
        self.assertEqual(by_id["window_meta"]["window_size"], [1260, 760])
        self.assertEqual(by_id["window_meta"]["controls_panel_width"], 520)
        self.assertIs(by_id["window_meta"]["preview_hq_default"], False)
        self.assertNotIn("preview_autostretch", by_id["window_meta"])
        self.assertIs(by_id["window_meta"]["header_progress"], False)

        section_labels = [param["label"] for param in defs if param.get("type") == "section"]
        self.assertEqual(section_labels, ["Enhancement", "Protection"])

        for param_id in ("texture", "structure", "shadow_authority"):
            self.assertIs(by_id[param_id]["tracking"], False, param_id)

    def test_manifest_declares_revela_preview_capabilities(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        self.assertEqual(
            processes["revela"]["capabilities"],
            {"execute": True, "preview": True, "keep_open": True},
        )

    def test_execute_writes_processed_image_and_provenance_metadata(self):
        src = FakeImage(synthetic_mono_image())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxRevelaExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "texture": 0.4,
                "structure": 0.2,
                "shadow_authority": 33.0,
                "protect_stars": True,
                "show_mask": False,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(dst.array - src.array))), 1e-4)
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_revela")
        self.assertEqual(dst.metadata["veralux.tool"], "Revela")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_writes_preview_image_without_provenance_metadata(self):
        src = FakeImage(synthetic_mono_image())
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxRevelaExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "texture": 0.4,
                "structure": 0.2,
                "shadow_authority": 33.0,
                "protect_stars": True,
                "show_mask": False,
            },
            progress,
        )

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(np.abs(preview.array - src.array))), 1e-4)
        self.assertEqual(preview.metadata, {})
        self.assertEqual(progress.value, 100.0)


if __name__ == "__main__":
    unittest.main()

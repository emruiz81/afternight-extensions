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
import veralux_starcomposer_core as core  # noqa: E402
import veralux_starcomposer_ui as starcomposer_ui  # noqa: E402
from veralux_extension import VeraLuxStarComposerExtension as SuiteStarComposerExtension  # noqa: E402
from veralux_starcomposer_adapter import VeraLuxStarComposerExtension  # noqa: E402


class FakeImage:
    def __init__(self, array, properties=None):
        self.array = np.asarray(array, dtype=np.float32)
        self.metadata = {}
        self.properties = dict(properties or {})

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


def synthetic_star_mask(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    star_a = np.exp(-(((x - 20.0) ** 2) + ((y - 22.0) ** 2)) / (2.0 * 2.2**2))
    star_b = 0.6 * np.exp(-(((x - 44.0) ** 2) + ((y - 39.0) ** 2)) / (2.0 * 3.5**2))
    faint = 0.18 * np.exp(-(((x - 36.0) ** 2) + ((y - 17.0) ** 2)) / (2.0 * 1.8**2))
    red = np.clip(star_a + faint * 1.2, 0.0, 1.0)
    green = np.clip(star_a * 0.82 + star_b + faint, 0.0, 1.0)
    blue = np.clip(star_a * 0.58 + star_b * 0.92 + faint * 0.8, 0.0, 1.0)
    return np.stack([red, green, blue], axis=-1).astype(np.float32)


def synthetic_starless_base(size=64):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    background = 0.12 + 0.08 * (x / max(size - 1, 1)) + 0.04 * (y / max(size - 1, 1))
    return np.repeat(background[..., None], 3, axis=2).astype(np.float32)


class VeraLuxStarComposerCoreTests(unittest.TestCase):
    def test_star_mask_shaping_is_finite_clipped_and_brighter(self):
        source = synthetic_star_mask()

        result = core.process_star_mask(
            source,
            log_d=2.0,
            profile_hardness=50.0,
            color_grip=0.55,
            shadow_convergence=0.0,
            star_reduction=0.0,
            optical_healing=0.0,
            large_structure_rejection=0.0,
        )

        self.assertEqual(result.shape, source.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.mean(result)), float(np.mean(source)))

    def test_star_reduction_reduces_star_footprint(self):
        source = synthetic_star_mask()

        shaped = core.process_star_mask(source, log_d=2.0, star_reduction=0.0)
        reduced = core.process_star_mask(source, log_d=2.0, star_reduction=0.55)

        self.assertLess(float(np.count_nonzero(reduced[..., 0] > 0.35)), float(np.count_nonzero(shaped[..., 0] > 0.35)))

    def test_screen_composite_preserves_bounds_and_brightens_base(self):
        starless = np.full_like(synthetic_star_mask(), 0.18)
        stars = core.process_star_mask(synthetic_star_mask(), log_d=1.8)

        result = core.compose_with_starless(starless, stars, blend_mode="screen")

        self.assertEqual(result.shape, starless.shape)
        self.assertGreaterEqual(float(result.min()), 0.0)
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreater(float(np.mean(result)), float(np.mean(starless)))

    def test_screen_and_linear_add_composites_match_upstream_formulas(self):
        starless = np.full((8, 8, 3), 0.62, dtype=np.float32)
        stars = np.full((8, 8, 3), 0.55, dtype=np.float32)

        screen = core.compose_with_starless(starless, stars, blend_mode="screen")
        linear_add = core.compose_with_starless(starless, stars, blend_mode="Linear Add (Physical)")

        expected_screen = 1.0 - (1.0 - starless) * (1.0 - stars)
        expected_linear_add = np.clip(starless + stars, 0.0, 1.0)
        self.assertTrue(np.allclose(screen, expected_screen, atol=1e-6))
        self.assertTrue(np.allclose(linear_add, expected_linear_add, atol=1e-6))
        self.assertGreater(float(np.mean(np.abs(linear_add - screen))), 0.1)


class VeraLuxStarComposerAdapterTests(unittest.TestCase):
    def test_process_is_rt_preview_based_with_native_preview_defaults(self):
        self.assertTrue(issubclass(VeraLuxStarComposerExtension, ui.RTPreviewProcess))

        defs = starcomposer_ui.parameter_defs()
        by_id = {param["id"]: param for param in defs if "id" in param}
        meta = by_id["window_meta"]

        self.assertIs(meta["preview_area"], False)
        self.assertNotIn("sub_area", meta)
        self.assertNotIn("sub_area_default_enabled", meta)
        self.assertNotIn("sub_area_size", meta)
        self.assertNotIn("sub_area_label", meta)
        self.assertEqual(meta["window_size"], [1260, 760])
        self.assertEqual(meta["controls_panel_width"], 520)
        self.assertIs(meta["preview_hq_default"], False)
        self.assertIs(meta["preview_autostretch"], False)
        self.assertIs(meta["preview_autostretch_default"], False)
        self.assertIs(meta["header_progress"], False)
        self.assertIs(meta["target_selector"], True)
        self.assertEqual(meta["target_channel_filter"], [1, 3])
        self.assertEqual(meta["target_selector_label"], "Starless (stretched)")
        self.assertEqual(meta["target_selector_position"], "params")
        self.assertEqual(by_id["starless_view"]["type"], "target_selector")
        self.assertEqual(by_id["starless_view"]["label"], "Starless (stretched)")
        self.assertEqual(by_id["stars_view"]["type"], "view_selector")
        self.assertEqual(by_id["stars_view"]["label"], "Stars (linear)")
        self.assertEqual(by_id["stars_view"]["default"], "")
        self.assertEqual(by_id["stars_view"]["channel_filter"], [1, 3])
        self.assertIs(by_id["stars_view"]["match_target_geometry"], True)
        self.assertIs(by_id["stars_view"]["match_target_channels"], True)
        self.assertIs(by_id["stars_view"]["exclude_target"], True)
        self.assertEqual(by_id["working_space"]["label"], "Sensor Profile")
        self.assertEqual(by_id["blend_mode"]["default"], "screen")
        self.assertEqual(
            by_id["blend_mode"]["options"],
            [["Screen (Safe)", "screen"], ["Linear Add (Physical)", "linear_add"]],
        )

        section_labels = [param["label"] for param in defs if param.get("type") == "section"]
        self.assertEqual(
            section_labels,
            [
                "Inputs",
                "Sensor Profile",
                "Star Stretch",
                "Hybrid Physics",
                "Star Surgery",
                "Output Composition",
            ],
        )

        for param_id in (
            "log_d",
            "profile_hardness",
            "color_grip",
            "shadow_convergence",
            "large_structure_rejection",
            "star_reduction",
            "optical_healing",
        ):
            self.assertIs(by_id[param_id]["tracking"], False, param_id)

        for param in defs:
            if param.get("type") in {
                "float",
                "double",
                "int",
                "bool",
                "choice",
                "string",
                "target_selector",
                "view_selector",
            }:
                self.assertTrue(param.get("tooltip"), param["id"])

        ui_strings = []
        for param in defs:
            for key in ("label", "text", "tooltip", "sub_area_label"):
                if key in param:
                    ui_strings.append(str(param[key]))
            for option in param.get("options", []):
                if option:
                    ui_strings.append(str(option[0]))

        visible_text = "\n".join(ui_strings).lower()
        self.assertNotIn("siril", visible_text)
        self.assertNotIn("multi-input", visible_text)

    def test_manifest_declares_starcomposer_preview_capabilities(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        self.assertEqual(
            processes["starcomposer"]["capabilities"],
            {"execute": True, "preview": True, "keep_open": True},
        )

    def test_execute_writes_composited_starless_and_provenance_metadata(self):
        src = FakeImage(synthetic_starless_base())
        stars = FakeImage(synthetic_star_mask())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxStarComposerExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "log_d": 1.8,
                "profile_hardness": 50.0,
                "color_grip": 0.55,
                "shadow_convergence": 0.0,
                "large_structure_rejection": 0.0,
                "star_reduction": 0.0,
                "optical_healing": 0.0,
                "use_adaptive_anchor": True,
                "blend_mode": "screen",
                "stars_view": "Stars",
                "_stars_image": stars,
            },
            progress,
        )

        self.assertEqual(dst.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(dst.array)), float(np.mean(src.array)))
        self.assertEqual(dst.metadata["afternight.extension"], "veralux_starcomposer")
        self.assertEqual(dst.metadata["veralux.tool"], "StarComposer")
        self.assertEqual(dst.metadata["veralux.starcomposer.stars_view"], "Stars")
        self.assertEqual(dst.metadata["veralux.starcomposer.blend_mode"], "screen")
        self.assertIn("Riccardo Paterniti", dst.metadata["veralux.attribution"])
        self.assertEqual(progress.value, 100.0)

    def test_execute_normalizes_linear_add_blend_mode_for_metadata(self):
        src = FakeImage(np.full((8, 8, 3), 0.62, dtype=np.float32))
        stars = FakeImage(np.full((8, 8, 3), 0.55, dtype=np.float32))
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxStarComposerExtension(None)

        extension.execute(
            None,
            src,
            dst,
            {
                "log_d": 1.0,
                "profile_hardness": 50.0,
                "color_grip": 0.5,
                "shadow_convergence": 0.0,
                "large_structure_rejection": 0.0,
                "star_reduction": 0.0,
                "optical_healing": 0.0,
                "use_adaptive_anchor": False,
                "blend_mode": "Linear Add (Physical)",
                "stars_view": "Stars",
                "_stars_image": stars,
            },
            progress,
        )

        self.assertEqual(dst.metadata["veralux.starcomposer.blend_mode"], "linear_add")
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_writes_preview_image_without_provenance_metadata(self):
        src = FakeImage(synthetic_starless_base())
        stars = FakeImage(synthetic_star_mask())
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxStarComposerExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "log_d": 1.8,
                "profile_hardness": 50.0,
                "color_grip": 0.55,
                "shadow_convergence": 0.0,
                "large_structure_rejection": 0.0,
                "star_reduction": 0.0,
                "optical_healing": 0.0,
                "use_adaptive_anchor": True,
                "blend_mode": "screen",
                "_stars_image": stars,
            },
            progress,
        )

        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(preview.array)), float(np.mean(src.array)))
        self.assertEqual(preview.metadata, {})
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_uses_proxy_processing_and_restores_output_size(self):
        src = FakeImage(synthetic_starless_base(32))
        stars = FakeImage(synthetic_star_mask(32))
        preview = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxStarComposerExtension(None)
        extension.PREVIEW_PROXY_MAX_DIMENSION = 8

        original_process_star_mask = core.process_star_mask
        observed_shapes = []

        def spy_process_star_mask(starmask, *args, **kwargs):
            observed_shapes.append(np.asarray(starmask).shape)
            return original_process_star_mask(starmask, *args, **kwargs)

        core.process_star_mask = spy_process_star_mask
        try:
            extension.execute_preview(
                None,
                src,
                preview,
                {
                    "log_d": 1.8,
                    "profile_hardness": 50.0,
                    "color_grip": 0.55,
                    "shadow_convergence": 0.0,
                    "large_structure_rejection": 0.0,
                    "star_reduction": 0.0,
                    "optical_healing": 0.0,
                    "use_adaptive_anchor": True,
                    "blend_mode": "screen",
                    "_stars_image": stars,
                },
                progress,
            )
        finally:
            core.process_star_mask = original_process_star_mask

        self.assertEqual(observed_shapes, [(8, 8, 3)])
        self.assertEqual(preview.array.shape, src.array.shape)
        self.assertGreater(float(np.mean(preview.array)), float(np.mean(src.array)))
        self.assertEqual(progress.value, 100.0)

    def test_execute_preview_crops_stars_to_selected_starless_sub_area(self):
        full_stars = np.zeros((20, 24, 3), dtype=np.float32)
        full_stars[9, 11] = [1.0, 0.8, 0.6]
        starless_crop = np.full((5, 6, 3), 0.12, dtype=np.float32)
        src = FakeImage(
            starless_crop,
            properties={
                "width": 6,
                "height": 5,
                "channels": 3,
                "offset_x": 8,
                "offset_y": 7,
                "source_width": 24,
                "source_height": 20,
            },
        )
        stars = FakeImage(full_stars)
        preview = FakeImage(np.zeros_like(starless_crop))
        progress = FakeProgress()
        extension = VeraLuxStarComposerExtension(None)

        extension.execute_preview(
            None,
            src,
            preview,
            {
                "log_d": 1.0,
                "profile_hardness": 50.0,
                "color_grip": 0.5,
                "shadow_convergence": 0.0,
                "large_structure_rejection": 0.0,
                "star_reduction": 0.0,
                "optical_healing": 0.0,
                "use_adaptive_anchor": False,
                "blend_mode": "screen",
                "_stars_image": stars,
            },
            progress,
        )

        self.assertEqual(preview.array.shape, starless_crop.shape)
        self.assertGreater(float(preview.array[2, 3, 0]), 0.12)
        self.assertGreater(float(np.max(preview.array)), 0.12)

    def test_execute_requires_second_stars_image(self):
        src = FakeImage(synthetic_starless_base())
        dst = FakeImage(np.zeros_like(src.array))
        progress = FakeProgress()
        extension = VeraLuxStarComposerExtension(None)

        with self.assertRaisesRegex(RuntimeError, r"Stars \(linear\)"):
            extension.execute(None, src, dst, {"stars_view": ""}, progress)

    def test_suite_entry_point_exports_starcomposer_process(self):
        self.assertIs(SuiteStarComposerExtension, VeraLuxStarComposerExtension)


if __name__ == "__main__":
    unittest.main()

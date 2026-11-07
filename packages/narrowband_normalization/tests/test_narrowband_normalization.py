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
import narrowband_normalization_core as core  # noqa: E402
import narrowband_normalization_ui as nbn_ui  # noqa: E402
from narrowband_normalization_extension import (  # noqa: E402
    NarrowbandNormalizationExtension,
    settings_from_params,
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
        self.text = ""
        self.value = 0.0
        self.cancelled = False

    def set_text(self, text):
        self.text = str(text)

    def set_value(self, value):
        self.value = float(value)

    def is_cancelled(self):
        return self.cancelled


def synthetic_narrowband_rgb(size=64, seed=7):
    """A stretched three-line image: strong Ha, faint OIII, fainter SII, plus noise."""

    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    cloud = np.exp(-(((x - 30.0) ** 2) + ((y - 34.0) ** 2)) / (2.0 * 14.0**2))
    shell = np.exp(-((np.hypot(x - 30.0, y - 34.0) - 16.0) ** 2) / (2.0 * 3.0**2))
    ha = 0.18 + 0.55 * cloud + 0.10 * shell
    oiii = 0.12 + 0.12 * cloud + 0.20 * shell
    sii = 0.10 + 0.20 * cloud
    image = np.stack([ha, oiii, sii], axis=-1) + rng.normal(0.0, 0.01, (size, size, 3))
    return np.clip(image, 0.0, 1.0).astype(np.float32)


def palette_image(palette, size=64):
    """Arrange the synthetic lines in the palette's letter order (HOO leaves green as written)."""

    lines = synthetic_narrowband_rgb(size)
    ha, oiii, sii = lines[..., 0], lines[..., 1], lines[..., 2]
    by_name = {"H": ha, "O": oiii, "S": sii}
    if palette == "HOO":
        return np.stack([ha, np.zeros_like(ha), oiii], axis=-1)
    return np.stack([by_name[letter] for letter in palette], axis=-1)


def params(**overrides):
    values = dict(core.DEFAULT_PARAMS)
    values.update(overrides)
    return values


class NarrowbandNormalizationCoreTests(unittest.TestCase):
    def test_default_hoo_keeps_ha_and_builds_green_from_ha_and_normalized_oiii(self):
        source = palette_image("HOO")

        result = core.process_image(source, params())

        self.assertEqual(result.shape, source.shape)
        self.assertEqual(result.dtype, np.float32)
        np.testing.assert_allclose(result[..., 0], source[..., 0], atol=1e-6)
        green = 0.6 * source[..., 0] + 0.4 * result[..., 2]
        np.testing.assert_allclose(result[..., 1], green, atol=1e-5)

    def test_oiii_boost_brightens_normalized_oiii(self):
        source = palette_image("SHO")

        plain = core.process_image(source, params(palette="SHO"))
        boosted = core.process_image(source, params(palette="SHO", oiii_boost=2.0))

        self.assertGreater(float(np.mean(boosted[..., 2])), float(np.mean(plain[..., 2])) + 1e-3)
        np.testing.assert_allclose(boosted[..., 1], plain[..., 1], atol=1e-6)

    def test_scnr_never_raises_green(self):
        source = palette_image("HSO")

        plain = core.process_image(source, params(palette="HSO"))
        reduced = core.process_image(source, params(palette="HSO", scnr=1.0))

        self.assertTrue(np.all(reduced[..., 1] <= plain[..., 1] + 1e-6))
        self.assertLess(float(np.mean(reduced[..., 1])), float(np.mean(plain[..., 1])))

    def test_every_palette_and_lightness_gives_finite_output_in_range(self):
        for palette in core.PALETTES:
            for lightness in core.LIGHTNESS_SOURCES:
                with self.subTest(palette=palette, lightness=lightness):
                    result = core.process_image(
                        palette_image(palette, 32), params(palette=palette, lightness=lightness)
                    )
                    self.assertTrue(np.all(np.isfinite(result)))
                    self.assertGreaterEqual(float(result.min()), 0.0)
                    self.assertLessEqual(float(result.max()), 1.0)

    def test_hoo_sii_lightness_uses_oiii_as_upstream_does(self):
        source = palette_image("HOO")

        sii = core.process_image(source, params(lightness="SII"))
        oiii = core.process_image(source, params(lightness="OIII"))

        np.testing.assert_array_equal(sii, oiii)

    def test_normalize_input_reads_the_sample_type(self):
        np.testing.assert_allclose(core.normalize_input(np.array([0, 255], dtype=np.uint8)), [0.0, 1.0])
        np.testing.assert_allclose(core.normalize_input(np.array([0, 65535], dtype=np.uint16)), [0.0, 1.0])
        np.testing.assert_allclose(core.normalize_input(np.array([0.0, 0.5], dtype=np.float32)), [0.0, 0.5])
        np.testing.assert_allclose(
            core.normalize_input(np.array([0.0, 32767.5], dtype=np.float32)), [0.0, 0.5], rtol=1e-6
        )


class NarrowbandNormalizationAdapterTests(unittest.TestCase):
    def make_extension(self):
        return NarrowbandNormalizationExtension(None)

    def test_execute_matches_core_and_stamps_result(self):
        source = palette_image("SHO")
        src = FakeImage(source)
        dst = FakeImage(source.copy())
        progress = FakeProgress()

        self.make_extension().execute("target", src, dst, params(palette="SHO", lightness="Ha"), progress)

        expected = core.process_image(source, params(palette="SHO", lightness="Ha"))
        np.testing.assert_allclose(dst.array, expected, atol=1e-6)
        self.assertEqual(progress.value, 100.0)
        self.assertEqual(dst.metadata["afternight.extension"], "narrowband_normalization")
        self.assertEqual(dst.metadata["narrowband_normalization.upstream_version"], core.UPSTREAM_VERSION)
        self.assertEqual(dst.metadata["narrowband_normalization.palette"], "SHO")
        self.assertEqual(dst.metadata["ANLIN"], "nonlinear")

    def test_preview_leaves_metadata_alone(self):
        source = palette_image("HOO")
        preview = FakeImage(source.copy())

        self.make_extension().execute_preview("target", FakeImage(source), preview, params(), FakeProgress())

        self.assertEqual(preview.metadata, {})
        np.testing.assert_allclose(preview.array, core.process_image(source, params()), atol=1e-6)

    def test_uint16_source_round_trips_in_its_sample_type(self):
        source = (palette_image("HOS") * 65535.0).astype(np.uint16)
        dst = FakeImage(source.copy())

        self.make_extension().execute("target", FakeImage(source), dst, params(palette="HOS"), FakeProgress())

        expected = core.process_image(source.astype(np.float32) / 65535.0, params(palette="HOS"))
        self.assertEqual(dst.array.dtype, np.uint16)
        np.testing.assert_array_equal(dst.array, (np.clip(expected, 0.0, 1.0) * 65535.0).astype(np.uint16))

    def test_channel_first_arrays_are_processed_and_written_channel_first(self):
        source = palette_image("SHO")
        planar = np.moveaxis(source, -1, 0).copy()
        dst = FakeImage(planar.copy())

        self.make_extension().execute("target", FakeImage(planar), dst, params(palette="SHO"), FakeProgress())

        expected = np.moveaxis(core.process_image(source, params(palette="SHO")), -1, 0)
        np.testing.assert_allclose(dst.array, expected, atol=1e-6)

    def test_mono_image_is_refused(self):
        mono = synthetic_narrowband_rgb()[..., 0]

        with self.assertRaisesRegex(ValueError, "3-channel RGB"):
            self.make_extension().execute("target", FakeImage(mono), FakeImage(mono), params(), FakeProgress())

    def test_cancelled_run_raises_before_writing(self):
        source = palette_image("HOO")
        dst = FakeImage(source.copy())
        progress = FakeProgress()
        progress.cancelled = True

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.make_extension().execute("target", FakeImage(source), dst, params(), progress)
        np.testing.assert_array_equal(dst.array, source)

    def test_settings_fall_back_to_upstream_defaults_and_reject_unknown_choices(self):
        self.assertEqual(settings_from_params({}), core.DEFAULT_PARAMS)
        with self.assertRaisesRegex(ValueError, "palette"):
            settings_from_params({"palette": "RGB"})


class NarrowbandNormalizationSchemaTests(unittest.TestCase):
    def test_schema_covers_every_core_parameter_with_upstream_defaults(self):
        defs = nbn_ui.parameter_defs()
        by_id = {item["id"]: item for item in defs}

        for key, default in core.DEFAULT_PARAMS.items():
            with self.subTest(param=key):
                self.assertIn(key, by_id)
                self.assertEqual(by_id[key]["default"], default)
        self.assertEqual(by_id["window_meta"]["target_channel_filter"], [3])
        self.assertEqual(by_id["blend_amount"]["enabled_when"], {"param": "palette", "equals": "HOO"})
        self.assertEqual(by_id["sii_boost"]["enabled_when"], {"param": "palette", "not_equals": "HOO"})
        self.assertEqual(by_id["scnr"]["enabled_when"], {"param": "palette", "not_equals": "HOO"})
        self.assertEqual((by_id["oiii_boost"]["min"], by_id["oiii_boost"]["max"]), (0.5, 2.0))
        self.assertEqual((by_id["brightness"]["min"], by_id["brightness"]["max"]), (0.1, 3.0))

    def test_manifest_declares_the_process_class_and_full_image_preview(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        process = manifest["processes"][0]

        self.assertEqual(manifest["entry_point"], "narrowband_normalization_extension")
        self.assertEqual(process["class"], NarrowbandNormalizationExtension.__name__)
        self.assertEqual(process["capabilities"]["preview_scaling"], "full_only")
        self.assertTrue(issubclass(NarrowbandNormalizationExtension, ui.RTPreviewProcess))


if __name__ == "__main__":
    unittest.main()

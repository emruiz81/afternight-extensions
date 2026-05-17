import os
import pathlib
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "package"
APP_REPO = Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import afternight  # noqa: E402
from cosmic_clarity_extension import (  # noqa: E402
    CosmicClarityDarkStarExtension,
    CosmicClarityDenoiseExtension,
    CosmicClaritySharpeningExtension,
    CosmicClaritySuperResExtension,
    _process_failure_message,
)


class CosmicClarityLoggingTests(unittest.TestCase):
    def setUp(self):
        self._original_log_info = afternight.log_info
        self.messages = []

        def capture_info(message, component="extension"):
            self.messages.append((str(component), str(message)))

        afternight.log_info = capture_info

    def tearDown(self):
        afternight.log_info = self._original_log_info

    def log_text(self):
        return "\n".join(message for _component, message in self.messages)

    def test_each_process_launch_hook_emits_banner_with_credits(self):
        cases = [
            (CosmicClarityDenoiseExtension, "Cosmic Clarity - Denoise"),
            (CosmicClarityDarkStarExtension, "Cosmic Clarity - Dark Star"),
            (CosmicClaritySharpeningExtension, "Cosmic Clarity - Sharpening"),
            (CosmicClaritySuperResExtension, "Cosmic Clarity - Super Resolution"),
        ]

        for extension_class, title in cases:
            with self.subTest(title=title):
                self.messages.clear()
                extension_class(None).on_process_launch()
                text = self.log_text()
                self.assertIn("##############################################", text)
                self.assertIn(title, text)
                self.assertIn("Wrapped process author: Seti Astro", text)
                self.assertIn("AfterNight extension maintainer: Ezequiel Ruiz", text)
                self.assertIn("https://github.com/setiastro/cosmicclarity", text)

    def test_each_process_window_meta_uses_process_specific_header(self):
        cases = [
            (CosmicClarityDenoiseExtension, "Seti Astro Cosmic Clarity - Denoise", "full-image noise"),
            (CosmicClarityDarkStarExtension, "Seti Astro Cosmic Clarity - Dark Star", "starless result"),
            (CosmicClaritySharpeningExtension, "Seti Astro Cosmic Clarity - Sharpening", "PSF detection"),
            (CosmicClaritySuperResExtension, "Seti Astro Cosmic Clarity - Super Resolution", "Upscale"),
        ]

        for extension_class, title, detail in cases:
            with self.subTest(title=title):
                params = extension_class(None).get_params()
                meta = params[0]

                self.assertEqual(meta["id"], "window_meta")
                self.assertIn(title, meta["header_description"])
                self.assertIn(detail, meta["header_description"])
                self.assertIn("external suite folder", meta["header_description"])

    def test_tool_configuration_accepts_starter_suite_without_managed_updater(self):
        params = CosmicClarityDenoiseExtension(None).get_params()
        tool_configuration = params[0]["tool_configuration"]

        self.assertEqual(
            tool_configuration["required_executables"],
            [
                "setiastrocosmicclarity_denoise",
                "setiastrocosmicclarity",
            ],
        )
        self.assertNotIn("platform_update_api_urls", tool_configuration)
        self.assertNotIn("update_page_url", tool_configuration)
        self.assertIn("complete current suite", tool_configuration["install_instructions"])
        self.assertIn("_internal runtime folder", tool_configuration["install_instructions"])

    def test_windows_runtime_mismatch_failure_has_actionable_hint(self):
        message = _process_failure_message(
            1,
            [
                'File "torch\\distributed\\distributed_c10d.py", line 285, in Backend',
                (
                    "AttributeError: type object 'torch._C._distributed_c10d.BackendType' "
                    "has no attribute 'XCCL'. Did you mean: 'NCCL'?"
                ),
            ],
        )

        self.assertIn("complete current Windows Cosmic Clarity suite", message)
        self.assertIn("GitHub per-file update release excludes _internal", message)

    def test_gpu_supported_processes_expose_process_toggle(self):
        for extension_class in (
            CosmicClarityDenoiseExtension,
            CosmicClarityDarkStarExtension,
            CosmicClaritySharpeningExtension,
        ):
            with self.subTest(extension=extension_class.__name__):
                params = extension_class(None).get_params()
                field_by_id = {field["id"]: field for field in params}

                self.assertEqual(field_by_id["use_gpu"]["type"], "bool")
                self.assertTrue(field_by_id["use_gpu"]["default"])
                self.assertEqual(field_by_id["use_gpu"]["label"], "Use GPU Acceleration")

        super_res_fields = {field["id"]: field for field in CosmicClaritySuperResExtension(None).get_params()}
        self.assertNotIn("use_gpu", super_res_fields)
        global_settings = {field["id"]: field for field in CosmicClarityDenoiseExtension(None).get_settings_params()}
        self.assertNotIn("gpu_enabled", global_settings)

    def test_denoise_and_sharpening_map_gpu_toggle_to_disable_gpu_arg(self):
        class FakeProgress:
            def set_text(self, _text):
                pass

        class FakeDestination:
            def copy_from(self, _image):
                pass

        class FakeImage:
            def __init__(self, path):
                self.path = pathlib.Path(path)

        cases = [
            (
                CosmicClarityDenoiseExtension,
                "_denoised",
                {
                    "strength": 0.9,
                    "denoise_mode": "full",
                    "use_gpu": False,
                },
            ),
            (
                CosmicClaritySharpeningExtension,
                "_sharpened",
                {
                    "sharpening_mode": "both",
                    "non_stellar_strength": 3.0,
                    "non_stellar_amount": 0.5,
                    "stellar_amount": 0.5,
                    "auto_detect_psf": False,
                    "process_rgb_channels": False,
                    "use_gpu": False,
                },
            ),
        ]

        for extension_class, output_suffix, params in cases:
            with self.subTest(extension=extension_class.__name__):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tool_dir = pathlib.Path(tmpdir) / "suite"
                    tool_dir.mkdir()
                    captured_args = []

                    def fake_run_process(_executable, args, workspace, _progress, **_kwargs):
                        captured_args.extend(args)
                        input_path = next(workspace.input_dir.iterdir())
                        (workspace.output_dir / f"{input_path.stem}{output_suffix}.tiff").write_text(
                            "result",
                            encoding="utf-8",
                        )

                    def fake_save(_image, path, options=None):
                        del options
                        path = pathlib.Path(path)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("image", encoding="utf-8")

                    def fake_load(path, load_metadata=True):
                        del load_metadata
                        return FakeImage(path)

                    extension = extension_class(None)
                    extension.settings.set("executable_path", str(tool_dir))

                    with (
                        mock.patch.object(extension, "_tool_executable", return_value=tool_dir / "helper.exe"),
                        mock.patch.object(extension, "_run_process", side_effect=fake_run_process),
                        mock.patch("cosmic_clarity_extension.io.save", side_effect=fake_save),
                        mock.patch("cosmic_clarity_extension.io.load", side_effect=fake_load),
                    ):
                        extension.execute(
                            None,
                            object(),
                            FakeDestination(),
                            params,
                            FakeProgress(),
                        )

                    self.assertIn("--disable_gpu", captured_args)

    def test_dark_star_maps_gpu_toggle_and_opens_results(self):
        class FakeProgress:
            def set_text(self, _text):
                pass

        class FakeDestination:
            copied = None

            def copy_from(self, image):
                self.copied = image

        class FakeImage:
            def __init__(self, path):
                self.path = pathlib.Path(path)

        with tempfile.TemporaryDirectory() as tmpdir:
            tool_dir = pathlib.Path(tmpdir) / "suite"
            tool_dir.mkdir()
            (tool_dir / "input").mkdir()
            (tool_dir / "output").mkdir()
            stale_input = tool_dir / "input" / "stale.tiff"
            stale_input.write_text("stale", encoding="utf-8")
            artifacts_dir = pathlib.Path(tmpdir) / "artifacts"
            artifacts_dir.mkdir()

            captured_args = []
            opened_titles = []
            saved_paths = []

            def fake_run_process(_executable, args, workspace, _progress, **_kwargs):
                captured_args.extend(args)
                input_path = next(workspace.input_dir.iterdir())
                (workspace.output_dir / f"{input_path.stem}_starless.tiff").write_text(
                    "starless",
                    encoding="utf-8",
                )
                (workspace.output_dir / f"{input_path.stem}_stars_only.tiff").write_text(
                    "stars",
                    encoding="utf-8",
                )

            def fake_save(_image, path, options=None):
                del options
                path = pathlib.Path(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("image", encoding="utf-8")
                saved_paths.append(path)

            def fake_load(path, load_metadata=True):
                del load_metadata
                return FakeImage(path)

            def fake_open_image(_image, title="Extension Image", metadata=None):
                del metadata
                opened_titles.append(title)
                return True

            original_session_paths = afternight.session_paths
            afternight.session_paths = lambda: SimpleNamespace(artifacts_dir=lambda: str(artifacts_dir))
            try:
                extension = CosmicClarityDarkStarExtension(None)
                extension.settings.set("executable_path", str(tool_dir))
                destination = FakeDestination()

                with (
                    mock.patch.object(extension, "_tool_executable", return_value=tool_dir / "darkstar.exe"),
                    mock.patch.object(extension, "_run_process", side_effect=fake_run_process),
                    mock.patch("cosmic_clarity_extension.io.save", side_effect=fake_save),
                    mock.patch("cosmic_clarity_extension.io.load", side_effect=fake_load),
                    mock.patch("cosmic_clarity_extension.ui.open_image", side_effect=fake_open_image),
                ):
                    extension.execute(
                        SimpleNamespace(view_name="RGB"),
                        object(),
                        destination,
                        {
                            "chunk_size": 256,
                            "star_removal_mode": "unscreen",
                            "show_extracted_stars": True,
                            "use_gpu": False,
                        },
                        FakeProgress(),
                    )
            finally:
                afternight.session_paths = original_session_paths

            self.assertIn("--disable_gpu", captured_args)
            self.assertIn("--show_extracted_stars", captured_args)
            self.assertFalse(stale_input.exists())
            self.assertIsNotNone(destination.copied)
            self.assertEqual(
                opened_titles,
                [
                    "RGB - Cosmic Clarity Starless",
                    "RGB - Cosmic Clarity Stars",
                ],
            )
            self.assertTrue(any(path.parent == artifacts_dir for path in saved_paths))

    def test_resolved_tool_executable_restores_posix_execute_bits(self):
        suffix = ".exe" if os.name == "nt" else ""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = Path(tmpdir) / f"setiastrocosmicclarity_superres{suffix}"
            tool_path.write_text("placeholder", encoding="utf-8")
            if os.name != "nt":
                tool_path.chmod(0o600)

            extension = CosmicClaritySuperResExtension(None)
            extension.settings.set("executable_path", tmpdir)

            resolved = extension._tool_executable("setiastrocosmicclarity_superres")

            self.assertEqual(resolved, tool_path)
            if os.name != "nt":
                self.assertTrue(resolved.stat().st_mode & stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()

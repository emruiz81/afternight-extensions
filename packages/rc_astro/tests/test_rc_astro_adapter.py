import json
import os
import pathlib
import stat
import sys
import tempfile
import textwrap
import unittest
from types import SimpleNamespace
from unittest import mock


PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "package"
APP_REPO = pathlib.Path(__file__).resolve().parents[4] / "afternight"
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(APP_REPO / "python" / "modules"))

import rc_astro_extension as rc  # noqa: E402
from rc_astro_extension import (  # noqa: E402
    RcAstroBxtExtension,
    RcAstroError,
    RcAstroNxtExtension,
    RcAstroSxtExtension,
)


class FakeProgress:
    def __init__(self):
        self.messages = []
        self.values = []

    def set_text(self, text):
        self.messages.append(str(text))

    def set_value(self, value):
        self.values.append(float(value))

    def is_cancelled(self):
        return False


class FakeDestination:
    def __init__(self):
        self.copied = None

    def copy_from(self, image):
        self.copied = image


def _fake_schema(product):
    parameters = [
        {
            "id": "amount",
            "type": "float",
            "label": "Amount",
            "default": 0.8,
            "min": 0,
            "max": 1,
            "step": 0.05,
        },
        {
            "id": "mode",
            "type": "choice",
            "label": "Mode",
            "default": "auto",
            "options": [["Automatic", "auto"], ["Manual", "manual"]],
        },
        {
            "id": "manual_strength",
            "type": "float",
            "label": "Manual Strength",
            "default": 0.5,
            "visibleIf": {"field": "mode", "op": "==", "value": "manual"},
            "disabledIf": {"field": "mode", "op": "!=", "value": "manual"},
        },
        {
            "id": "gpu",
            "type": "bool",
            "label": "Use GPU",
            "default": True,
        },
        {
            "id": "device",
            "type": "choice",
            "label": "Acceleration Device",
            "default": "default",
            "flag": "--device",
            "options": [["Default Device", "default"], ["CPU", "cpu"], ["DirectML GPU", "dml"]],
        },
    ]
    if product == "sxt":
        parameters.append(
            {
                "id": "stars_output",
                "type": "string",
                "label": "Stars Output",
                "flag": "--stars-output",
                "hidden": True,
            }
        )
    return {
        "schema_version": 4,
        "product": product,
        "mlVersion": {"bxt": 4, "sxt": 3, "nxt": 3}.get(product, 1),
        "parameters": parameters,
    }


def _fake_nxt_grouped_schema():
    return {
        "schema_version": 4,
        "product": "nxt",
        "mlVersion": 3,
        "parameters": [
            {"id": "csep", "type": "bool", "label": "Color Separation", "default": False, "guiOnly": True},
            {"id": "fsep", "type": "bool", "label": "Frequency Separation", "default": False, "guiOnly": True},
            {
                "id": "device",
                "type": "choice",
                "label": "Acceleration Device",
                "default": "default",
                "flag": "--device",
                "options": [["Default Device", "default"], ["CPU", "cpu"], ["DirectML GPU", "dml"]],
            },
            {
                "id": "dn",
                "type": "float",
                "label": "Denoise",
                "default": 0.0,
                "min": 0.0,
                "max": 1.0,
                "visibleIf": "!csep && !fsep",
                "flag": "--dn",
            },
            {
                "id": "di",
                "type": "float",
                "label": "Denoise Intensity",
                "default": 0.0,
                "min": 0.0,
                "max": 1.0,
                "visibleIf": "csep && !fsep",
                "flag": "--di",
            },
            {
                "id": "dc",
                "type": "float",
                "label": "Denoise Color",
                "default": 0.0,
                "min": 0.0,
                "max": 1.0,
                "visibleIf": "csep && !fsep",
                "flag": "--dc",
            },
            {
                "id": "fs",
                "type": "float",
                "label": "Frequency Scale",
                "default": 5.0,
                "min": 1.0,
                "max": 100.0,
                "visibleIf": "fsep",
                "flag": "--fs",
            },
            {"id": "it", "type": "int", "label": "Iterations", "default": 2, "min": 1, "max": 5},
            {"id": "overlap", "type": "float", "label": "Tile Overlap", "default": 0.2, "min": 0.0, "max": 0.5},
        ],
        "groups": [
            {"name": "mode_options", "label": "Options", "params": ["csep", "fsep"]},
            {"name": "denoise", "label": "Denoise", "params": ["dn", "di", "dc", "fs"]},
            {"name": "engine", "label": "Engine", "params": ["device", "it", "overlap"]},
        ],
    }


def make_fake_cli(directory, executable_name=None):
    directory = pathlib.Path(directory)
    if executable_name is None:
        executable_name = "rc-astro.cmd" if os.name == "nt" else "rc-astro"
    helper = directory / "fake_rc_astro.py"
    helper.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import pathlib
            import sys

            SCHEMAS = json.loads(os.environ["FAKE_RC_SCHEMAS"])
            CAPTURE = pathlib.Path(os.environ["FAKE_RC_CAPTURE"])
            SCHEMA_STYLE = os.environ.get("FAKE_RC_SCHEMA_STYLE", "product_json")
            LICENSE_STATUS = os.environ.get("FAKE_RC_LICENSE_STATUS", "activated").strip().lower()
            UPDATE_STATUS = os.environ.get("FAKE_RC_UPDATE_STATUS", "none").strip().lower()

            def record(kind, payload):
                existing = []
                if CAPTURE.exists():
                    existing = json.loads(CAPTURE.read_text(encoding="utf-8"))
                existing.append({"kind": kind, "payload": payload})
                CAPTURE.write_text(json.dumps(existing), encoding="utf-8")

            argv = sys.argv[1:]
            record("argv", argv)
            if argv in (["--help"], ["--help", "--json"]):
                print("Astronomical image processing tools")
                print("Version 9.9.0")
                raise SystemExit(0)
            if argv == ["--json"]:
                print(json.dumps({"schemaVersion": 4, "cliVersion": "9.9.0", "products": []}))
                raise SystemExit(0)
            if argv == ["--version"]:
                print("rc-astro 9.9.0")
                raise SystemExit(0)
            if argv == ["--device"]:
                print("default")
                print("cpu")
                print("dml")
                raise SystemExit(0)
            if SCHEMA_STYLE == "product_json" and len(argv) >= 2 and argv[1] == "--json":
                print(json.dumps(SCHEMAS[argv[0]]))
                raise SystemExit(0)
            if SCHEMA_STYLE == "product_schema_json" and len(argv) >= 3 and argv[1:] == ["schema", "--json"]:
                print(json.dumps(SCHEMAS[argv[0]]))
                raise SystemExit(0)
            if SCHEMA_STYLE == "help_only" and len(argv) == 1 and argv[0] in SCHEMAS:
                print("Usage: rc-astro " + argv[0] + " input_file [options]")
                if argv[0] == "bxt":
                    print("  --ss, --sharpen-stars (float in [0, 0.7], default 0.00)")
                    print("      Amount of stellar sharpening.")
                    print("  --ash, --adjust-star-halos (float in [-0.5, 0.5], default 0.00)")
                    print("  --nsr, --nonstellar-radius (float in [0, 8], default 0.0)")
                    print("  --ansr, --auto-nonstellar-radius, --no-ansr (default true)")
                    print("  --sn, --sharpen-nonstellar (float in [0, 1], default 0.00)")
                    print("  --correct-only")
                    print("      Correct PSF aberrations without sharpening.")
                    print("  --device (text {default,cpu,dml}, default default)")
                    print("  --ml-version (int, default 0)")
                    print("  --overlap (float in [0, 0.5], default 0.2)")
                    print("  --depth (text {8U,16U,32F,64F})")
                else:
                    print("  --amount (float in [0, 1], default 0.80)")
                    print("      Processing amount.")
                    print("  --device (text {default,cpu,dml}, default default)")
                    print("  --ansr, --no-ansr (default true)")
                raise SystemExit(0)
            if len(argv) >= 2 and argv[1] == "--activate":
                payload = sys.stdin.read()
                record("stdin", payload)
                print(json.dumps({"ok": True, "message": "activated"}))
                raise SystemExit(0)
            if len(argv) >= 2 and argv[1] == "--license":
                if LICENSE_STATUS in {"inactive", "not_activated", "unlicensed"}:
                    print("License: Not activated")
                elif LICENSE_STATUS == "unknown":
                    print("License status unavailable")
                else:
                    print("License: Activated")
                raise SystemExit(0)
            if argv[:1] == ["update"]:
                if "--install" in argv:
                    print(json.dumps({"ok": True, "message": "updated to 0.9.9"}))
                    raise SystemExit(0)
                if UPDATE_STATUS in {"available", "newer"}:
                    print(json.dumps({"ok": True, "update_available": True, "latest_version": "0.9.9"}))
                    raise SystemExit(0)
                print(json.dumps({"ok": True, "update_available": False, "message": "up to date"}))
                raise SystemExit(0)
            if argv[:1] == ["download-models"]:
                print(json.dumps({"ok": True, "message": "models downloaded"}))
                raise SystemExit(0)

            def option_value(name):
                if name not in argv:
                    return ""
                index = argv.index(name)
                if index + 1 >= len(argv):
                    return ""
                return argv[index + 1]

            output = option_value("--output") or option_value("-o")
            stars = option_value("--stars-output")
            if output:
                pathlib.Path(output).write_text("synthetic output", encoding="utf-8")
            if stars:
                pathlib.Path(stars).write_text("synthetic stars", encoding="utf-8")
            print(json.dumps({"progress": {"percent": 25, "message": "working"}}))
            print("Progress: 100%")
            raise SystemExit(0)
            """
        ).strip(),
        encoding="utf-8",
    )
    executable = directory / executable_name
    if os.name == "nt" and executable.suffix.lower() in {".cmd", ".bat"}:
        executable.write_text(
            f'@echo off\r\n"{sys.executable}" "{helper}" %*\r\n',
            encoding="utf-8",
        )
    else:
        executable.write_text(f'#!/bin/sh\nexec {sys.executable!r} {str(helper)!r} "$@"\n', encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return executable


class RcAstroAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.capture = self.root / "capture.json"
        self.executable = make_fake_cli(self.root)
        self._env = mock.patch.dict(
            os.environ,
            {
                "FAKE_RC_SCHEMAS": json.dumps({product: _fake_schema(product) for product in ("bxt", "sxt", "nxt")}),
                "FAKE_RC_CAPTURE": str(self.capture),
            },
        )
        self._env.start()
        rc._SCHEMA_CACHE.clear()

    def tearDown(self):
        self._env.stop()
        self.temp.cleanup()
        rc._SCHEMA_CACHE.clear()

    def _events(self):
        if not self.capture.exists():
            return []
        return json.loads(self.capture.read_text(encoding="utf-8"))

    def test_run_cli_streams_stdout_and_stderr_callbacks_before_process_exit(self):
        script = self.root / "streaming_cli.py"
        sentinel = self.root / "line_seen"
        script.write_text(
            textwrap.dedent(
                """
                import os
                import sys
                import time

                sentinel = sys.argv[1]
                print("stdout one", flush=True)
                print("stderr one", file=sys.stderr, flush=True)
                deadline = time.monotonic() + 5.0
                while not os.path.exists(sentinel):
                    if time.monotonic() > deadline:
                        print("sentinel timeout", file=sys.stderr, flush=True)
                        raise SystemExit(7)
                    time.sleep(0.02)
                print("stdout two", flush=True)
                """
            ).strip(),
            encoding="utf-8",
        )

        streamed = []

        def callback(entry):
            streamed.append(entry)
            if entry["stream"] == "stdout" and entry["text"] == "stdout one":
                sentinel.write_text("seen", encoding="utf-8")

        lines, console_output = rc._run_cli(
            [sys.executable, str(script), str(sentinel)],
            timeout_seconds=3.0,
            capture_console=True,
            console_callback=callback,
        )

        self.assertEqual(lines, ["stdout one", "stdout two"])
        self.assertIn({"stream": "stderr", "text": "stderr one"}, console_output)
        self.assertIn({"stream": "stderr", "text": "stderr one"}, streamed)
        self.assertTrue(sentinel.exists())

    def test_check_updates_emits_incremental_settings_console_updates(self):
        extension = RcAstroBxtExtension(None)
        streamed_updates = []

        with mock.patch.object(
            rc.afternight,
            "emit_settings_action_update",
            side_effect=lambda update: streamed_updates.append(update) or True,
            create=True,
        ):
            with mock.patch.dict(os.environ, {"FAKE_RC_UPDATE_STATUS": "available"}):
                result = extension.handle_settings_action(
                    "check_updates",
                    {
                        "resolved_cli_executable": str(self.executable),
                        "resolved_cli_version": "0.9.2",
                    },
                )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(streamed_updates), 2)
        self.assertEqual(streamed_updates[0]["transient_updates"]["settings_console_output"], "")
        self.assertTrue(
            any("append" in update["transient_updates"]["settings_console_output"] for update in streamed_updates[1:])
        )

    def test_manifest_declares_keep_open_for_native_reset_button(self):
        manifest = json.loads((PACKAGE_ROOT / "extension.json").read_text(encoding="utf-8"))
        processes = {process["id_suffix"]: process for process in manifest["processes"]}

        for process_id in ("bxt", "sxt", "nxt"):
            self.assertTrue(processes[process_id]["capabilities"]["keep_open"])

    def test_get_params_maps_synthetic_schema_conditions(self):
        extension = RcAstroBxtExtension(None)
        extension.settings.set("resolved_cli_executable", str(self.executable))

        params = extension.get_params()
        by_id = {param["id"]: param for param in params}

        self.assertEqual(by_id["amount"]["type"], "float")
        self.assertEqual(by_id["mode"]["type"], "choice")
        self.assertEqual(by_id["manual_strength"]["visible_when"], 'mode == "manual"')
        self.assertEqual(by_id["manual_strength"]["enabled_when"], 'mode == "manual"')
        self.assertIn("tool_configuration", by_id["window_meta"])
        self.assertEqual(by_id["window_meta"]["tool_configuration"]["primary_executable"], "rc-astro")
        self.assertEqual(by_id["window_meta"]["tool_configuration"]["button_label"], "Settings")
        self.assertTrue(by_id["window_meta"]["tool_configuration"]["open_extension_settings"])
        self.assertFalse(by_id["window_meta"]["tool_configuration"]["show_configured_banner"])
        section_labels = [param["label"] for param in params if param.get("type") == "section"]
        self.assertNotIn("Models", section_labels)
        self.assertIn("Engine", section_labels)
        self.assertEqual(by_id["model_version"]["type"], "choice")
        self.assertEqual(by_id["model_version"]["group"], "Engine")
        self.assertEqual(by_id["model_version"]["default"], "latest")
        self.assertIn("latest schema model version is v4", by_id["model_version"]["tooltip"])
        self.assertEqual(
            by_id["model_version"]["options"],
            [["Latest (v4)", "latest"], ["Version 2", "2"], ["Version 3", "3"], ["Version 4", "4"]],
        )
        self.assertEqual(by_id["device"]["group"], "Engine")
        self.assertEqual(by_id["device"]["default"], "default")
        self.assertEqual(by_id["device"]["options"][0], ["Default Device", "default"])
        self.assertNotIn("model_status", by_id)
        self.assertNotIn("list_models", by_id)
        self.assertNotIn("download_models", by_id)
        self.assertNotIn("force_redownload_models", by_id)

    def test_sxt_model_selector_does_not_invent_fixed_versions(self):
        extension = RcAstroSxtExtension(None)
        extension.settings.set("resolved_cli_executable", str(self.executable))

        params = extension.get_params()
        by_id = {param["id"]: param for param in params}
        section_labels = [param["label"] for param in params if param.get("type") == "section"]

        self.assertIn("Engine", section_labels)
        self.assertEqual(by_id["model_version"]["options"], [["Latest (v3)", "latest"]])
        self.assertEqual(by_id["model_version"]["group"], "Engine")
        self.assertIn("latest schema model version is v3", by_id["model_version"]["tooltip"])

    def test_model_selector_uses_explicit_schema_catalog_when_reported(self):
        schema = _fake_schema("bxt")
        schema["modelVersions"] = [2, 4]

        self.assertEqual(
            rc._model_version_options(schema),
            [["Latest (v4)", "latest"], ["Version 2", "2"], ["Version 4", "4"]],
        )

    def test_sxt_options_precede_engine_and_unscreen_requires_generated_stars(self):
        schema = rc._apply_product_schema_overrides(
            {
                "schemaVersion": 4,
                "product": "sxt",
                "mlVersion": 3,
                "parameters": [
                    {
                        "id": "overlap",
                        "type": "float",
                        "label": "Tile Overlap",
                        "flag": "--overlap",
                        "default": 0.2,
                    },
                    {
                        "id": "generate_stars_image",
                        "type": "bool",
                        "label": "Generate Stars Image",
                        "flag": "--generate-stars",
                        "default": False,
                    },
                    {
                        "id": "unscreen_stars",
                        "type": "bool",
                        "label": "Unscreen Stars",
                        "flag": "--unscreen-stars",
                        "default": False,
                    },
                    {
                        "id": "stars_output",
                        "type": "string",
                        "label": "Stars Output",
                        "flag": "--stars-output",
                        "hidden": True,
                    },
                ],
            },
            "sxt",
        )

        params = rc._schema_params(schema)
        by_id = {param["id"]: param for param in params}
        section_labels = [param["label"] for param in params if param.get("type") == "section"]

        self.assertEqual(section_labels, ["Options", "Engine"])
        self.assertEqual(
            [param["id"] for param in params if param.get("group") == "Options"],
            ["generate_stars_image", "unscreen_stars"],
        )
        self.assertEqual(
            [param["id"] for param in params if param.get("group") == "Engine"],
            ["device", "model_version", "overlap"],
        )
        self.assertEqual(by_id["unscreen_stars"]["enabled_when"], "generate_stars_image == true")

        command_without_stars = rc._command_for_schema(
            self.executable,
            "sxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {"generate_stars_image": False, "unscreen_stars": True},
        )
        self.assertNotIn("--stars-output", command_without_stars)
        self.assertNotIn("--unscreen-stars", command_without_stars)

        command_with_stars = rc._command_for_schema(
            self.executable,
            "sxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {"generate_stars_image": True, "unscreen_stars": True},
        )
        self.assertIn("--stars-output", command_with_stars)
        self.assertIn("--unscreen-stars", command_with_stars)

    def test_get_params_can_inspect_schema_from_configured_folder_before_host_record(self):
        extension = RcAstroBxtExtension(None)
        extension.settings.set("cli_folder", str(self.root))

        params = extension.get_params()
        by_id = {param["id"]: param for param in params}

        self.assertIn("amount", by_id)
        self.assertNotIn("schema_status", by_id)
        with self.assertRaises(RcAstroError):
            extension.execute(None, object(), FakeDestination(), {}, FakeProgress())

    def test_get_params_tries_schema_command_alternates(self):
        with mock.patch.dict(os.environ, {"FAKE_RC_SCHEMA_STYLE": "product_schema_json"}):
            rc._SCHEMA_CACHE.clear()
            extension = RcAstroBxtExtension(None)
            extension.settings.set("resolved_cli_executable", str(self.executable))

            params = extension.get_params()

        by_id = {param["id"]: param for param in params}
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn("amount", by_id)
        self.assertNotIn("schema_status", by_id)
        self.assertIn(["bxt", "schema", "--json"], argv_events)

    def test_get_params_falls_back_to_cli_help_when_json_schema_is_unavailable(self):
        with mock.patch.dict(os.environ, {"FAKE_RC_SCHEMA_STYLE": "help_only"}):
            rc._SCHEMA_CACHE.clear()
            extension = RcAstroNxtExtension(None)
            extension.settings.set("resolved_cli_executable", str(self.executable))

            params = extension.get_params()

        by_id = {param["id"]: param for param in params}
        self.assertNotIn("schema_status", by_id)
        self.assertEqual(by_id["amount"]["type"], "float")
        self.assertEqual(by_id["amount"]["min"], 0)
        self.assertEqual(by_id["amount"]["max"], 1)
        self.assertEqual(by_id["device"]["type"], "choice")
        self.assertEqual(by_id["ansr"]["type"], "bool")
        self.assertTrue(by_id["ansr"]["default"])

    def test_nxt_params_are_grouped_into_options_denoise_and_engine_cards(self):
        schemas = {product: _fake_schema(product) for product in ("bxt", "sxt")}
        schemas["nxt"] = _fake_nxt_grouped_schema()
        with mock.patch.dict(os.environ, {"FAKE_RC_SCHEMAS": json.dumps(schemas)}):
            rc._SCHEMA_CACHE.clear()
            extension = RcAstroNxtExtension(None)
            extension.settings.set("resolved_cli_executable", str(self.executable))

            params = extension.get_params()

        by_id = {param["id"]: param for param in params}
        section_labels = [param["label"] for param in params if param.get("type") == "section"]
        self.assertEqual(section_labels, ["Options", "Denoise", "Engine"])
        self.assertEqual(
            [param["id"] for param in params if param.get("group") == "Options"],
            ["csep", "fsep"],
        )
        self.assertEqual([param["id"] for param in params if param.get("group") == "Denoise"], ["dn", "di", "dc", "fs"])
        self.assertEqual(
            [param["id"] for param in params if param.get("group") == "Engine"],
            ["device", "model_version", "it", "overlap"],
        )
        self.assertEqual(by_id["dn"]["visible_when"], "csep != true && fsep != true")
        self.assertEqual(by_id["dn"]["default"], 0.9)
        self.assertEqual(by_id["di"]["visible_when"], "csep == true && fsep != true")
        self.assertEqual(by_id["dc"]["visible_when"], "csep == true && fsep != true")
        self.assertEqual(by_id["fs"]["visible_when"], "fsep == true")
        self.assertEqual(by_id["model_version"]["type"], "choice")
        self.assertEqual(by_id["model_version"]["group"], "Engine")
        self.assertEqual(by_id["model_version"]["default"], "latest")
        self.assertEqual(by_id["device"]["default"], "default")
        self.assertEqual(
            by_id["model_version"]["options"],
            [["Latest (v3)", "latest"], ["Version 2", "2"], ["Version 3", "3"]],
        )

    def test_bxt_help_schema_hides_technical_fields_and_disables_correct_only_controls(self):
        with mock.patch.dict(os.environ, {"FAKE_RC_SCHEMA_STYLE": "help_only"}):
            rc._SCHEMA_CACHE.clear()
            extension = RcAstroBxtExtension(None)
            extension.settings.set("resolved_cli_executable", str(self.executable))

            params = extension.get_params()

        by_id = {param["id"]: param for param in params}
        options_ids = [param["id"] for param in params if param.get("group") == "Options"]
        engine_ids = [param["id"] for param in params if param.get("group") == "Engine"]
        section_labels = [param["label"] for param in params if param.get("type") == "section"]
        self.assertEqual(section_labels, ["Stellar Adjustments", "Non stellar adjustments", "Options", "Engine"])
        self.assertEqual(options_ids, ["correct_only"])
        self.assertEqual(engine_ids, ["device", "model_version", "overlap"])
        self.assertIn("correct_only", by_id)
        self.assertIn("model_version", by_id)
        self.assertIn("device", by_id)
        self.assertIn("overlap", by_id)
        self.assertNotIn("depth", by_id)
        self.assertNotIn("ml_version", by_id)
        self.assertEqual(by_id["sharpen_stars"]["group"], "Stellar Adjustments")
        self.assertEqual(by_id["adjust_star_halos"]["group"], "Stellar Adjustments")
        self.assertEqual(by_id["nonstellar_radius"]["group"], "Non stellar adjustments")
        self.assertEqual(by_id["auto_nonstellar_radius"]["group"], "Non stellar adjustments")
        self.assertEqual(by_id["sharpen_nonstellar"]["group"], "Non stellar adjustments")
        self.assertEqual(by_id["model_version"]["group"], "Engine")
        self.assertEqual(by_id["correct_only"]["group"], "Options")
        self.assertEqual(by_id["device"]["group"], "Engine")
        self.assertEqual(by_id["overlap"]["group"], "Engine")
        self.assertEqual(by_id["sharpen_stars"]["default"], 0.5)
        self.assertEqual(by_id["adjust_star_halos"]["default"], 0.0)
        self.assertTrue(by_id["auto_nonstellar_radius"]["default"])
        self.assertEqual(by_id["sharpen_nonstellar"]["default"], 0.5)
        self.assertFalse(by_id["correct_only"]["default"])
        self.assertEqual(by_id["device"]["default"], "default")
        self.assertEqual(by_id["overlap"]["default"], 0.2)
        for field_id in (
            "sharpen_stars",
            "adjust_star_halos",
            "auto_nonstellar_radius",
            "sharpen_nonstellar",
        ):
            self.assertEqual(by_id[field_id]["enabled_when"], "correct_only != true")
        self.assertEqual(
            by_id["nonstellar_radius"]["enabled_when"],
            "correct_only != true && auto_nonstellar_radius != true",
        )
        self.assertNotIn("enabled_when", by_id["device"])
        self.assertNotIn("enabled_when", by_id["overlap"])

    def test_bxt_json_modes_restore_correct_only_control_and_command_flag(self):
        schema = rc._apply_product_schema_overrides(
            {
                "schemaVersion": 4,
                "key": "bxt",
                "mlVersion": 4,
                "parameters": [
                    {"id": "overlap", "type": "float", "label": "Tile Overlap", "flag": "--overlap", "default": 0.1},
                    {"id": "ss", "type": "float", "label": "Sharpen Stars", "flag": "--ss", "default": 0.0},
                    {"id": "ash", "type": "float", "label": "Adjust Star Halos", "flag": "--ash", "default": 0.1},
                    {"id": "nsr", "type": "float", "label": "Nonstellar Radius", "flag": "--nsr", "default": 2.0},
                    {
                        "id": "ansr",
                        "type": "bool",
                        "label": "Auto Nonstellar Radius",
                        "flag": "--ansr",
                        "default": False,
                    },
                    {"id": "sn", "type": "float", "label": "Sharpen Nonstellar", "flag": "--sn", "default": 0.2},
                ],
                "modes": [
                    {
                        "name": "correctOnlyMode",
                        "label": "Correct Only",
                        "description": "Correct PSF aberrations without sharpening.",
                        "flag": "--correct-only",
                        "pins": {"ansr": True, "ash": 0.0, "nsr": 0.0, "sn": 0.0, "ss": 0.0},
                    }
                ],
            },
            "bxt",
        )

        params = rc._schema_params(schema)
        by_id = {param["id"]: param for param in params}
        options_ids = [param["id"] for param in params if param.get("group") == "Options"]
        engine_ids = [param["id"] for param in params if param.get("group") == "Engine"]
        section_labels = [param["label"] for param in params if param.get("type") == "section"]

        self.assertEqual(section_labels, ["Stellar Adjustments", "Non stellar adjustments", "Options", "Engine"])
        self.assertEqual(options_ids, ["correct_only"])
        self.assertEqual(engine_ids, ["device", "model_version", "overlap"])
        self.assertEqual(by_id["correct_only"]["type"], "bool")
        self.assertEqual(by_id["correct_only"]["label"], "Correct Only")
        self.assertEqual(by_id["correct_only"]["group"], "Options")
        self.assertEqual(by_id["model_version"]["group"], "Engine")
        self.assertFalse(by_id["correct_only"]["default"])
        self.assertEqual(by_id["correct_only"]["tooltip"], "Correct PSF aberrations without sharpening.")
        self.assertEqual(by_id["device"]["group"], "Engine")
        self.assertEqual(by_id["device"]["default"], "default")
        self.assertEqual(by_id["overlap"]["group"], "Engine")
        self.assertEqual(by_id["overlap"]["default"], 0.2)

        command = rc._command_for_schema(
            self.executable,
            "bxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {
                "correct_only": True,
                "ss": 0.6,
                "ash": 0.2,
                "nsr": 3.0,
                "ansr": False,
                "sn": 0.8,
                "device": "cpu",
                "overlap": 0.3,
            },
        )

        self.assertIn("--correct-only", command)
        self.assertIn("--device", command)
        self.assertIn("cpu", command)
        self.assertIn("--overlap", command)
        self.assertIn("0.3", command)
        self.assertNotIn("--ss", command)
        self.assertNotIn("--ash", command)
        self.assertNotIn("--nsr", command)
        self.assertNotIn("--ansr", command)
        self.assertNotIn("--sn", command)

    def test_bxt_correct_only_command_keeps_engine_overlap_and_strips_sharpening_flags(self):
        schema = rc._apply_product_schema_overrides(
            {
                "schema_version": 3,
                "product": "bxt",
                "parameters": [
                    {"id": "sharpen_stars", "type": "float", "flag": "--sharpen-stars", "default": 0.0},
                    {"id": "adjust_star_halos", "type": "float", "flag": "--adjust-star-halos", "default": 0.0},
                    {"id": "nonstellar_radius", "type": "float", "flag": "--nonstellar-radius", "default": 0.0},
                    {
                        "id": "auto_nonstellar_radius",
                        "type": "bool",
                        "flag": "--auto-nonstellar-radius",
                        "default": True,
                    },
                    {"id": "sharpen_nonstellar", "type": "float", "flag": "--sharpen-nonstellar", "default": 0.0},
                    {"id": "correct_only", "type": "bool", "flag": "--correct-only", "default": False},
                    {
                        "id": "engine",
                        "type": "choice",
                        "flag": "--engine",
                        "default": "auto",
                        "options": ["auto", "cpu"],
                    },
                    {"id": "overlap", "type": "float", "flag": "--overlap", "default": 0.2},
                    {"id": "depth", "type": "choice", "flag": "--depth", "options": ["16U", "32F"]},
                ],
            },
            "bxt",
        )

        command = rc._command_for_schema(
            self.executable,
            "bxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {
                "correct_only": True,
                "sharpen_stars": 0.6,
                "adjust_star_halos": 0.2,
                "nonstellar_radius": 3.0,
                "auto_nonstellar_radius": False,
                "sharpen_nonstellar": 0.8,
                "engine": "cpu",
                "overlap": 0.3,
                "depth": "16U",
            },
        )

        self.assertIn("--correct-only", command)
        self.assertIn("--engine", command)
        self.assertIn("cpu", command)
        self.assertIn("--overlap", command)
        self.assertIn("0.3", command)
        self.assertNotIn("--sharpen-stars", command)
        self.assertNotIn("--adjust-star-halos", command)
        self.assertNotIn("--nonstellar-radius", command)
        self.assertNotIn("--auto-nonstellar-radius", command)
        self.assertNotIn("--sharpen-nonstellar", command)
        self.assertNotIn("--depth", command)

    def test_schema_v4_legacy_engine_field_is_translated_to_device(self):
        schema = rc._apply_product_schema_overrides(
            {
                "schema_version": 4,
                "product": "bxt",
                "parameters": [
                    {"id": "correct_only", "type": "bool", "flag": "--correct-only", "default": False},
                    {
                        "id": "engine",
                        "type": "choice",
                        "flag": "--engine",
                        "default": "default",
                        "options": ["default", "cpu"],
                    },
                    {"id": "overlap", "type": "float", "flag": "--overlap", "default": 0.2},
                ],
            },
            "bxt",
        )

        params = rc._schema_params(schema)
        by_id = {param["id"]: param for param in params}
        command = rc._command_for_schema(
            self.executable,
            "bxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {"correct_only": True, "device": "cpu", "overlap": 0.3},
        )

        self.assertIn("device", by_id)
        self.assertNotIn("engine", by_id)
        self.assertIn("--device", command)
        self.assertIn("cpu", command)
        self.assertNotIn("--engine", command)

    def test_bxt_command_uses_curated_defaults_when_params_are_omitted(self):
        schema = rc._apply_product_schema_overrides(
            {
                "schema_version": 3,
                "product": "bxt",
                "parameters": [
                    {"id": "sharpen_stars", "type": "float", "flag": "--sharpen-stars", "default": 0.0},
                    {"id": "adjust_star_halos", "type": "float", "flag": "--adjust-star-halos", "default": 0.5},
                    {"id": "nonstellar_radius", "type": "float", "flag": "--nonstellar-radius", "default": 0.0},
                    {
                        "id": "auto_nonstellar_radius",
                        "type": "bool",
                        "flag": "--auto-nonstellar-radius",
                        "default": False,
                    },
                    {"id": "sharpen_nonstellar", "type": "float", "flag": "--sharpen-nonstellar", "default": 0.1},
                    {"id": "correct_only", "type": "bool", "flag": "--correct-only", "default": True},
                    {
                        "id": "device",
                        "type": "choice",
                        "flag": "--device",
                        "default": "cpu",
                        "options": ["default", "cpu"],
                    },
                    {"id": "overlap", "type": "float", "flag": "--overlap", "default": 0.4},
                ],
            },
            "bxt",
        )

        command = rc._command_for_schema(
            self.executable,
            "bxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {},
        )

        self.assertIn("--sharpen-stars", command)
        self.assertIn("0.5", command)
        self.assertIn("--adjust-star-halos", command)
        self.assertIn("0.0", command)
        self.assertIn("--auto-nonstellar-radius", command)
        self.assertIn("--sharpen-nonstellar", command)
        self.assertIn("0.5", command)
        self.assertNotIn("--correct-only", command)
        self.assertNotIn("--device", command)
        self.assertNotIn("cpu", command)
        self.assertIn("--overlap", command)
        self.assertIn("0.2", command)

    def test_command_pins_selected_model_version(self):
        command = rc._command_for_schema(
            self.executable,
            "bxt",
            _fake_schema("bxt"),
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {"model_version": "3"},
        )

        self.assertIn("--ml-version", command)
        self.assertIn("3", command)

    def test_command_omits_latest_model_version_pin(self):
        command = rc._command_for_schema(
            self.executable,
            "bxt",
            _fake_schema("bxt"),
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {"model_version": "latest"},
        )

        self.assertNotIn("--ml-version", command)

    def test_nxt_command_skips_gui_only_and_inactive_conditional_fields(self):
        schema = rc._apply_product_schema_overrides(_fake_nxt_grouped_schema(), "nxt")

        command = rc._command_for_schema(
            self.executable,
            "nxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {"csep": False, "fsep": False, "dn": 0.5, "di": 0.7, "dc": 0.4, "fs": 9.0},
        )

        self.assertIn("--dn", command)
        self.assertNotIn("--csep", command)
        self.assertNotIn("--fsep", command)
        self.assertNotIn("--di", command)
        self.assertNotIn("--dc", command)
        self.assertNotIn("--fs", command)

        command = rc._command_for_schema(
            self.executable,
            "nxt",
            schema,
            pathlib.Path("input.fit"),
            pathlib.Path("output.fit"),
            pathlib.Path("stars.fit"),
            {"csep": True, "fsep": False, "dn": 0.5, "di": 0.7, "dc": 0.4, "fs": 9.0},
        )

        self.assertIn("--di", command)
        self.assertIn("--dc", command)
        self.assertNotIn("--dn", command)
        self.assertNotIn("--fs", command)

    def test_shared_settings_schema_exposes_detection_and_status_fields(self):
        schemas = []
        for extension_class in (RcAstroBxtExtension, RcAstroSxtExtension, RcAstroNxtExtension):
            schema = extension_class(None).get_settings_params()
            schemas.append(schema)

        self.assertEqual(schemas[0], schemas[1])
        self.assertEqual(schemas[0], schemas[2])
        by_id = {field["id"]: field for field in schemas[0]}
        self.assertNotIn("cli_folder", by_id)
        self.assertIn("tool_configuration", by_id["cli_executable"])
        self.assertEqual(by_id["cli_executable"]["type"], "file_path")
        self.assertEqual(by_id["cli_executable"]["tool_configuration"]["primary_executable"], "rc-astro")
        self.assertIn("rc-astro-cli", by_id["cli_executable"]["tool_configuration"]["primary_executable_candidates"])
        self.assertIn("CLI", by_id["cli_executable"]["tool_configuration"]["candidate_subdirectories"])
        self.assertEqual(by_id["cli_executable"]["tool_configuration"]["version_arguments"], ["--json"])
        self.assertIn("cliVersion", by_id["cli_executable"]["tool_configuration"]["version_pattern"])
        self.assertFalse(by_id["cli_executable"]["tool_configuration"]["show_configured_banner"])
        self.assertEqual(by_id["cli_executable"]["group"], "CLI Connection")
        self.assertEqual(by_id["cli_executable"]["group_style"], "card")
        self.assertEqual(by_id["cli_executable"]["label"], "Executable")
        self.assertEqual(by_id["cli_executable"]["button_label"], "Browse...")
        self.assertTrue(by_id["cli_executable"]["read_only"])
        self.assertEqual(by_id["resolver_diagnostic"]["label"], "Status")
        self.assertEqual(by_id["resolved_cli_version"]["label"], "Version")
        self.assertEqual(by_id["resolved_cli_executable"]["label"], "Resolved Executable")
        self.assertFalse(by_id["resolved_cli_executable"]["visible"])
        self.assertFalse(by_id["resolution_source"]["visible"])
        self.assertIn("detect_installation", by_id)
        self.assertEqual(by_id["detect_installation"]["title"], "Find RC-Astro CLI")
        self.assertTrue(by_id["refresh_status_on_open"]["autorun"])
        self.assertFalse(by_id["refresh_status_on_open"]["show_status"])
        self.assertFalse(by_id["refresh_status_on_open"]["visible"])
        self.assertEqual(by_id["refresh_status_on_open"]["action_id"], "refresh_status")
        self.assertFalse(by_id["resolved_cli_executable"]["persist"])
        self.assertFalse(by_id["resolved_cli_version"]["persist"])
        self.assertFalse(by_id["activation_status"]["persist"])
        self.assertFalse(by_id["activation_status"]["visible"])
        self.assertEqual(by_id["activation_product"]["group"], "Products")
        self.assertFalse(by_id["activation_product"]["visible"])
        self.assertEqual(
            by_id["activation_product"]["options"],
            [["BlurXTerminator", "bxt"], ["StarXTerminator", "sxt"], ["NoiseXTerminator", "nxt"]],
        )
        self.assertFalse(by_id["activation_email"]["visible"])
        self.assertFalse(by_id["activation_key"]["visible"])
        self.assertEqual(by_id["activation_console_output"]["type"], "console_output")
        self.assertEqual(by_id["activation_console_output"]["default"], "")
        self.assertEqual(by_id["activation_console_output"]["placeholder"], "Activation output will appear here.")
        self.assertTrue(by_id["activation_console_output"]["collapsed_when_empty"])
        self.assertFalse(by_id["activation_console_output"]["visible"])
        self.assertFalse(by_id["activation_console_output"]["persist"])
        self.assertEqual(by_id["open_activation_dialog"]["label"], "Activation...")
        self.assertEqual(by_id["open_activation_dialog"]["action_id"], "activate_selected")
        self.assertEqual(
            by_id["open_activation_dialog"]["dialog"]["fields"],
            ["activation_product", "activation_email", "activation_key", "activation_console_output"],
        )
        self.assertTrue(by_id["open_activation_dialog"]["dialog"]["keep_open_on_accept"])
        self.assertEqual(
            by_id["open_activation_dialog"]["dialog"]["accept_label"],
            "Activate Selected Product",
        )
        self.assertNotIn("activate_selected", by_id)
        for field_id in ("bxt_activation_status", "sxt_activation_status", "nxt_activation_status"):
            self.assertIn(field_id, by_id)
            self.assertEqual(by_id[field_id]["type"], "status")
            self.assertEqual(by_id[field_id]["group"], "Products")
            self.assertEqual(by_id[field_id]["group_style"], "card")
            self.assertFalse(by_id[field_id]["persist"])
            self.assertFalse(by_id[field_id]["enabled"])
        self.assertNotIn("update_status", by_id)
        schema_text = json.dumps(schemas[0])
        self.assertNotIn("Latest Version", schema_text)
        self.assertNotIn("Run Check Updates to look for a newer RC-Astro CLI", schema_text)
        self.assertFalse(by_id["update_available"]["persist"])
        self.assertFalse(by_id["update_available"]["visible"])
        self.assertEqual(by_id["settings_console_output"]["type"], "console_output")
        self.assertEqual(by_id["settings_console_output"]["default"], "")
        self.assertEqual(
            by_id["settings_console_output"]["placeholder"],
            "Check Updates and Update output will appear here.",
        )
        self.assertTrue(by_id["settings_console_output"]["collapsed_when_empty"])
        self.assertFalse(by_id["settings_console_output"]["persist"])
        self.assertEqual(by_id["settings_console_output"]["group"], "Updates")
        self.assertEqual(by_id["settings_console_output"]["min_lines"], 18)
        self.assertEqual(by_id["download_update"]["label"], "Update")
        self.assertEqual(by_id["download_update"]["enabled_when"], "update_available == true")
        self.assertNotIn("download_models", by_id)
        self.assertNotIn("force_redownload_models", by_id)

    def test_cli_version_parses_json_catalog_and_text_banner(self):
        self.assertEqual(rc._extract_cli_version_from_text('{"schemaVersion":4,"cliVersion":"0.9.9"}'), "0.9.9")
        self.assertEqual(
            rc._extract_cli_version_from_text("Astronomical image processing tools\nVersion 0.9.2 (build 105)"),
            "0.9.2 (build 105)",
        )

    def test_missing_host_resolved_cli_fails_closed(self):
        extension = RcAstroNxtExtension(None)
        with mock.patch.object(rc, "_default_cli_directories", return_value=[]):
            with mock.patch.object(rc, "_path_cli_directories", return_value=[]):
                params = extension.get_params()
                diagnostics = extension.validate_process({}, {})
        by_id = {param["id"]: param for param in params}
        self.assertIn("schema_status", by_id)
        self.assertFalse(diagnostics[0]["ok"])
        self.assertIn("RC-Astro CLI is not ready", diagnostics[0]["message"])
        with self.assertRaises(RcAstroError):
            extension.execute(None, object(), FakeDestination(), {}, FakeProgress())

    def test_validate_process_blocks_unactivated_product(self):
        extension = RcAstroBxtExtension(None)
        extension.settings.set("resolved_cli_executable", str(self.executable))

        with mock.patch.dict(os.environ, {"FAKE_RC_LICENSE_STATUS": "not_activated"}):
            diagnostics = extension.validate_process({}, {})

        self.assertEqual(len(diagnostics), 1)
        self.assertFalse(diagnostics[0]["ok"])
        self.assertEqual(diagnostics[0]["severity"], "error")
        self.assertIn("BlurXTerminator is not activated", diagnostics[0]["message"])
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn(["bxt", "--license"], argv_events)

    def test_execute_blocks_unactivated_product_before_image_io(self):
        extension = RcAstroBxtExtension(None)
        extension.settings.set("resolved_cli_executable", str(self.executable))

        with mock.patch.dict(os.environ, {"FAKE_RC_LICENSE_STATUS": "not_activated"}):
            with mock.patch.object(rc.io, "save") as save_image:
                with self.assertRaisesRegex(RcAstroError, "BlurXTerminator is not activated"):
                    extension.execute(None, object(), FakeDestination(), {}, FakeProgress())

        save_image.assert_not_called()

    def test_execute_uses_resolved_cli_generates_command_and_loads_output(self):
        extension = RcAstroBxtExtension(None)
        extension.settings.set("resolved_cli_executable", str(self.executable))
        destination = FakeDestination()
        progress = FakeProgress()

        with mock.patch.object(rc.io, "save", side_effect=lambda _image, path: pathlib.Path(path).write_text("input")):
            with mock.patch.object(rc.io, "load", side_effect=lambda path: SimpleNamespace(path=path)):
                extension.execute(
                    None,
                    SimpleNamespace(metadata={}),
                    destination,
                    {"amount": 0.42, "mode": "manual", "manual_strength": 0.7, "gpu": True},
                    progress,
                )

        self.assertIsNotNone(destination.copied)
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        process_argv = argv_events[-1]
        self.assertEqual(process_argv[0], "bxt")
        self.assertNotIn("--input", process_argv)
        self.assertIn("-o", process_argv)
        self.assertIn("--overwrite", process_argv)
        self.assertIn("--amount", process_argv)
        self.assertIn("0.42", process_argv)
        self.assertIn("--gpu", process_argv)
        self.assertIn(100.0, progress.values)

    def test_sxt_opens_secondary_stars_output(self):
        extension = RcAstroSxtExtension(None)
        extension.settings.set("resolved_cli_executable", str(self.executable))
        opened = []

        with mock.patch.object(rc.io, "save", side_effect=lambda _image, path: pathlib.Path(path).write_text("input")):
            with mock.patch.object(rc.io, "load", side_effect=lambda path: SimpleNamespace(path=path)):
                with mock.patch.object(
                    rc.ui, "open_image", side_effect=lambda image, title: opened.append((image, title))
                ):
                    extension.execute(None, object(), FakeDestination(), {"amount": 0.2}, FakeProgress())

        self.assertEqual(opened[0][1], "RC-Astro SXT Stars")

    def test_activation_uses_stdin_not_argv_for_credentials(self):
        extension = RcAstroBxtExtension(None)
        result = extension.handle_settings_action(
            "activate_selected",
            {
                "resolved_cli_executable": str(self.executable),
                "activation_email": "user@example.test",
                "activation_key": "SECRET-KEY",
            },
        )

        self.assertTrue(result["ok"])
        argv_text = json.dumps([event["payload"] for event in self._events() if event["kind"] == "argv"])
        self.assertNotIn("SECRET-KEY", argv_text)
        self.assertNotIn("user@example.test", argv_text)
        stdin_payloads = [event["payload"] for event in self._events() if event["kind"] == "stdin"]
        self.assertEqual(len(stdin_payloads), 1)
        self.assertIn("SECRET-KEY", stdin_payloads[0])
        self.assertIn("user@example.test", stdin_payloads[0])
        console_output = result["transient_updates"]["activation_console_output"]
        self.assertIn("activated", json.dumps(console_output))
        self.assertNotIn("SECRET-KEY", json.dumps(console_output))
        self.assertNotIn("user@example.test", json.dumps(console_output))

    def test_activation_uses_selected_product_from_settings(self):
        extension = RcAstroBxtExtension(None)
        result = extension.handle_settings_action(
            "activate_selected",
            {
                "resolved_cli_executable": str(self.executable),
                "activation_product": "sxt",
                "activation_email": "user@example.test",
                "activation_key": "SECRET-KEY",
            },
        )

        self.assertTrue(result["ok"])
        self.assertIn("StarXTerminator", result["message"])
        self.assertEqual(result["transient_updates"]["activation_status"], "Activated")
        self.assertEqual(result["transient_updates"]["sxt_activation_status"], "Activated")
        self.assertIn("activated", json.dumps(result["transient_updates"]["activation_console_output"]))
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn(["sxt", "--activate"], argv_events)
        self.assertNotIn(["bxt", "--activate"], argv_events)

    def test_detect_installation_persists_candidate_executable_and_updates_status_fields(self):
        extension = RcAstroBxtExtension(None)
        result = extension.handle_settings_action(
            "detect_installation",
            {
                "resolved_cli_executable": str(self.executable),
                "configured_folder": str(self.root),
                "resolution_source": "candidate_directory",
                "resolved_cli_version": "9.9.0",
                "resolver_diagnostic": "RC-Astro CLI is configured and ready to use.",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["settings_updates"]["cli_executable"], str(self.executable))
        transient = result["transient_updates"]
        self.assertEqual(transient["cli_executable"], str(self.executable))
        self.assertEqual(transient["resolved_cli_executable"], str(self.executable))
        self.assertEqual(transient["resolved_cli_version"], "9.9.0")
        self.assertEqual(transient["resolution_source"], "candidate_directory")
        self.assertEqual(transient["activation_status"], "Activated")
        self.assertEqual(transient["bxt_activation_status"], "Activated")
        self.assertEqual(transient["sxt_activation_status"], "Activated")
        self.assertEqual(transient["nxt_activation_status"], "Activated")

    def test_detect_installation_falls_back_to_selected_parent_folder_alias_subdir(self):
        extension = RcAstroBxtExtension(None)
        install_root = self.root / "install"
        cli_dir = install_root / "CLI"
        cli_dir.mkdir(parents=True)
        executable_name = "rc-astro-cli.cmd" if os.name == "nt" else "rc-astro-cli"
        executable = make_fake_cli(cli_dir, executable_name=executable_name)

        result = extension.handle_settings_action(
            "detect_installation",
            {
                "cli_folder": str(install_root),
            },
        )

        self.assertTrue(result["ok"], result.get("message"))
        self.assertEqual(pathlib.Path(result["settings_updates"]["cli_executable"]), executable.resolve())
        transient = result["transient_updates"]
        self.assertEqual(pathlib.Path(transient["cli_executable"]), executable.resolve())
        self.assertEqual(pathlib.Path(transient["resolved_cli_executable"]), executable.resolve())
        self.assertEqual(transient["resolved_cli_version"], "9.9.0")
        self.assertEqual(transient["resolution_source"], "settings")
        self.assertEqual(transient["activation_status"], "Activated")
        self.assertEqual(transient["bxt_activation_status"], "Activated")
        self.assertEqual(transient["sxt_activation_status"], "Activated")
        self.assertEqual(transient["nxt_activation_status"], "Activated")

    def test_refresh_status_updates_version_and_activation_status_fields(self):
        extension = RcAstroBxtExtension(None)
        result = extension.handle_settings_action(
            "refresh_status",
            {
                "resolved_cli_executable": str(self.executable),
                "configured_folder": str(self.root),
                "resolution_source": "settings",
            },
        )

        self.assertTrue(result["ok"])
        transient = result["transient_updates"]
        self.assertEqual(transient["cli_executable"], str(self.executable))
        self.assertEqual(transient["resolved_cli_version"], "9.9.0")
        self.assertEqual(transient["activation_status"], "Activated")
        self.assertEqual(transient["bxt_activation_status"], "Activated")
        self.assertEqual(transient["sxt_activation_status"], "Activated")
        self.assertEqual(transient["nxt_activation_status"], "Activated")
        self.assertIn("Product activation statuses refreshed", result["message"])

    def test_refresh_status_reports_unavailable_products_when_cli_is_missing(self):
        extension = RcAstroBxtExtension(None)
        with mock.patch.object(rc, "_default_cli_directories", return_value=[]):
            with mock.patch.object(rc, "_path_cli_directories", return_value=[]):
                result = extension.handle_settings_action("refresh_status", {})

        self.assertFalse(result["ok"])
        transient = result["transient_updates"]
        self.assertIn("Could not find", transient["resolver_diagnostic"])
        self.assertEqual(transient["activation_status"], transient["bxt_activation_status"])
        self.assertEqual(transient["sxt_activation_status"], transient["bxt_activation_status"])
        self.assertEqual(transient["nxt_activation_status"], transient["bxt_activation_status"])

    def test_update_action_requires_positive_update_check(self):
        extension = RcAstroBxtExtension(None)
        result = extension.handle_settings_action(
            "download_update",
            {"resolved_cli_executable": str(self.executable)},
        )

        self.assertFalse(result["ok"])
        self.assertIn("No RC-Astro CLI update", result["message"])
        self.assertFalse(result["transient_updates"]["update_available"])
        self.assertIn("up to date", json.dumps(result["transient_updates"]["settings_console_output"]))
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn(["update"], argv_events)
        self.assertNotIn(["update", "--install"], argv_events)

    def test_update_action_rechecks_when_availability_snapshot_is_missing(self):
        extension = RcAstroBxtExtension(None)

        with mock.patch.dict(os.environ, {"FAKE_RC_UPDATE_STATUS": "available"}):
            result = extension.handle_settings_action(
                "download_update",
                {
                    "resolved_cli_executable": str(self.executable),
                    "resolved_cli_version": "0.9.2",
                },
            )

        self.assertTrue(result["ok"], result.get("message"))
        self.assertFalse(result["transient_updates"]["update_available"])
        self.assertIn("updated to 0.9.9", result["message"])
        self.assertIn("updated to 0.9.9", json.dumps(result["transient_updates"]["settings_console_output"]))
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn(["update"], argv_events)
        self.assertIn(["update", "--install"], argv_events)

    def test_check_updates_enables_update_when_newer_version_reported(self):
        extension = RcAstroBxtExtension(None)

        with mock.patch.dict(os.environ, {"FAKE_RC_UPDATE_STATUS": "available"}):
            result = extension.handle_settings_action(
                "check_updates",
                {
                    "resolved_cli_executable": str(self.executable),
                    "resolved_cli_version": "0.9.2",
                },
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tone"], "warning")
        self.assertIn("0.9.9", result["message"])
        self.assertTrue(result["transient_updates"]["update_available"])
        self.assertIn("0.9.9", json.dumps(result["transient_updates"]["settings_console_output"]))
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn(["update"], argv_events)
        self.assertNotIn(["update", "--install"], argv_events)

    def test_update_action_runs_install_after_available_check(self):
        extension = RcAstroBxtExtension(None)

        result = extension.handle_settings_action(
            "download_update",
            {
                "resolved_cli_executable": str(self.executable),
                "update_available": True,
            },
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["transient_updates"]["update_available"])
        self.assertIn("updated to 0.9.9", result["message"])
        self.assertIn("updated to 0.9.9", json.dumps(result["transient_updates"]["settings_console_output"]))
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn(["update", "--install"], argv_events)

    def test_check_updates_keeps_update_disabled_when_current(self):
        extension = RcAstroBxtExtension(None)

        result = extension.handle_settings_action(
            "check_updates",
            {
                "resolved_cli_executable": str(self.executable),
                "resolved_cli_version": "9.9.0",
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["tone"], "success")
        self.assertFalse(result["transient_updates"]["update_available"])
        self.assertIn("up to date", json.dumps(result["transient_updates"]["settings_console_output"]))

    def test_model_actions_are_process_local(self):
        extension = RcAstroBxtExtension(None)
        extension.settings.set("resolved_cli_executable", str(self.executable))

        status_update = extension.handle_param_action("list_models", None, None, {})
        download_update = extension.handle_param_action("download_models", None, None, {})
        force_update = extension.handle_param_action("force_redownload_models", None, None, {})

        self.assertIn("latest schema model version is v4", status_update["model_status"])
        self.assertIn("Model download command completed", download_update["model_status"])
        self.assertIn("Model download command completed", force_update["model_status"])
        argv_events = [event["payload"] for event in self._events() if event["kind"] == "argv"]
        self.assertIn(["download-models"], argv_events)
        self.assertIn(["download-models", "--force"], argv_events)


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: GPL-3.0-or-later
"""AfterNight adapter for user-installed RC-Astro XTerminator CLI tools."""

from __future__ import annotations

import json
import os
import pathlib
import queue
import re
import signal
import subprocess
import tempfile
import threading
import time
import uuid

import afternight
from afternight import io, ui


_CLI_NAME = "rc-astro"
_CLI_EXECUTABLE_BASENAMES = (
    "rc-astro",
    "rcastro",
    "rc-astro-cli",
    "rcastro-cli",
    "RCAstroCLI",
    "RCAstro",
)
_CLI_SEARCH_SUBDIRECTORIES = ("", "CLI", "cli", "bin", "Bin")
_CLI_SETTING_KEY = "cli_executable"
_LEGACY_CLI_SETTING_KEY = "cli_folder"
_RESOLVED_CLI_KEY = "resolved_cli_executable"
_MODEL_STATUS_PARAM_ID = "model_status"
_MODEL_VERSION_PARAM_ID = "model_version"
_UPDATE_AVAILABLE_PARAM_ID = "update_available"
_DEVICE_OPTIONS_SETTING_KEY = "device_options_json"
_SETTINGS_CONSOLE_PARAM_ID = "settings_console_output"
_ACTIVATION_CONSOLE_PARAM_ID = "activation_console_output"
_ACTIVATION_PRODUCT_PARAM_ID = "activation_product"
_ACTIVATION_STATUS_PARAM_IDS = {
    "bxt": "bxt_activation_status",
    "sxt": "sxt_activation_status",
    "nxt": "nxt_activation_status",
}
_SCHEMA_TIMEOUT_SECONDS = 5.0
_ACTION_TIMEOUT_SECONDS = 30.0
_UPDATE_TIMEOUT_SECONDS = 300.0
_RUN_TIMEOUT_SECONDS = 60.0 * 60.0
_SUPPORTED_SCHEMA_MAJORS = {1, 2, 3, 4}
_PRODUCTS = {
    "bxt": {
        "name": "BlurXTerminator",
        "display": "RC-Astro BlurXTerminator",
        "category": "sharpening_enhancement",
    },
    "sxt": {
        "name": "StarXTerminator",
        "display": "RC-Astro StarXTerminator",
        "category": "star_object",
    },
    "nxt": {
        "name": "NoiseXTerminator",
        "display": "RC-Astro NoiseXTerminator",
        "category": "denoising",
    },
}
_MISSING = object()
_SCHEMA_CACHE = {}
_DEVICE_OPTIONS_CACHE = {}
_TEXT_PROGRESS_RE = re.compile(r".*?([0-9]+(?:\.[0-9]+)?)\s*%")
_FIELD_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_TECHNICAL_OUTPUT_FIELDS = {"depth"}
_MODEL_SELECTOR_FIELDS = {"ml_version", "mlVersion", "model_version", "modelVersion"}
_BXT_CORRECT_ONLY_FIELD_IDS = {"correct_only", "correctOnlyMode"}
_BXT_CORRECT_ONLY_DISABLED_FIELD_IDS = {
    "ss",
    "sharpen_stars",
    "ash",
    "adjust_star_halos",
    "nsr",
    "nonstellar_radius",
    "ansr",
    "auto_nonstellar_radius",
    "sn",
    "sharpen_nonstellar",
}
_BXT_CORRECT_ONLY_ALLOWED_FIELD_IDS = {
    *_BXT_CORRECT_ONLY_FIELD_IDS,
    _MODEL_VERSION_PARAM_ID,
    "device",
    "engine",
    "overlap",
}
_BXT_NONSTELLAR_RADIUS_ENABLED_WHEN = {
    "nsr": "correct_only != true && ansr != true",
    "nonstellar_radius": "correct_only != true && auto_nonstellar_radius != true",
}
_BXT_FIELD_GROUPS = {
    "ss": "Stellar Adjustments",
    "sharpen_stars": "Stellar Adjustments",
    "ash": "Stellar Adjustments",
    "adjust_star_halos": "Stellar Adjustments",
    "nsr": "Non stellar adjustments",
    "nonstellar_radius": "Non stellar adjustments",
    "ansr": "Non stellar adjustments",
    "auto_nonstellar_radius": "Non stellar adjustments",
    "sn": "Non stellar adjustments",
    "sharpen_nonstellar": "Non stellar adjustments",
    "correct_only": "Options",
    "correctOnlyMode": "Options",
    "device": "Engine",
    _MODEL_VERSION_PARAM_ID: "Engine",
    "engine": "Engine",
    "overlap": "Engine",
}
_BXT_GROUP_ORDER = {
    "Stellar Adjustments": 0,
    "Non stellar adjustments": 1,
    "Options": 2,
    "Engine": 3,
}
_BXT_FIELD_ORDER = {
    "ss": 0,
    "sharpen_stars": 0,
    "ash": 1,
    "adjust_star_halos": 1,
    "ansr": 0,
    "auto_nonstellar_radius": 0,
    "nsr": 1,
    "nonstellar_radius": 1,
    "sn": 2,
    "sharpen_nonstellar": 2,
    "correct_only": 0,
    "correctOnlyMode": 0,
    "device": 0,
    "engine": 0,
    _MODEL_VERSION_PARAM_ID: 1,
    "overlap": 2,
}
_BXT_FIELD_DEFAULTS = {
    "ss": 0.5,
    "sharpen_stars": 0.5,
    "ash": 0.0,
    "adjust_star_halos": 0.0,
    "ansr": True,
    "auto_nonstellar_radius": True,
    "sn": 0.5,
    "sharpen_nonstellar": 0.5,
    "correct_only": False,
    "correctOnlyMode": False,
    "device": "default",
    "engine": "auto",
    "overlap": 0.2,
}
_BXT_MODE_FIELD_ALIASES = {
    "correctOnlyMode": "correct_only",
}
_PARAM_VALUE_ALIASES = {
    "ss": ("sharpen_stars",),
    "sharpen_stars": ("ss",),
    "ash": ("adjust_star_halos",),
    "adjust_star_halos": ("ash",),
    "nsr": ("nonstellar_radius",),
    "nonstellar_radius": ("nsr",),
    "ansr": ("auto_nonstellar_radius",),
    "auto_nonstellar_radius": ("ansr",),
    "sn": ("sharpen_nonstellar",),
    "sharpen_nonstellar": ("sn",),
    "correct_only": ("correctOnlyMode",),
    "correctOnlyMode": ("correct_only",),
    "dn": ("denoise", "amount"),
    "denoise": ("dn", "amount"),
    "amount": ("dn", "denoise"),
    "stars": (
        "generate_stars",
        "generate_star_image",
        "generate_stars_image",
        "generateStars",
        "generateStarImage",
        "generateStarsImage",
        "create_stars",
        "create_star_image",
        "create_stars_image",
    ),
    "generate_stars_image": (
        "stars",
        "generate_stars",
        "generate_star_image",
        "generateStars",
        "generateStarImage",
        "generateStarsImage",
        "create_stars",
        "create_star_image",
        "create_stars_image",
    ),
    "generate_stars": ("generate_stars_image",),
    "generate_star_image": ("generate_stars_image",),
    "generateStars": ("generate_stars_image",),
    "generateStarImage": ("generate_stars_image",),
    "generateStarsImage": ("generate_stars_image",),
    "create_stars": ("generate_stars_image",),
    "create_star_image": ("generate_stars_image",),
    "create_stars_image": ("generate_stars_image",),
    "unscreen": (
        "unscreen_stars",
        "unscreenStars",
        "unscreen_star_image",
        "unscreen_stars_image",
        "unscreenStarImage",
        "unscreenStarsImage",
    ),
    "unscreen_stars": (
        "unscreen",
        "unscreenStars",
        "unscreen_star_image",
        "unscreen_stars_image",
        "unscreenStarImage",
        "unscreenStarsImage",
    ),
    "unscreenStars": ("unscreen_stars",),
    "unscreen_star_image": ("unscreen_stars",),
    "unscreen_stars_image": ("unscreen_stars",),
    "unscreenStarImage": ("unscreen_stars",),
    "unscreenStarsImage": ("unscreen_stars",),
}
_NXT_FIELD_GROUPS = {
    "csep": "Options",
    "color_separation": "Options",
    "fsep": "Options",
    "frequency_separation": "Options",
    _MODEL_VERSION_PARAM_ID: "Engine",
    "dn": "Denoise",
    "denoise": "Denoise",
    "amount": "Denoise",
    "di": "Denoise",
    "denoise_intensity": "Denoise",
    "dc": "Denoise",
    "denoise_color": "Denoise",
    "dhf": "Denoise",
    "denoise_high_frequency": "Denoise",
    "dlf": "Denoise",
    "denoise_low_frequency": "Denoise",
    "dihf": "Denoise",
    "denoise_intensity_high_frequency": "Denoise",
    "dilf": "Denoise",
    "denoise_intensity_low_frequency": "Denoise",
    "dchf": "Denoise",
    "denoise_color_high_frequency": "Denoise",
    "dclf": "Denoise",
    "denoise_color_low_frequency": "Denoise",
    "fs": "Denoise",
    "frequency_scale": "Denoise",
    "manual_strength": "Denoise",
    "device": "Engine",
    "engine": "Engine",
    "gpu": "Engine",
    "it": "Engine",
    "iterations": "Engine",
    "overlap": "Engine",
}
_NXT_GROUP_ORDER = {
    "Options": 0,
    "Denoise": 1,
    "Engine": 2,
}
_NXT_FIELD_ORDER = {
    "csep": 0,
    "color_separation": 0,
    "fsep": 1,
    "frequency_separation": 1,
    "dn": 0,
    "denoise": 0,
    "amount": 0,
    "di": 1,
    "denoise_intensity": 1,
    "dc": 2,
    "denoise_color": 2,
    "dhf": 3,
    "denoise_high_frequency": 3,
    "dlf": 4,
    "denoise_low_frequency": 4,
    "dihf": 5,
    "denoise_intensity_high_frequency": 5,
    "dilf": 6,
    "denoise_intensity_low_frequency": 6,
    "dchf": 7,
    "denoise_color_high_frequency": 7,
    "dclf": 8,
    "denoise_color_low_frequency": 8,
    "fs": 9,
    "frequency_scale": 9,
    "manual_strength": 10,
    "device": 0,
    "engine": 0,
    "gpu": 0,
    _MODEL_VERSION_PARAM_ID: 1,
    "it": 2,
    "iterations": 2,
    "overlap": 3,
}
_NXT_FIELD_DEFAULTS = {
    "dn": 0.9,
    "denoise": 0.9,
    "amount": 0.9,
}
_SXT_GENERATE_STARS_TOKENS = {
    "stars",
    "generatestars",
    "generatestarimage",
    "generatestarsimage",
    "createstars",
    "createstarimage",
    "createstarsimage",
    "starimage",
    "starsimage",
}
_SXT_UNSCREEN_STARS_TOKENS = {
    "unscreen",
    "unscreenstars",
    "unscreenstarimage",
    "unscreenstarsimage",
}
_SXT_FIELD_GROUPS = {
    "stars": "Options",
    "generate_stars": "Options",
    "generate_star_image": "Options",
    "generate_stars_image": "Options",
    "generateStars": "Options",
    "generateStarImage": "Options",
    "generateStarsImage": "Options",
    "create_stars": "Options",
    "create_star_image": "Options",
    "create_stars_image": "Options",
    "unscreen": "Options",
    "unscreen_stars": "Options",
    "unscreenStars": "Options",
    "unscreen_star_image": "Options",
    "unscreen_stars_image": "Options",
    "unscreenStarImage": "Options",
    "unscreenStarsImage": "Options",
    _MODEL_VERSION_PARAM_ID: "Engine",
    "device": "Engine",
    "engine": "Engine",
    "gpu": "Engine",
    "overlap": "Engine",
}
_SXT_GROUP_ORDER = {
    "Options": 0,
    "Engine": 1,
    "": 2,
}
_SXT_FIELD_ORDER = {
    "stars": 0,
    "generate_stars": 0,
    "generate_star_image": 0,
    "generate_stars_image": 0,
    "generateStars": 0,
    "generateStarImage": 0,
    "generateStarsImage": 0,
    "create_stars": 0,
    "create_star_image": 0,
    "create_stars_image": 0,
    "unscreen": 1,
    "unscreen_stars": 1,
    "unscreenStars": 1,
    "unscreen_star_image": 1,
    "unscreen_stars_image": 1,
    "unscreenStarImage": 1,
    "unscreenStarsImage": 1,
    "device": 0,
    "engine": 0,
    "gpu": 0,
    _MODEL_VERSION_PARAM_ID: 1,
    "overlap": 2,
}
_MODEL_VERSION_FALLBACK_MINIMUMS = {
    "bxt": 2,
    "nxt": 2,
}
_DEFAULT_DEVICE_OPTION = ["Automatically select device", "default"]
_DEVICE_DEFAULT_TOKENS = {
    "default",
    "auto",
    "automatic",
    "automaticdevice",
    "automaticallyselect",
    "automaticallyselectdevice",
}
_DEVICE_VALUE_LABELS = {
    "default": _DEFAULT_DEVICE_OPTION[0],
    "auto": _DEFAULT_DEVICE_OPTION[0],
    "cpu": "CPU",
    "dml": "DirectML GPU",
    "directml": "DirectML GPU",
    "cuda": "CUDA GPU",
    "opencl": "OpenCL GPU",
    "metal": "Metal GPU",
    "coreml": "Core ML",
    "rocm": "ROCm GPU",
}
_COMMON_DEVICE_FIELD = {
    "id": "device",
    "type": "choice",
    "label": "Acceleration Device",
    "default": "default",
    "flag": "--device",
    "options": [_DEFAULT_DEVICE_OPTION],
}
_COMMON_ENGINE_FIELD = {
    "id": "engine",
    "type": "choice",
    "label": "Inference Engine",
    "default": "auto",
    "flag": "--engine",
    "options": ["auto", "dml", "cpu"],
}
_HELP_OPTION_RE = re.compile(
    r"^\s*(?P<names>(?:-[A-Za-z0-9],\s*)?--[A-Za-z0-9][A-Za-z0-9-]*(?:,\s*--[A-Za-z0-9][A-Za-z0-9-]*)*)"
    r"(?:\s*\((?P<meta>[^)]*)\))?"
)
_HELP_SKIP_FLAGS = {
    "--activate",
    "--debug",
    "--help",
    "--license",
    "--output",
    "--overwrite",
}


class RcAstroError(RuntimeError):
    """Raised for user-facing RC-Astro adapter failures."""


class RcAstroCliError(RcAstroError):
    """Raised when the RC-Astro CLI fails after producing console output."""

    def __init__(self, message, console_output=None):
        super().__init__(message)
        self.console_output = list(console_output or [])


def _console_entry(stream, text):
    return {"stream": str(stream or "stdout"), "text": str(text or "")}


def _console_output_from_lines(lines, stream="stdout"):
    return [_console_entry(stream, line) for line in lines if str(line).strip()]


def _console_updates_for_action(action_id, console_output):
    if not console_output:
        return {}
    if action_id == "activate_selected":
        return {_ACTIVATION_CONSOLE_PARAM_ID: console_output}
    if action_id in {"check_updates", "download_update", "install_update"}:
        return {_SETTINGS_CONSOLE_PARAM_ID: console_output}
    return {}


def _console_param_id_for_action(action_id):
    if action_id == "activate_selected":
        return _ACTIVATION_CONSOLE_PARAM_ID
    if action_id in {"check_updates", "download_update", "install_update"}:
        return _SETTINGS_CONSOLE_PARAM_ID
    return ""


def _emit_settings_action_update(update):
    emitter = getattr(afternight, "emit_settings_action_update", None)
    if emitter is None:
        return False
    try:
        return bool(emitter(update))
    except Exception:
        return False


def _clear_console_for_action(action_id):
    param_id = _console_param_id_for_action(action_id)
    if not param_id:
        return
    _emit_settings_action_update({"transient_updates": {param_id: ""}})


def _console_stream_callback_for_action(action_id):
    param_id = _console_param_id_for_action(action_id)
    if not param_id:
        return None

    def callback(entry):
        _emit_settings_action_update({"transient_updates": {param_id: {"append": [entry]}}})

    return callback


def _progress_cancelled(progress):
    try:
        return bool(progress.is_cancelled())
    except Exception:
        return False


def _progress_text(progress, text):
    try:
        progress.set_text(str(text))
    except Exception:
        pass


def _progress_value(progress, value):
    try:
        progress.set_value(max(0.0, min(100.0, float(value))))
    except Exception:
        pass


def _log_info(message):
    afternight.log_info(str(message), component="extension.rc_astro")


def _log_warning(message):
    afternight.log_warning(str(message), component="extension.rc_astro")


def _session_temp_root():
    try:
        base = afternight.session_paths().temp_dir()
    except Exception:
        base = ""
    return pathlib.Path(base or tempfile.gettempdir())


class _Workspace:
    def __init__(self):
        self.root = _session_temp_root() / f"rc_astro_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=True)
        self.input_path = self.root / "input.fit"
        self.output_path = self.root / "output.fit"
        self.stars_path = self.root / "stars.fit"


_RESERVED_METADATA_KEYS = {
    "SIMPLE",
    "BITPIX",
    "BZERO",
    "BSCALE",
    "EXTEND",
    "BLOCKED",
    "BLANK",
    "BUNIT",
}
_STRUCTURED_METADATA_MAP_KEYS = {"fits_header", "exif_header"}
_STRUCTURED_METADATA_CARD_KEYS = {"fits_cards", "exif_entries"}
_STRUCTURED_METADATA_SKIP_KEYS = {"astrometry"}


def _metadata_key_is_reserved(key):
    upper = str(key or "").strip().upper()
    return upper in _RESERVED_METADATA_KEYS or upper.startswith("NAXIS")


def _metadata_is_scalar(value):
    return value is None or isinstance(value, (str, int, float, bool))


def _metadata_entries_from_cards(cards):
    if not isinstance(cards, list):
        return
    for card in cards:
        if not isinstance(card, dict):
            continue
        key = card.get("key", card.get("name"))
        value = card.get("value")
        if key and _metadata_is_scalar(value):
            yield key, value


def _metadata_entries(metadata):
    if not hasattr(metadata, "items"):
        return
    for key, value in metadata.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        key_lower = key_text.lower()
        if key_lower in _STRUCTURED_METADATA_MAP_KEYS:
            if hasattr(value, "items"):
                for nested_key, nested_value in value.items():
                    if nested_key and _metadata_is_scalar(nested_value):
                        yield nested_key, nested_value
            continue
        if key_lower in _STRUCTURED_METADATA_CARD_KEYS:
            yield from _metadata_entries_from_cards(value)
            continue
        if key_lower in _STRUCTURED_METADATA_SKIP_KEYS:
            continue
        if _metadata_is_scalar(value):
            yield key_text, value


def _metadata_snapshot(image):
    try:
        metadata = image.metadata
    except Exception:
        return {}
    if not hasattr(metadata, "items"):
        return {}
    return dict(metadata)


def _restore_original_metadata(image, metadata):
    if not metadata or not hasattr(image, "set_metadata"):
        return
    for key, value in _metadata_entries(metadata) or ():
        if _metadata_key_is_reserved(key):
            continue
        try:
            image.set_metadata(str(key), "" if value is None else str(value))
        except Exception as exc:
            _log_warning(f"Could not restore RC-Astro output metadata key {key}: {exc}")


def _terminate_process(process, reason):
    if process.poll() is not None:
        return
    _log_warning(f"Terminating RC-Astro CLI process for {reason}.")
    if os.name == "nt":
        ctrl_break = getattr(subprocess, "CTRL_BREAK_EVENT", None)
        if ctrl_break is not None:
            try:
                process.send_signal(ctrl_break)
                process.wait(timeout=2.0)
            except Exception:
                pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2.0)
        except Exception:
            pass
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                process.kill()
    try:
        process.wait(timeout=2.0)
    except Exception:
        pass


def _json_event(line):
    try:
        value = json.loads(line)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _progress_from_event(event):
    candidates = []
    if isinstance(event.get("progress"), dict):
        candidates.append(event["progress"].get("value"))
        candidates.append(event["progress"].get("percent"))
    candidates.extend([event.get("percent"), event.get("progress")])
    for candidate in candidates:
        try:
            value = float(candidate)
        except TypeError, ValueError:
            continue
        return value * 100.0 if 0.0 <= value <= 1.0 else value
    return None


def _message_from_event(event):
    if isinstance(event.get("progress"), dict):
        message = event["progress"].get("message")
        if message:
            return str(message)
    for key in ("message", "status", "stage"):
        if event.get(key):
            return str(event[key])
    return ""


def _reader_thread(pipe, stream_name, output_queue):
    try:
        for raw_line in pipe:
            output_queue.put((stream_name, raw_line))
    finally:
        output_queue.put((stream_name, None))


def _run_cli(
    command,
    *,
    timeout_seconds,
    progress=None,
    stdin_payload=None,
    cwd=None,
    capture_console=False,
    console_callback=None,
):
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=os.name != "nt",
        creationflags=creationflags,
    )
    if stdin_payload is not None:
        assert process.stdin is not None
        try:
            process.stdin.write(stdin_payload)
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()

    start = time.monotonic()
    output_lines = []
    all_output_lines = []
    console_output = []
    stream_queue = queue.Queue()
    readers = []
    active_readers = 0
    for stream_name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
        if pipe is None:
            continue
        active_readers += 1
        reader = threading.Thread(
            target=_reader_thread,
            args=(pipe, stream_name, stream_queue),
            daemon=True,
        )
        reader.start()
        readers.append(reader)

    def check_process_state():
        if progress is not None and _progress_cancelled(progress):
            _terminate_process(process, "cancellation")
            if capture_console:
                raise RcAstroCliError("RC-Astro processing was cancelled.", console_output)
            raise RcAstroError("RC-Astro processing was cancelled.")
        if timeout_seconds > 0 and time.monotonic() - start > timeout_seconds:
            _terminate_process(process, "timeout")
            if capture_console:
                raise RcAstroCliError("RC-Astro CLI timed out.", console_output)
            raise RcAstroError("RC-Astro CLI timed out.")

    try:
        while active_readers > 0:
            try:
                stream_name, raw_line = stream_queue.get(timeout=0.05)
            except queue.Empty:
                check_process_state()
                continue
            if raw_line is None:
                active_readers -= 1
                check_process_state()
                continue
            line = raw_line.rstrip()
            if line:
                all_output_lines.append(line)
                if len(all_output_lines) > 500:
                    all_output_lines.pop(0)
                if stream_name == "stdout":
                    output_lines.append(line)
                    if len(output_lines) > 500:
                        output_lines.pop(0)
                if capture_console or console_callback is not None:
                    entry = _console_entry(stream_name, line)
                    if capture_console:
                        console_output.append(entry)
                        if len(console_output) > 500:
                            console_output.pop(0)
                    if console_callback is not None:
                        try:
                            console_callback(entry)
                        except Exception:
                            pass
                event = _json_event(line)
                if event:
                    message = _message_from_event(event)
                    if message and progress is not None:
                        _progress_text(progress, message)
                    percent = _progress_from_event(event)
                    if percent is not None and progress is not None:
                        _progress_value(progress, percent)
                else:
                    match = _TEXT_PROGRESS_RE.match(line)
                    if match and progress is not None:
                        _progress_value(progress, float(match.group(1)))
            check_process_state()
        process.wait()
    finally:
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except Exception:
                    pass
        for reader in readers:
            reader.join(timeout=0.2)

    if process.returncode != 0:
        tail = "\n".join(all_output_lines[-40:]) or "The CLI produced no output."
        error_message = f"RC-Astro CLI exited with status {process.returncode}.\n\n{tail}"
        if capture_console:
            raise RcAstroCliError(error_message, console_output or _console_output_from_lines(all_output_lines[-40:]))
        raise RcAstroError(error_message)
    return (output_lines, console_output) if capture_console else output_lines


def _sxt_stars_output_paths(output_lines, workspace):
    paths = [workspace.stars_path] if workspace.stars_path.exists() else []
    workspace_root = workspace.root.resolve()

    def add_path(value):
        if not isinstance(value, str) or not value.strip():
            return
        candidate = pathlib.Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_root / candidate
        try:
            candidate = candidate.resolve()
            candidate.relative_to(workspace_root)
        except OSError, ValueError:
            return
        if candidate.is_file() and candidate not in paths:
            paths.append(candidate)

    def collect(value, key=""):
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                collect(child_value, str(child_key))
            return
        if isinstance(value, list):
            for item in value:
                collect(item, key)
            return
        token = _identity_token(key)
        if "star" in token and "starless" not in token and (token == "stars" or "output" in token or "path" in token):
            add_path(value)

    for line in output_lines:
        event = _json_event(line)
        if event:
            collect(event)
    try:
        workspace_files = workspace_root.iterdir()
    except OSError:
        workspace_files = ()
    for candidate in workspace_files:
        token = _identity_token(candidate.stem)
        if candidate.is_file() and "star" in token and "starless" not in token:
            add_path(str(candidate))
    return paths


def _resolved_cli_from_mapping(mapping):
    raw_executable = str(mapping.get(_RESOLVED_CLI_KEY, "") or "").strip()
    if not raw_executable:
        raise RcAstroError("RC-Astro CLI is not resolved by the host.")
    executable = pathlib.Path(raw_executable)
    if not executable.is_file():
        raise RcAstroError(f"Host-resolved RC-Astro CLI does not exist: {executable}")
    if os.name != "nt":
        mode = executable.stat().st_mode
        executable.chmod(mode | 0o111)
    return executable


def _schema_version_major(schema):
    raw = schema.get("schema_version", schema.get("schemaVersion", schema.get("version", 0)))
    try:
        return int(str(raw).split(".", 1)[0])
    except Exception:
        return 0


def _extract_cli_version_from_text(text):
    text = str(text or "").strip()
    if not text:
        return ""
    try:
        payload = json.loads(_json_payload_from_lines(text.splitlines()))
    except Exception:
        payload = None
    if isinstance(payload, dict):
        version = str(payload.get("cliVersion", payload.get("cli_version", "")) or "").strip()
        if version:
            return version
    match = re.search(r'(?:\bVersion\s+|"cliVersion"\s*:\s*")([^"\r\n]+)', text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def _cli_version(executable):
    for arguments in (["--json"], ["--help", "--json"], ["--help"], ["--version"]):
        try:
            lines = _run_cli([executable, *arguments], timeout_seconds=3.0)
        except Exception:
            continue
        text = "\n".join(lines)
        version = _extract_cli_version_from_text(text)
        if version:
            return version
        if arguments == ["--version"] and lines:
            return lines[-1].strip()
    return ""


def _schema_inspection_commands(executable, product):
    return [
        [executable, "schema", product, "--json"],
        [executable, product, "--schema", "--json"],
        [executable, product, "--schema"],
        [executable, product, "schema", "--json"],
        [executable, "--schema", product, "--json"],
        [executable, product, "--dump-schema", "--json"],
        [executable, product, "--json-schema"],
        [executable, product, "--json"],
    ]


def _json_payload_from_lines(lines):
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(payload, (dict, list)):
                return payload

    payload = "\n".join(lines).strip()
    if not payload:
        raise json.JSONDecodeError("empty JSON payload", "", 0)
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        starts = [index for index in (payload.find("{"), payload.find("[")) if index >= 0]
        ends = [index for index in (payload.rfind("}"), payload.rfind("]")) if index >= 0]
        if not starts or not ends:
            raise
    return json.loads(payload[min(starts) : max(ends) + 1])


def _strip_ansi(text):
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", str(text or ""))


def _device_label_for_value(value):
    text = str(value or "").strip()
    key = re.sub(r"[^a-z0-9]+", "", text.lower())
    if key in _DEVICE_VALUE_LABELS:
        return _DEVICE_VALUE_LABELS[key]
    if text.islower() or "_" in text or "-" in text:
        return text.replace("_", " ").replace("-", " ").title()
    return text


def _normalise_device_value(value):
    text = _strip_ansi(value).strip().strip("`'\"")
    text = re.sub(r"^\[\s*|\s*\]$", "", text).strip()
    text = re.sub(r"^\(?\s*(?:default|selected|current)\s*\)?\s+", "", text, flags=re.IGNORECASE).strip()
    text = text.strip().strip(",;")
    if _identity_token(text) in _DEVICE_DEFAULT_TOKENS:
        return "default"
    return text


def _normalise_device_label(label):
    text = _strip_ansi(label).strip().strip("`'\"")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(",;")
    if _identity_token(text) in _DEVICE_DEFAULT_TOKENS:
        return _DEFAULT_DEVICE_OPTION[0]
    return text


def _device_text_has_identifier(text):
    return bool(re.search(r"[A-Za-z0-9]", str(text or "")))


def _is_device_output_footer_line(line):
    text = str(line or "").strip()
    lowered = text.lower()
    token = _identity_token(text)
    if token in {"eg", "example", "examples"}:
        return True
    if re.match(r"^(?:e\.?\s*g\.?|for example)\b", lowered):
        return True
    if lowered.startswith(("select a device", "choose a device")):
        return True
    if "device" in lowered and lowered.startswith(("run ", "use ", "with ")):
        return True
    if re.match(r"^device\s+[A-Za-z0-9_.:-]+\.?$", text, flags=re.IGNORECASE):
        return True
    return False


def _append_device_option(options, seen, value, label=""):
    value_text = _normalise_device_value(value)
    raw_label = _normalise_device_label(label)
    combined_token = _identity_token(f"{value_text} {raw_label}".strip())
    if _identity_token(raw_label) in _DEVICE_DEFAULT_TOKENS or combined_token in _DEVICE_DEFAULT_TOKENS:
        value_text = "default"
    if not value_text or not _device_text_has_identifier(value_text):
        return
    key = value_text.lower()
    if key in seen:
        return
    label_text = raw_label if _device_text_has_identifier(raw_label) else _device_label_for_value(value_text)
    if not _device_text_has_identifier(label_text):
        return
    if value_text.isdigit() and label_text == value_text:
        return
    seen.add(key)
    options.append([label_text, value_text])


def _append_device_options_from_payload(options, seen, payload):
    if isinstance(payload, dict):
        for key in (
            "devices",
            "availableDevices",
            "available_devices",
            "accelerationDevices",
            "acceleration_devices",
            "deviceOptions",
            "device_options",
        ):
            value = payload.get(key)
            if isinstance(value, (list, tuple, dict)):
                _append_device_options_from_payload(options, seen, value)
                return
        value = payload.get("id", payload.get("value", payload.get("key", payload.get("device"))))
        label = payload.get("label", payload.get("display", payload.get("title", payload.get("name"))))
        if value is None and label is not None:
            value = label
            label = ""
        if value is not None:
            _append_device_option(options, seen, value, label)
            return
        for key, value in payload.items():
            if isinstance(value, str):
                _append_device_option(options, seen, key, value)
        return
    if isinstance(payload, (list, tuple)):
        for item in payload:
            _append_device_options_from_payload(options, seen, item)
        return
    if isinstance(payload, str):
        for item in payload.split(","):
            _append_device_option(options, seen, item)


def _append_device_options_from_text(options, seen, lines):
    for raw_line in lines:
        line = _strip_ansi(raw_line).strip()
        if not line:
            continue
        line = re.sub(r"^[>*+\-\s]+", "", line).strip()
        line = re.sub(r"^\d+[.)]\s*", "", line).strip()
        if not line:
            continue
        if _identity_token(line) in _DEVICE_DEFAULT_TOKENS:
            _append_device_option(options, seen, "default", _DEFAULT_DEVICE_OPTION[0])
            continue
        lowered = line.lower()
        if _is_device_output_footer_line(line):
            break
        if not line or line.startswith("--") or lowered.startswith(("usage", "version")):
            continue
        if lowered.rstrip(":") in {
            "device",
            "devices",
            "available devices",
            "available acceleration devices",
            "acceleration devices",
        }:
            continue
        if ":" in line:
            left, right = line.split(":", 1)
            if "device" in left.lower():
                separator = "," if "," in right else None
                for item in right.split(separator):
                    _append_device_option(options, seen, item)
                continue
            if "device" not in left.lower():
                _append_device_option(options, seen, left, right)
                continue
        if "," in line:
            for item in line.split(","):
                _append_device_option(options, seen, item)
            continue
        parts = re.split(r"\s+-\s+|\t+", line, maxsplit=1)
        if len(parts) == 2:
            _append_device_option(options, seen, parts[0], parts[1])
            continue
        match = re.match(r"^([A-Za-z0-9_.:-]+)\s+\(([^)]+)\)$", line)
        if match:
            _append_device_option(options, seen, match.group(1), match.group(2))
            continue
        match = re.match(r"^([A-Za-z0-9_.:-]+)(?:\s+(.+))?$", line)
        if match:
            value, label = match.group(1), match.group(2) or ""
            _append_device_option(options, seen, value, label)


def _parse_device_options(lines):
    options = [_DEFAULT_DEVICE_OPTION.copy()]
    seen = {"default"}
    try:
        payload = _json_payload_from_lines(lines)
    except Exception:
        payload = None
    if payload is not None:
        _append_device_options_from_payload(options, seen, payload)
        if options:
            return options
    _append_device_options_from_text(options, seen, lines)
    return options


def _normalised_device_options(options):
    normalised = []
    seen = set()
    for item in options or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            label, value = item[0], item[1]
        elif isinstance(item, dict):
            label = item.get("label", item.get("name", item.get("value")))
            value = item.get("value", item.get("id", label))
        else:
            label = value = item
        _append_device_option(normalised, seen, value, label)
    if not any(str(value).strip().lower() == "default" for _label, value in normalised):
        normalised.insert(0, _DEFAULT_DEVICE_OPTION.copy())
    return normalised


def _device_options_json(options):
    return json.dumps(_normalised_device_options(options), separators=(",", ":"))


def _device_options_from_json(value):
    text = str(value or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except Exception:
        return []
    return _normalised_device_options(payload)


def _device_options_from_settings(settings):
    try:
        raw_options = settings.get(_DEVICE_OPTIONS_SETTING_KEY, "")
    except Exception:
        raw_options = ""
    options = _device_options_from_json(raw_options)
    if options:
        return options

    try:
        raw_executable = str(settings.get(_RESOLVED_CLI_KEY, "") or settings.get(_CLI_SETTING_KEY, "") or "").strip()
        version = str(settings.get("resolved_cli_version", "") or "").strip()
    except Exception:
        raw_executable = ""
        version = ""
    if not raw_executable:
        return []
    try:
        resolved = str(pathlib.Path(raw_executable).resolve())
    except Exception:
        resolved = raw_executable
    cache_keys = [(resolved, version), (resolved, "")]
    cache_keys.extend(key for key in _DEVICE_OPTIONS_CACHE if key[0] == resolved and key not in cache_keys)
    for key in cache_keys:
        cached = _DEVICE_OPTIONS_CACHE.get(key)
        if cached:
            return _normalised_device_options(cached)
    return []


def _device_option_setting_updates(executable, version=""):
    options = _device_options_for_cli(executable, version)
    if not options:
        return {}
    return {_DEVICE_OPTIONS_SETTING_KEY: _device_options_json(options)}


def _device_options_for_cli(executable, version=""):
    try:
        resolved = str(pathlib.Path(executable).resolve())
    except Exception:
        resolved = str(executable)
    key = (resolved, str(version or ""))
    if key in _DEVICE_OPTIONS_CACHE:
        return [list(option) for option in _DEVICE_OPTIONS_CACHE[key]]
    try:
        lines, console_output = _run_cli([executable, "--device"], timeout_seconds=3.0, capture_console=True)
    except Exception:
        options = []
    else:
        output_lines = [entry["text"] for entry in console_output] if console_output else lines
        options = _parse_device_options(output_lines)
    _DEVICE_OPTIONS_CACHE[key] = [list(option) for option in options]
    return [list(option) for option in options]


def _schema_runtime_device_options(schema):
    raw_options = schema.get("_afternight_device_options")
    if not isinstance(raw_options, list):
        return []
    options = []
    for item in raw_options:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            options.append([str(item[0]), str(item[1])])
    return options


def _schema_uses_device(schema):
    if _schema_version_major(schema) >= 4:
        return True
    for field in [*_schema_fields(schema), *_schema_mode_fields(schema)]:
        field_id = _schema_field_id(field)
        flag = str(field.get("flag", "") or "").strip()
        if field_id == "device" or flag == "--device":
            return True
    return False


def _apply_runtime_device_options(schema, executable, version=""):
    if not _schema_uses_device(schema):
        return schema
    options = _device_options_for_cli(executable, version)
    if not options:
        return schema
    schema["_afternight_device_options"] = [list(option) for option in options]
    for field in _schema_fields(schema):
        field_id = _schema_field_id(field)
        flag = str(field.get("flag", "") or "").strip()
        if field_id != "device" and flag != "--device":
            continue
        field["type"] = "choice"
        field["options"] = [list(option) for option in options]
        field.setdefault("default", "default")
    return schema


def _schema_from_json_payload(payload, product):
    if isinstance(payload, list):
        return {"schema_version": 3, "product": product, "parameters": payload}
    if not isinstance(payload, dict):
        return payload

    products = payload.get("products")
    if isinstance(products, dict) and isinstance(products.get(product), (dict, list)):
        return _schema_from_json_payload(products[product], product)
    if isinstance(payload.get(product), (dict, list)):
        return _schema_from_json_payload(payload[product], product)
    for key in ("schema", "param_schema", "params_schema"):
        if isinstance(payload.get(key), (dict, list)):
            schema = _schema_from_json_payload(payload[key], product)
            if isinstance(schema, dict):
                schema.setdefault("product", product)
                schema.setdefault("schema_version", payload.get("schema_version", payload.get("version", 3)))
            return schema
    normalized = dict(payload)
    if "schemaVersion" in normalized:
        normalized.setdefault("schema_version", normalized.get("schemaVersion"))
    if "key" in normalized:
        normalized.setdefault("product", normalized.get("key"))
    return normalized


def _validate_product_schema(schema, product):
    if not isinstance(schema, dict):
        raise RcAstroError(f"RC-Astro {product.upper()} schema inspection did not return an object.")
    declared_product = str(schema.get("product", product)).strip().lower()
    if declared_product and declared_product != product:
        raise RcAstroError(f"RC-Astro schema product mismatch: expected {product}, received {declared_product}.")
    if _schema_version_major(schema) not in _SUPPORTED_SCHEMA_MAJORS:
        raise RcAstroError("RC-Astro schema version is not supported by this adapter.")


def _field_id_from_flag(flag):
    return str(flag).lstrip("-").replace("-", "_")


def _label_from_field_id(field_id):
    return str(field_id).replace("_", " ").title()


def _number_from_text(text):
    try:
        return int(text)
    except Exception:
        return float(text)


def _help_default(meta, field_type):
    match = re.search(r"\bdefault\s+([^\s,]+)", meta, flags=re.IGNORECASE)
    if not match:
        return False if field_type == "bool" else None
    text = match.group(1).strip().strip("'\"")
    if field_type == "bool":
        return text.lower() in {"1", "true", "yes", "on"}
    if field_type in {"float", "int"}:
        try:
            value = _number_from_text(text)
        except Exception:
            return None
        return int(value) if field_type == "int" else float(value)
    return text


def _help_field_from_line(line, next_line=""):
    match = _HELP_OPTION_RE.match(line)
    if not match:
        return None
    raw_names = [name.strip() for name in match.group("names").split(",")]
    long_flags = [name for name in raw_names if name.startswith("--") and name not in _HELP_SKIP_FLAGS]
    positive_flags = [name for name in long_flags if not name.startswith("--no-")]
    if not positive_flags:
        return None
    flag = positive_flags[-1]
    false_flag = next((name for name in long_flags if name.startswith("--no-")), "")
    field_id = _field_id_from_flag(flag)
    meta = str(match.group("meta") or "")
    meta_lower = meta.lower()
    field = {
        "id": field_id,
        "name": field_id,
        "label": _label_from_field_id(field_id),
        "flag": flag,
    }
    if false_flag:
        field["false_flag"] = false_flag
    if "float" in meta_lower:
        field["type"] = "float"
    elif "int" in meta_lower:
        field["type"] = "int"
    elif "text" in meta_lower or "string" in meta_lower:
        field["type"] = "choice" if "{" in meta and "}" in meta else "string"
    else:
        field["type"] = "bool"

    if field["type"] == "choice":
        option_match = re.search(r"\{([^}]+)\}", meta)
        if option_match:
            field["options"] = [
                [value.strip(), value.strip()] for value in option_match.group(1).split(",") if value.strip()
            ]
    range_match = re.search(r"\[\s*([-+]?[0-9]*\.?[0-9]+)\s*,\s*([-+]?[0-9]*\.?[0-9]+)\s*\]", meta)
    if range_match:
        field["min"] = _number_from_text(range_match.group(1))
        field["max"] = _number_from_text(range_match.group(2))
    elif field["type"] == "int" and "nonnegative" in meta_lower:
        field["min"] = 0
    default = _help_default(meta, field["type"])
    if default is not None:
        field["default"] = default
    if next_line and next_line.startswith(" ") and not _HELP_OPTION_RE.match(next_line):
        field["tooltip"] = next_line.strip()
    return field


def _load_product_schema_from_help(executable, product):
    lines = _run_cli([executable, product], timeout_seconds=_SCHEMA_TIMEOUT_SECONDS)
    fields = []
    for index, line in enumerate(lines):
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        field = _help_field_from_line(line, next_line)
        if field:
            fields.append(field)
    if not fields:
        raise RcAstroError("RC-Astro CLI help did not expose parseable product parameters.")
    return {
        "schema_version": 3,
        "product": product,
        "schema_source": "help",
        "parameters": fields,
    }


def _schema_field_id(field):
    field_id = _safe_field_id(field.get("id", field.get("name")))
    if field_id:
        return field_id
    return _field_id_from_flag(str(field.get("flag", "") or ""))


def _section_id_from_group(label):
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", str(label).strip().lower()).strip("_")
    return f"section_{suffix or 'parameters'}"


def _schema_group_lookup(schema):
    lookup = {}
    groups = schema.get("groups")
    if not isinstance(groups, list):
        return lookup
    for group in groups:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label", group.get("name", "")) or "").strip()
        params = group.get("params", group.get("parameters", group.get("fields")))
        if not label or not isinstance(params, list):
            continue
        for raw_param in params:
            field_id = _safe_field_id(raw_param)
            if field_id and field_id not in lookup:
                lookup[field_id] = label
    return lookup


def _identity_token(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _schema_field_matches_tokens(field, tokens):
    values = [
        _schema_field_id(field),
        field.get("id"),
        field.get("name"),
        field.get("label"),
        field.get("flag"),
    ]
    return any(_identity_token(value) in tokens for value in values)


def _sxt_generate_stars_field_id(schema):
    for field in _schema_fields(schema):
        if _schema_field_matches_tokens(field, _SXT_GENERATE_STARS_TOKENS):
            return _schema_field_id(field)
    return ""


def _sxt_generate_stars_enabled(schema, params):
    field_id = _sxt_generate_stars_field_id(schema)
    if not field_id:
        return True
    if field_id in params:
        return bool(params.get(field_id))
    for key, value in params.items():
        if _identity_token(key) in _SXT_GENERATE_STARS_TOKENS:
            return bool(value)
    for field in _schema_fields(schema):
        if _schema_field_id(field) == field_id:
            return bool(field.get("default", False))
    return False


def _apply_product_schema_overrides(schema, product):
    schema_groups = _schema_group_lookup(schema)
    schema_major = _schema_version_major(schema)
    schema_field_ids = {_schema_field_id(field) for field in _schema_fields(schema)}
    schema_has_device = "device" in schema_field_ids
    sxt_generate_stars_field_id = _sxt_generate_stars_field_id(schema) if product == "sxt" else ""
    for field in _ordered_schema_fields(schema):
        field_id = _schema_field_id(field)
        if not field_id:
            continue
        if schema_major >= 4 and field_id == "engine":
            if schema_has_device:
                field["hidden"] = True
                continue
            field["id"] = "device"
            field["name"] = "device"
            field["flag"] = "--device"
            field["label"] = "Acceleration Device"
            field_id = "device"
        if field_id in _TECHNICAL_OUTPUT_FIELDS or field_id in _MODEL_SELECTOR_FIELDS:
            field["hidden"] = True
            continue
        if "group" not in field and field_id in schema_groups:
            field["group"] = schema_groups[field_id]
        if field_id == "device":
            field["group"] = {
                "bxt": _BXT_FIELD_GROUPS,
                "nxt": _NXT_FIELD_GROUPS,
                "sxt": _SXT_FIELD_GROUPS,
            }.get(product, {}).get(field_id, "Engine")
            field["label"] = "Acceleration Device"
            field["flag"] = "--device"
            field.setdefault("default", "default")
            if _normalized_field_type(field) == "choice" and not _options_for_field(field):
                field["options"] = [["Default device", "default"]]
        if product == "bxt":
            group = _BXT_FIELD_GROUPS.get(field_id)
            if group:
                field["group"] = group
            if field_id in _BXT_FIELD_DEFAULTS:
                field["default"] = _BXT_FIELD_DEFAULTS[field_id]
            if field_id in _BXT_CORRECT_ONLY_DISABLED_FIELD_IDS:
                enabled_when = _BXT_NONSTELLAR_RADIUS_ENABLED_WHEN.get(field_id)
                if enabled_when:
                    field["enabled_when"] = enabled_when
                    field.setdefault("disabledValue", 0.0)
                else:
                    field["disabledIf"] = {"field": "correct_only", "op": "==", "value": True}
        if product == "nxt" and "group" not in field:
            group = _NXT_FIELD_GROUPS.get(field_id)
            if group:
                field["group"] = group
        if product == "nxt" and field_id in _NXT_FIELD_DEFAULTS:
            field["default"] = _NXT_FIELD_DEFAULTS[field_id]
        if product == "sxt" and "group" not in field:
            group = _SXT_FIELD_GROUPS.get(field_id)
            if group:
                field["group"] = group
        if product == "sxt" and _schema_field_matches_tokens(field, _SXT_GENERATE_STARS_TOKENS):
            field["group"] = "Options"
        if product == "sxt" and _schema_field_matches_tokens(field, _SXT_UNSCREEN_STARS_TOKENS):
            field["group"] = "Options"
            if sxt_generate_stars_field_id:
                field["enabled_when"] = f"{sxt_generate_stars_field_id} == true"
    return schema


def _fast_product_schema(product, device_options=None):
    """Local first-paint schema used by native process windows before CLI probing."""
    device_field = dict(_COMMON_DEVICE_FIELD)
    device_field["options"] = _normalised_device_options(device_options)
    if product == "bxt":
        schema = {
            "schema_version": 4,
            "product": "bxt",
            "schema_source": "fast_ui",
            "mlVersion": 4,
            "parameters": [
                {
                    "id": "sharpen_stars",
                    "type": "float",
                    "label": "Sharpen Stars",
                    "flag": "--sharpen-stars",
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                },
                {
                    "id": "adjust_star_halos",
                    "type": "float",
                    "label": "Adjust Star Halos",
                    "flag": "--adjust-star-halos",
                    "default": 0.0,
                    "min": -1.0,
                    "max": 1.0,
                    "step": 0.01,
                },
                {
                    "id": "auto_nonstellar_radius",
                    "type": "bool",
                    "label": "Auto Nonstellar Radius",
                    "flag": "--auto-nonstellar-radius",
                    "false_flag": "--no-auto-nonstellar-radius",
                    "default": True,
                },
                {
                    "id": "nonstellar_radius",
                    "type": "float",
                    "label": "Nonstellar Radius",
                    "flag": "--nonstellar-radius",
                    "default": 0.0,
                    "min": 0.0,
                    "max": 8.0,
                    "step": 0.1,
                },
                {
                    "id": "sharpen_nonstellar",
                    "type": "float",
                    "label": "Sharpen Nonstellar",
                    "flag": "--sharpen-nonstellar",
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                },
                {
                    "id": "correct_only",
                    "type": "bool",
                    "label": "Correct Only",
                    "flag": "--correct-only",
                    "default": False,
                },
                device_field,
                {
                    "id": "overlap",
                    "type": "float",
                    "label": "Tile Overlap",
                    "flag": "--overlap",
                    "default": 0.2,
                    "min": 0.0,
                    "max": 0.5,
                    "step": 0.01,
                },
            ],
        }
    elif product == "nxt":
        schema = {
            "schema_version": 4,
            "product": "nxt",
            "schema_source": "fast_ui",
            "mlVersion": 3,
            "modelVersions": [2, 3],
            "parameters": [
                {
                    "id": "dn",
                    "type": "float",
                    "label": "Denoise",
                    "flag": "--dn",
                    "default": 0.9,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.01,
                },
                device_field,
                {
                    "id": "overlap",
                    "type": "float",
                    "label": "Tile Overlap",
                    "flag": "--overlap",
                    "default": 0.2,
                    "min": 0.0,
                    "max": 0.5,
                    "step": 0.01,
                },
            ],
        }
    elif product == "sxt":
        schema = {
            "schema_version": 4,
            "product": "sxt",
            "schema_source": "fast_ui",
            "mlVersion": 3,
            "parameters": [
                {
                    "id": "stars",
                    "type": "bool",
                    "label": "Generate Stars Image",
                    "flag": "--stars",
                    "default": False,
                },
                {
                    "id": "unscreen",
                    "type": "bool",
                    "label": "Unscreen Stars",
                    "flag": "--unscreen",
                    "default": False,
                },
                device_field,
                {
                    "id": "overlap",
                    "type": "float",
                    "label": "Tile Overlap",
                    "flag": "--overlap",
                    "default": 0.2,
                    "min": 0.0,
                    "max": 0.5,
                    "step": 0.01,
                },
            ],
        }
    else:
        raise RcAstroError(f"Unsupported RC-Astro product: {product}")
    return _apply_product_schema_overrides(schema, product)


def _dedupe_paths(paths):
    seen = set()
    result = []
    for path in paths:
        text = str(path or "").strip()
        if not text:
            continue
        key = os.path.normcase(os.path.abspath(os.path.expanduser(text)))
        if key in seen:
            continue
        seen.add(key)
        result.append(pathlib.Path(text).expanduser())
    return result


def _candidate_executable_names():
    names = []
    seen = set()
    for base_name in _CLI_EXECUTABLE_BASENAMES:
        candidates = [base_name]
        suffix = pathlib.PureWindowsPath(base_name).suffix.lower()
        if os.name == "nt" and suffix not in {".exe", ".cmd", ".bat"}:
            candidates.extend([f"{base_name}.exe", f"{base_name}.cmd", f"{base_name}.bat"])
        for candidate in candidates:
            key = candidate.lower() if os.name == "nt" else candidate
            if key not in seen:
                seen.add(key)
                names.append(candidate)
    return names


def _is_runnable_file(path):
    if not path.is_file():
        return False
    if os.name == "nt":
        return True
    return os.access(path, os.X_OK)


def _case_insensitive_file(directory, file_name):
    direct = directory / file_name
    if _is_runnable_file(direct):
        return direct
    if "/" in file_name or "\\" in file_name:
        return None
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.name.lower() == file_name.lower() and _is_runnable_file(entry):
            return entry
    return None


def _find_cli_in_directory(directory):
    root = pathlib.Path(directory).expanduser()
    if root.is_file() and _is_runnable_file(root):
        if root.name.lower() in {name.lower() for name in _candidate_executable_names()}:
            return root.resolve()
        return None
    if not root.is_dir():
        return None
    for subdirectory in _CLI_SEARCH_SUBDIRECTORIES:
        search_dir = root / subdirectory if subdirectory else root
        if not search_dir.is_dir():
            continue
        for file_name in _candidate_executable_names():
            executable = _case_insensitive_file(search_dir, file_name)
            if executable:
                if os.name != "nt":
                    executable.chmod(executable.stat().st_mode | 0o111)
                return executable.resolve()
    return None


def _default_cli_directories():
    platform_key = "windows" if os.name == "nt" else "linux"
    configured = _tool_configuration().get("platform_candidate_directories", {}).get(platform_key, [])
    directories = list(configured)
    if os.name == "nt":
        for env_name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(env_name)
            if not base:
                continue
            for folder_name in ("RC-Astro", "RC Astro"):
                root = pathlib.Path(base) / folder_name
                directories.extend([root, root / "CLI", root / "bin"])
    return _dedupe_paths(directories)


def _path_cli_directories():
    return _dedupe_paths(os.environ.get("PATH", "").split(os.pathsep))


def _resolve_cli_for_settings_action(snapshot):
    try:
        executable = _resolved_cli_from_mapping(snapshot)
    except Exception as host_error:
        host_diagnostic = str(host_error)
    else:
        resolved_snapshot = dict(snapshot)
        resolved_snapshot.setdefault(
            "configured_folder", str(snapshot.get("configured_folder", "") or executable.parent)
        )
        resolved_snapshot.setdefault(_CLI_SETTING_KEY, str(snapshot.get(_CLI_SETTING_KEY, "") or executable))
        resolved_snapshot.setdefault("resolution_source", "host")
        resolved_snapshot.setdefault("resolved_cli_version", _cli_version(executable))
        resolved_snapshot.setdefault("resolver_diagnostic", "RC-Astro CLI is configured and ready to use.")
        resolved_snapshot[_RESOLVED_CLI_KEY] = str(executable)
        return executable, resolved_snapshot

    configured_dirs = _dedupe_paths(
        [
            snapshot.get(_CLI_SETTING_KEY, ""),
            snapshot.get(_LEGACY_CLI_SETTING_KEY, ""),
            snapshot.get("configured_folder", ""),
        ]
    )
    search_roots = [("settings", path) for path in configured_dirs]
    search_roots.extend(("candidate_directory", path) for path in _default_cli_directories())
    search_roots.extend(("path", path) for path in _path_cli_directories())

    for source, root in search_roots:
        executable = _find_cli_in_directory(root)
        if not executable:
            continue
        version = _cli_version(executable)
        root_path = pathlib.Path(root).expanduser()
        configured_folder = root_path.parent if root_path.is_file() else root_path
        resolved_snapshot = dict(snapshot)
        resolved_snapshot[_RESOLVED_CLI_KEY] = str(executable)
        resolved_snapshot[_CLI_SETTING_KEY] = str(executable)
        resolved_snapshot["configured_folder"] = str(configured_folder)
        resolved_snapshot["resolution_source"] = source
        resolved_snapshot["resolved_cli_version"] = version or "Unknown"
        resolved_snapshot["resolver_diagnostic"] = "RC-Astro CLI is configured and ready to use."
        return executable, resolved_snapshot

    message = (
        "Could not find a supported RC-Astro CLI executable in the selected executable or folder, "
        "default installation folders, or PATH."
    )
    if host_diagnostic:
        message = f"{message} Host resolver said: {host_diagnostic}"
    raise RcAstroError(message)


def _tool_configuration():
    return {
        "settings_key": _CLI_SETTING_KEY,
        "label": "RC-Astro CLI",
        "button_label": "Configure",
        "dialog_title": "Select RC-Astro CLI Executable",
        "not_configured_text": "RC-Astro CLI is not configured.",
        "configured_text": "RC-Astro CLI is configured and ready to use.",
        "invalid_text": (
            "Selected file is not a supported RC-Astro CLI executable (%1). "
            "Choose the rc-astro executable, or use Detect Installation."
        ),
        "show_configured_banner": False,
        "primary_executable": _CLI_NAME,
        "primary_executable_candidates": _candidate_executable_names(),
        "candidate_subdirectories": [item for item in _CLI_SEARCH_SUBDIRECTORIES if item],
        "append_platform_executable_suffix": True,
        "require_executable": True,
        "version_arguments": ["--json"],
        "version_pattern": r'(?:\bVersion\s+|"cliVersion"\s*:\s*")([^"\r\n]+)',
        "platform_candidate_directories": {
            "windows": [
                r"C:\Program Files\RC-Astro\CLI",
                r"C:\Program Files\RC-Astro",
                r"C:\Program Files\RC Astro\CLI",
                r"C:\Program Files\RC Astro",
            ],
            "linux": [
                "/opt/rc-astro/bin",
                "/opt/rc-astro",
                "/usr/local/bin",
                "/usr/bin",
                str(pathlib.Path.home() / ".local" / "bin"),
            ],
        },
        "download_page_url": "https://www.rc-astro.com/resources/",
        "install_instructions": (
            "Install the RC-Astro command-line tools separately, then select the rc-astro "
            "executable or click Detect Installation. This package does not redistribute "
            "RC-Astro binaries, models, icons, licenses, or activation material."
        ),
    }


def _tool_record_updates(snapshot, executable):
    configured_folder = str(snapshot.get("configured_folder", "") or pathlib.Path(executable).parent).strip()
    source = str(snapshot.get("resolution_source", "") or "").strip()
    version = str(snapshot.get("resolved_cli_version", "") or "").strip() or _cli_version(executable)
    diagnostic = str(snapshot.get("resolver_diagnostic", "") or "").strip()
    if not diagnostic:
        diagnostic = "RC-Astro CLI is configured and ready to use."
    return {
        "resolver_diagnostic": diagnostic,
        _CLI_SETTING_KEY: str(executable),
        "resolved_cli_executable": str(executable),
        "resolved_cli_version": version or "Unknown",
        "resolution_source": source or "settings",
        "configured_folder": configured_folder,
    }


def _activation_status(executable, product):
    try:
        lines = _run_cli([executable, product, "--license"], timeout_seconds=_ACTION_TIMEOUT_SECONDS)
    except Exception:
        return "Activation status was not reported by this RC-Astro CLI."
    for line in lines:
        event = _json_event(line)
        if event:
            for key in ("activated", "licensed", "license_valid", "is_activated"):
                if key in event:
                    return "Activated" if bool(event[key]) else "Not activated"
            status = str(event.get("activation_status", event.get("license_status", "")) or "").strip()
            if status:
                return status
        text = str(line).strip()
        if not text:
            continue
        lowered = text.lower()
        if "not activated" in lowered or "not licensed" in lowered:
            return "Not activated"
        if "activated" in lowered or "licensed" in lowered or "valid" in lowered:
            return "Activated"
    return "Activation status was not reported by this RC-Astro CLI."


def _activation_settings_options():
    return [[info["name"], product] for product, info in _PRODUCTS.items()]


def _selected_activation_product(snapshot, fallback="bxt"):
    product = str(snapshot.get(_ACTIVATION_PRODUCT_PARAM_ID, "") or "").strip().lower()
    if product in _PRODUCTS:
        return product
    fallback = str(fallback or "").strip().lower()
    return fallback if fallback in _PRODUCTS else "bxt"


def _activation_status_updates(executable, selected_product="bxt"):
    updates = {}
    for product in _PRODUCTS:
        updates[_ACTIVATION_STATUS_PARAM_IDS[product]] = _activation_status(executable, product)
    selected_product = _selected_activation_product({_ACTIVATION_PRODUCT_PARAM_ID: selected_product})
    updates["activation_status"] = updates[_ACTIVATION_STATUS_PARAM_IDS[selected_product]]
    return updates


def _activation_unavailable_updates(message):
    text = str(message or "").strip() or "RC-Astro CLI is not configured."
    updates = {param_id: text for param_id in _ACTIVATION_STATUS_PARAM_IDS.values()}
    updates["activation_status"] = text
    updates["resolver_diagnostic"] = text
    return updates


def _activation_state_from_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return None
    inactive_markers = (
        "not activated",
        "not licensed",
        "unactivated",
        "unlicensed",
        "license required",
        "no license",
        "invalid",
        "expired",
    )
    if any(marker in text for marker in inactive_markers):
        return False
    active_markers = ("activated", "licensed", "permanently licensed", "trial", "valid")
    if any(marker in text for marker in active_markers):
        return True
    return None


def _activation_state_from_mapping(value):
    if not isinstance(value, dict):
        return None
    for key in ("activated", "licensed", "license_valid", "is_activated", "valid"):
        if key in value:
            return bool(value[key])
    for key in ("activation_status", "license_status", "status", "state"):
        state = _activation_state_from_text(value.get(key))
        if state is not None:
            return state
    for key in ("license", "activation"):
        state = _activation_state_from_mapping(value.get(key))
        if state is not None:
            return state
    return None


def _activation_state_from_schema(schema):
    return _activation_state_from_mapping(schema)


def _activation_state_for_product(executable, product, schema=None):
    if schema is not None:
        state = _activation_state_from_schema(schema)
        if state is not None:
            return state, "product schema"
    status = _activation_status(executable, product)
    return _activation_state_from_text(status), status


def _activation_required_message(product, status=""):
    message = (
        f"{_PRODUCTS[product]['name']} is not activated in the RC-Astro CLI. "
        "Open the RC-Astro XTerminators settings, activate this product, then refresh status."
    )
    status = str(status or "").strip()
    if status and status != "Not activated":
        message = f"{message} Reported status: {status}."
    return message


def _activation_validation_diagnostic(product, status=""):
    return {
        "ok": False,
        "severity": "error",
        "message": _activation_required_message(product, status),
    }


def _require_activated_product(executable, product, schema=None):
    state, status = _activation_state_for_product(executable, product, schema)
    if state is False:
        raise RcAstroError(_activation_required_message(product, status))


def _version_tuple(value):
    match = re.search(r"\b([0-9]+(?:\.[0-9]+){1,3})\b", str(value or ""))
    if not match:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def _update_info_from_lines(lines, current_version=""):
    text = "\n".join(str(line) for line in lines if str(line).strip()).strip()
    status = text or "Update check completed."
    available = None
    latest_version = ""

    for line in lines:
        event = _json_event(line)
        if not event:
            continue
        for key in ("latest_version", "latestVersion", "available_version", "availableVersion", "new_version"):
            if event.get(key):
                latest_version = str(event[key]).strip()
                break
        for key in ("update_available", "updateAvailable", "available", "has_update", "newer_available"):
            if key in event:
                available = bool(event[key])
                break

    lowered = status.lower()
    if available is None:
        if any(marker in lowered for marker in ("up to date", "up-to-date", "latest version", "no update")):
            available = False
        elif any(marker in lowered for marker in ("newer version", "new version", "update available", "available")):
            available = True

    if not latest_version:
        versions = re.findall(r"\b[0-9]+(?:\.[0-9]+){1,3}\b", status)
        current_tuple = _version_tuple(current_version)
        if versions:
            newer_versions = [version for version in versions if _version_tuple(version) > current_tuple]
            if newer_versions:
                latest_version = newer_versions[-1]
                available = True

    if available is None:
        available = False
    return {
        "available": bool(available),
        "latest_version": latest_version,
        "status": status,
    }


def _load_product_schema(executable, product):
    version = _cli_version(executable)
    key = (str(executable.resolve()), version, product)
    if key in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[key]

    failures = []
    last_error = None
    for command in _schema_inspection_commands(executable, product):
        display_command = " ".join(str(part) for part in command[1:])
        try:
            lines = _run_cli(command, timeout_seconds=_SCHEMA_TIMEOUT_SECONDS)
            schema = _schema_from_json_payload(_json_payload_from_lines(lines), product)
            _validate_product_schema(schema, product)
        except json.JSONDecodeError as exc:
            failures.append(f"{display_command}: invalid JSON")
            last_error = exc
        except RcAstroError as exc:
            failures.append(f"{display_command}: {exc}")
            last_error = exc
        else:
            schema = _apply_product_schema_overrides(schema, product)
            schema = _apply_runtime_device_options(schema, executable, version)
            _SCHEMA_CACHE[key] = schema
            return schema

    try:
        schema = _load_product_schema_from_help(executable, product)
        _validate_product_schema(schema, product)
    except RcAstroError as exc:
        failures.append(f"{product}: {exc}")
        last_error = exc
    else:
        schema = _apply_product_schema_overrides(schema, product)
        schema = _apply_runtime_device_options(schema, executable, version)
        _SCHEMA_CACHE[key] = schema
        return schema

    detail = "; ".join(failures[-3:]) if failures else "No schema command was attempted."
    raise RcAstroError(f"RC-Astro {product.upper()} schema inspection failed. Tried: {detail}") from last_error


def _schema_fields(schema):
    for key in ("parameters", "params", "controls", "fields"):
        value = schema.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _schema_product(schema):
    return str(schema.get("product", schema.get("key", "")) or "").strip().lower()


def _schema_modes(schema):
    value = schema.get("modes")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _mode_field_id(mode):
    field_id = _safe_field_id(mode.get("id", mode.get("name")))
    if not field_id:
        field_id = _field_id_from_flag(str(mode.get("flag", "") or ""))
    return _BXT_MODE_FIELD_ALIASES.get(field_id, field_id)


def _field_from_schema_mode(mode, product):
    field_id = _mode_field_id(mode)
    if not field_id:
        return None
    field = {
        "id": field_id,
        "type": "bool",
        "label": str(mode.get("label", field_id.replace("_", " ").title())),
        "default": mode.get("default", False),
        "flag": str(mode.get("flag", "") or "").strip() or _flag_name(field_id),
    }
    if mode.get("description") or mode.get("tooltip"):
        field["description"] = str(mode.get("description", mode.get("tooltip")))
    if product == "bxt":
        group = _BXT_FIELD_GROUPS.get(field_id)
        if group:
            field["group"] = group
        if field_id in _BXT_FIELD_DEFAULTS:
            field["default"] = _BXT_FIELD_DEFAULTS[field_id]
        if field_id == "device":
            field.setdefault("label", "Acceleration Device")
            field.setdefault("flag", "--device")
    if product == "nxt" and "group" not in field:
        group = _NXT_FIELD_GROUPS.get(field_id)
        if group:
            field["group"] = group
    if product == "nxt" and field_id in _NXT_FIELD_DEFAULTS:
        field["default"] = _NXT_FIELD_DEFAULTS[field_id]
    if product == "nxt" and field_id == "device":
        field.setdefault("label", "Acceleration Device")
        field.setdefault("flag", "--device")
    if product == "sxt" and "group" not in field:
        group = _SXT_FIELD_GROUPS.get(field_id)
        if group:
            field["group"] = group
    if product == "sxt" and field_id == "device":
        field.setdefault("label", "Acceleration Device")
        field.setdefault("flag", "--device")
    return field


def _schema_mode_fields(schema):
    product = _schema_product(schema)
    existing_ids = {_schema_field_id(field) for field in _schema_fields(schema)}
    fields = []
    for mode in _schema_modes(schema):
        field = _field_from_schema_mode(mode, product)
        if not field:
            continue
        field_id = _schema_field_id(field)
        if field_id and field_id not in existing_ids:
            fields.append(field)
            existing_ids.add(field_id)
    return fields


def _synthetic_schema_fields(schema):
    product = _schema_product(schema)
    if product not in _PRODUCTS:
        return []
    existing_ids = {_schema_field_id(field) for field in [*_schema_fields(schema), *_schema_mode_fields(schema)]}
    if {"device", "engine"} & existing_ids:
        return []
    schema_major = _schema_version_major(schema)
    if schema_major < 4 and product != "bxt":
        return []
    field = dict(_COMMON_DEVICE_FIELD if schema_major >= 4 else _COMMON_ENGINE_FIELD)
    if field["id"] == "device":
        device_options = _schema_runtime_device_options(schema)
        if device_options:
            field["options"] = device_options
    field_groups = {
        "bxt": _BXT_FIELD_GROUPS,
        "nxt": _NXT_FIELD_GROUPS,
        "sxt": _SXT_FIELD_GROUPS,
    }[product]
    field["group"] = field_groups[field["id"]]
    if product == "bxt":
        field["default"] = _BXT_FIELD_DEFAULTS[field["id"]]
    return [field]


def _schema_ui_fields(schema, include_model_version=False):
    fields = [*_schema_fields(schema), *_schema_mode_fields(schema), *_synthetic_schema_fields(schema)]
    if include_model_version:
        product = _schema_product(schema)
        if product in _PRODUCTS:
            fields.append(_model_version_field(schema, product))
    return fields


def _ordered_schema_fields(schema, include_model_version=False):
    fields = _schema_ui_fields(schema, include_model_version=include_model_version)
    product = _schema_product(schema)
    if product not in {"bxt", "nxt", "sxt"}:
        return fields

    if product == "bxt":
        group_order = _BXT_GROUP_ORDER
        field_order = _BXT_FIELD_ORDER
        field_groups = _BXT_FIELD_GROUPS
    elif product == "nxt":
        group_order = _NXT_GROUP_ORDER
        field_order = _NXT_FIELD_ORDER
        field_groups = _NXT_FIELD_GROUPS
    else:
        group_order = _SXT_GROUP_ORDER
        field_order = _SXT_FIELD_ORDER
        field_groups = _SXT_FIELD_GROUPS

    def sort_key(index_and_field):
        index, field = index_and_field
        field_id = _schema_field_id(field)
        group = str(field.get("group", "") or field_groups.get(field_id, "")).strip()
        order = field_order.get(field_id, 1000 + index)
        return (group_order.get(group, 99), order, index)

    return [field for _index, field in sorted(enumerate(fields), key=sort_key)]


def _as_positive_int(value):
    try:
        number = int(value)
    except TypeError, ValueError:
        return 0
    return number if number > 0 else 0


def _model_version_number(value):
    number = _as_positive_int(value)
    if number > 0:
        return number
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.search(r"(?:\bAI|\bv)?\s*([1-9][0-9]*)\b", text, flags=re.IGNORECASE)
    if not match:
        return 0
    return _as_positive_int(match.group(1))


def _schema_latest_model_version(schema):
    for key in ("mlVersion", "ml_version", "modelVersion", "model_version", "latestModelVersion"):
        version = _model_version_number(schema.get(key))
        if version > 0:
            return version
    for field in _ordered_schema_fields(schema):
        if _schema_field_id(field) not in _MODEL_SELECTOR_FIELDS:
            continue
        for key in ("latest", "max", "default"):
            version = _model_version_number(field.get(key))
            if version > 0:
                return version
    return 0


def _add_model_version_value(versions, value):
    if isinstance(value, dict):
        for key in ("version", "value", "id", "name", "label", "mlVersion", "modelVersion"):
            version = _model_version_number(value.get(key))
            if version > 0:
                versions.add(version)
        return
    version = _model_version_number(value)
    if version > 0:
        versions.add(version)


def _schema_model_versions(schema, product=None):
    versions = set()
    for key in (
        "modelVersions",
        "model_versions",
        "mlVersions",
        "ml_versions",
        "availableModelVersions",
        "available_model_versions",
        "models",
        "model_catalog",
    ):
        raw_versions = schema.get(key)
        if isinstance(raw_versions, list):
            for item in raw_versions:
                _add_model_version_value(versions, item)
    for field in _ordered_schema_fields(schema):
        if _schema_field_id(field) not in _MODEL_SELECTOR_FIELDS:
            continue
        for _label, value in _options_for_field(field):
            _add_model_version_value(versions, value)
    if versions:
        return sorted(versions)
    latest = _schema_latest_model_version(schema)
    first_version = _MODEL_VERSION_FALLBACK_MINIMUMS.get(product)
    if latest > 0 and first_version is not None:
        versions.update(range(first_version, latest + 1))
    return sorted(versions)


def _model_version_options(schema):
    latest = _schema_latest_model_version(schema)
    latest_label = "Latest" if latest <= 0 else f"Latest (v{latest})"
    options = [[latest_label, "latest"]]
    options.extend(
        [f"Version {version}", str(version)] for version in _schema_model_versions(schema, _schema_product(schema))
    )
    return options


def _model_status_text(schema, product):
    product_name = _PRODUCTS[product]["name"]
    latest = _schema_latest_model_version(schema)
    versions = _schema_model_versions(schema, product)
    if latest > 0 and versions:
        return (
            f"{product_name}: latest schema model version is v{latest}. "
            f"Selectable fixed versions: {', '.join('v' + str(version) for version in versions)}."
        )
    if latest > 0:
        return (
            f"{product_name}: latest schema model version is v{latest}. "
            "The CLI did not report a selectable fixed model version catalog for this product."
        )
    return f"{product_name}: the CLI did not report a model version catalog for this product."


def _model_version_field(schema, product):
    field = {
        "id": _MODEL_VERSION_PARAM_ID,
        "type": "choice",
        "label": "Model Version",
        "default": "latest",
        "tooltip": (
            f"{_model_status_text(schema, product)} "
            "Use the latest RC-Astro model by default, or pin one of the model versions "
            "reported by this product schema for this run."
        ),
        "options": _model_version_options(schema),
    }
    if product == "bxt":
        field["group"] = _BXT_FIELD_GROUPS[_MODEL_VERSION_PARAM_ID]
    if product == "nxt":
        field["group"] = _NXT_FIELD_GROUPS[_MODEL_VERSION_PARAM_ID]
    if product == "sxt":
        field["group"] = _SXT_FIELD_GROUPS[_MODEL_VERSION_PARAM_ID]
    return field


def _safe_field_id(value):
    text = str(value or "").strip()
    return text if _FIELD_ID_RE.match(text) else ""


def _normalized_field_type(field):
    raw_type = str(field.get("type", field.get("kind", "string"))).strip().lower()
    if raw_type in {"boolean", "bool", "checkbox"}:
        return "bool"
    if raw_type in {"integer", "int"}:
        return "int"
    if raw_type in {"float", "double", "number"}:
        return "float"
    if raw_type in {"enum", "select", "choice"}:
        return "choice"
    if raw_type in {"slider", "range"}:
        return "slider"
    return "string"


def _options_for_field(field):
    raw_options = field.get("options", field.get("choices", []))
    options = []
    if isinstance(raw_options, dict):
        raw_options = raw_options.items()
    for item in raw_options or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            label, value = item[0], item[1]
        elif isinstance(item, dict):
            label = item.get("label", item.get("name", item.get("value")))
            value = item.get("value", label)
        else:
            label = value = item
        options.append([str(label), value])
    return options


def _invert_condition(expression):
    if not isinstance(expression, str):
        return ""
    replacements = [
        ("==", "!="),
        ("!=", "=="),
        (">=", "<"),
        ("<=", ">"),
        (">", "<="),
        ("<", ">="),
    ]
    for operator, inverse in replacements:
        if operator in expression:
            left, right = expression.split(operator, 1)
            return f"{left.strip()} {inverse} {right.strip()}"
    return ""


def _normalise_boolean_condition_text(expression):
    text = str(expression or "").strip()
    if not text:
        return ""
    if any(operator in text for operator in ("==", "!=", ">=", "<=", ">", "<")):
        return text
    if "||" in text or "(" in text or ")" in text:
        return text

    terms = []
    for raw_term in text.split("&&"):
        term = raw_term.strip()
        if not term:
            return text
        negate = term.startswith("!")
        if negate:
            term = term[1:].strip()
        field = _safe_field_id(term)
        if not field:
            return text
        terms.append(f"{field} {'!=' if negate else '=='} true")
    return " && ".join(terms)


def _condition_text(value):
    if isinstance(value, str):
        return _normalise_boolean_condition_text(value)
    if isinstance(value, dict):
        field = _safe_field_id(value.get("field", value.get("param", value.get("id"))))
        op = str(value.get("op", value.get("operator", "=="))).strip()
        rhs = value.get("value")
        if not field or op not in {"==", "!=", ">=", "<=", ">", "<"}:
            return ""
        if isinstance(rhs, str):
            rhs_text = json.dumps(rhs)
        elif isinstance(rhs, bool):
            rhs_text = "true" if rhs else "false"
        else:
            rhs_text = str(rhs)
        return f"{field} {op} {rhs_text}"
    return ""


def _condition_literal(value):
    text = str(value).strip()
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text[1:-1]
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _truthy_condition_value(value):
    if isinstance(value, bool):
        return value
    try:
        return float(value) != 0.0
    except TypeError, ValueError:
        return bool(value)


def _condition_matches(expression, state):
    text = _condition_text(expression)
    if not text:
        return True
    for raw_term in re.split(r"\s*(?:&&|\band\b)\s*", text):
        term = raw_term.strip()
        if not term:
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*(==|!=|>=|<=|>|<)\s*(.+?)$", term)
        if not match:
            return False
        field, op, raw_rhs = match.groups()
        left = state.get(field, False)
        right = _condition_literal(raw_rhs)
        if isinstance(right, bool):
            left = _truthy_condition_value(left)
        if op in {"<", "<=", ">", ">="}:
            try:
                left = float(left)
                right = float(right)
            except TypeError, ValueError:
                return False
        if op == "==" and left != right:
            return False
        if op == "!=" and left == right:
            return False
        if op == ">=" and left < right:
            return False
        if op == "<=" and left > right:
            return False
        if op == ">" and left <= right:
            return False
        if op == "<" and left >= right:
            return False
    return True


def _param_from_schema_field(field):
    field_id = _schema_field_id(field)
    if not field_id or field.get("hidden"):
        return None
    if field_id in {"input", "output", "input_path", "output_path", "stars_output"}:
        return None

    param = {
        "id": field_id,
        "type": _normalized_field_type(field),
        "label": str(field.get("label", field_id.replace("_", " ").title())),
        "default": field.get("default"),
    }
    group = str(field.get("group", "") or "").strip()
    if group:
        param["group"] = group
    if field.get("tooltip") or field.get("description"):
        param["tooltip"] = str(field.get("tooltip", field.get("description")))
    for source, target in (("min", "min"), ("max", "max"), ("step", "step")):
        if source in field:
            param[target] = field[source]
    if param["type"] == "choice":
        options = _options_for_field(field)
        if not options:
            return None
        param["options"] = options
    visible_when = _condition_text(field.get("visibleIf", field.get("visible_when")))
    if visible_when:
        param["visible_when"] = visible_when
    enabled_when = _condition_text(field.get("enabledIf", field.get("enabled_when")))
    if not enabled_when:
        disabled_when = _condition_text(field.get("disabledIf", field.get("disabled_when")))
        enabled_when = _invert_condition(disabled_when)
    if enabled_when:
        param["enabled_when"] = enabled_when
    return param


def _schema_params(schema):
    params = []
    current_group = ""
    section_counts = {}
    for field in _ordered_schema_fields(schema, include_model_version=True):
        param = _param_from_schema_field(field)
        if param:
            group = str(param.get("group", "") or "").strip()
            if group and group != current_group:
                section_base_id = _section_id_from_group(group)
                count = section_counts.get(section_base_id, 0)
                section_counts[section_base_id] = count + 1
                section_id = section_base_id if count == 0 else f"{section_base_id}_{count + 1}"
                params.append({"id": section_id, "type": "section", "label": group})
                current_group = group
            elif not group:
                current_group = ""
            params.append(param)
    return params


def _schema_flag_for_field(schema, field_id):
    for field in _schema_fields(schema):
        if _schema_field_id(field) == field_id:
            flag = str(field.get("flag", "") or "").strip()
            return flag or _flag_name(field_id)
    return ""


def _flag_name(field_id):
    return "--" + field_id.replace("_", "-")


def _param_value(params, field_id, default=None):
    if field_id in params:
        return params.get(field_id)
    for alias in _PARAM_VALUE_ALIASES.get(field_id, ()):
        if alias in params:
            return params.get(alias)
    return default


def _bool_param(params, field_ids):
    for field_id in field_ids:
        value = _param_value(params, field_id, _MISSING)
        if value is not _MISSING:
            return bool(value)
    return False


def _should_emit_field(product, field, field_id, params):
    if field.get("guiOnly"):
        return False
    visible_when = field.get("visibleIf", field.get("visible_when"))
    if visible_when and not _condition_matches(visible_when, params):
        return False
    if product == "bxt" and _bool_param(params, _BXT_CORRECT_ONLY_FIELD_IDS):
        return field_id in _BXT_CORRECT_ONLY_ALLOWED_FIELD_IDS
    if product == "bxt" and field_id in {"nsr", "nonstellar_radius"}:
        return not _bool_param(params, {"ansr", "auto_nonstellar_radius"})
    if product == "sxt" and _schema_field_matches_tokens(field, _SXT_UNSCREEN_STARS_TOKENS):
        return any(_identity_token(key) in _SXT_GENERATE_STARS_TOKENS and bool(value) for key, value in params.items())
    return True


def _should_omit_field_value(field_id, flag, value):
    if field_id == "device" or flag == "--device":
        return str(value or "").strip().lower() in {"", "default", "auto"}
    return False


def _command_for_schema(executable, product, schema, input_path, output_path, stars_path, params):
    params = params or {}
    command = [
        str(executable),
        product,
        str(input_path),
        "-o",
        str(output_path),
        "--overwrite",
    ]
    if product == "sxt":
        stars_flag = _schema_flag_for_field(schema, "stars_output")
        if stars_flag and _sxt_generate_stars_enabled(schema, params):
            command.extend([stars_flag, str(stars_path)])
    model_version = str((params or {}).get(_MODEL_VERSION_PARAM_ID, "") or "").strip().lower()
    if model_version and model_version not in {"latest", "0"}:
        command.extend(["--ml-version", model_version])
    fields = _ordered_schema_fields(schema)
    state = {}
    for field in fields:
        param = _param_from_schema_field(field)
        if param:
            state[param["id"]] = _param_value(params, param["id"], param.get("default"))
    for field in fields:
        param = _param_from_schema_field(field)
        if not param:
            continue
        field_id = param["id"]
        if not _should_emit_field(product, field, field_id, state):
            continue
        value = _param_value(params, field_id, param.get("default"))
        if value is None:
            continue
        flag = str(field.get("flag", "") or "").strip() or _flag_name(field_id)
        if _should_omit_field_value(field_id, flag, value):
            continue
        if param["type"] == "bool":
            if value:
                command.append(flag)
            elif field.get("false_flag"):
                command.append(str(field["false_flag"]))
            continue
        command.extend([flag, str(value)])
    return command


class _RcAstroBase(ui.ProcessWindow):
    product = ""
    component = "extension.rc_astro"

    def get_settings_params(self):
        return [
            {
                "id": "resolver_diagnostic",
                "type": "string",
                "label": "Status",
                "default": "Select the RC-Astro CLI executable or click Detect Installation.",
                "group": "CLI Connection",
                "group_style": "card",
                "persist": False,
                "enabled": False,
            },
            {
                "id": "resolved_cli_version",
                "type": "string",
                "label": "Version",
                "default": "Not detected",
                "group": "CLI Connection",
                "group_style": "card",
                "persist": False,
                "enabled": False,
            },
            {
                "id": _RESOLVED_CLI_KEY,
                "type": "string",
                "label": "Resolved Executable",
                "default": "Not detected",
                "group": "CLI Connection",
                "group_style": "card",
                "persist": False,
                "enabled": False,
                "visible": False,
            },
            {
                "id": _DEVICE_OPTIONS_SETTING_KEY,
                "type": "string",
                "label": "Detected Acceleration Devices",
                "default": "",
                "group": "CLI Connection",
                "group_style": "card",
                "persist": True,
                "enabled": False,
                "visible": False,
            },
            {
                "id": _CLI_SETTING_KEY,
                "type": "file_path",
                "label": "Executable",
                "default": "",
                "group": "CLI Connection",
                "group_style": "card",
                "placeholder": "Select rc-astro, rc-astro-cli, or RCAstroCLI",
                "button_label": "Browse...",
                "read_only": True,
                "tooltip": "User-installed RC-Astro CLI executable.",
                "tool_configuration": _tool_configuration(),
            },
            {
                "id": "resolution_source",
                "type": "string",
                "label": "Detected From",
                "default": "",
                "group": "CLI Connection",
                "group_style": "card",
                "persist": False,
                "enabled": False,
                "visible": False,
            },
            {
                "id": "detect_installation",
                "type": "action",
                "label": "Detect Installation",
                "title": "Find RC-Astro CLI",
                "group": "CLI Connection",
                "group_style": "card",
                "tooltip": "Search the saved executable, common installation folders, and PATH for rc-astro.",
                "timeout_ms": 10000,
            },
            {
                "id": "refresh_status",
                "type": "action",
                "label": "Refresh Status",
                "title": "Refresh RC-Astro Status",
                "group": "CLI Connection",
                "group_style": "card",
                "tooltip": "Query the detected RC-Astro CLI version and product activation statuses.",
                "timeout_ms": 30000,
            },
            {
                "id": "refresh_status_on_open",
                "type": "action",
                "label": "Refresh Status",
                "title": "Refresh RC-Astro Status",
                "group": "CLI Connection",
                "group_style": "card",
                "visible": False,
                "persist": False,
                "action_id": "refresh_status",
                "autorun": True,
                "show_status": False,
                "timeout_ms": 30000,
            },
            *[
                {
                    "id": _ACTIVATION_STATUS_PARAM_IDS[product],
                    "type": "status",
                    "label": info["name"],
                    "default": "Checking...",
                    "group": "Products",
                    "group_style": "card",
                    "persist": False,
                    "enabled": False,
                }
                for product, info in _PRODUCTS.items()
            ],
            {
                "id": "activation_status",
                "type": "string",
                "label": "Selected Product Status",
                "default": "Checking...",
                "group": "Products",
                "group_style": "card",
                "persist": False,
                "enabled": False,
                "visible": False,
            },
            {
                "id": _ACTIVATION_PRODUCT_PARAM_ID,
                "type": "choice",
                "label": "Product",
                "default": "bxt",
                "group": "Products",
                "group_style": "card",
                "options": _activation_settings_options(),
                "visible": False,
            },
            {
                "id": "activation_email",
                "type": "string",
                "label": "Email",
                "default": "",
                "group": "Products",
                "group_style": "card",
                "placeholder": "Activation email",
                "sensitive": True,
                "persist": False,
                "visible": False,
            },
            {
                "id": "activation_key",
                "type": "string",
                "label": "Activation Key",
                "default": "",
                "group": "Products",
                "group_style": "card",
                "placeholder": "Activation key",
                "secret": True,
                "sensitive": True,
                "persist": False,
                "visible": False,
            },
            {
                "id": _ACTIVATION_CONSOLE_PARAM_ID,
                "type": "console_output",
                "label": "Activation Output",
                "default": "",
                "placeholder": "Activation output will appear here.",
                "group": "Products",
                "group_style": "card",
                "persist": False,
                "visible": False,
                "min_lines": 10,
                "collapsed_when_empty": True,
            },
            {
                "id": "open_activation_dialog",
                "type": "action",
                "label": "Activation...",
                "title": "Product Activation",
                "group": "Products",
                "group_style": "card",
                "tooltip": "Open the RC-Astro product activation dialog.",
                "action_id": "activate_selected",
                "dialog": {
                    "title": "RC-Astro Product Activation",
                    "accept_label": "Activate Selected Product",
                    "keep_open_on_accept": True,
                    "minimum_width": 720,
                    "fields": [
                        _ACTIVATION_PRODUCT_PARAM_ID,
                        "activation_email",
                        "activation_key",
                        _ACTIVATION_CONSOLE_PARAM_ID,
                    ],
                },
                "timeout_ms": 30000,
            },
            {
                "id": "check_updates",
                "type": "action",
                "label": "Check Updates",
                "title": "Check for RC-Astro CLI Updates",
                "group": "Updates",
                "group_style": "card",
                "tooltip": "Ask the RC-Astro CLI whether a newer version is available.",
                "timeout_ms": 15000,
            },
            {
                "id": _UPDATE_AVAILABLE_PARAM_ID,
                "type": "bool",
                "label": "Update Available",
                "default": False,
                "group": "Updates",
                "group_style": "card",
                "persist": False,
                "enabled": False,
                "visible": False,
            },
            {
                "id": "download_update",
                "type": "action",
                "label": "Update",
                "title": "Update RC-Astro CLI",
                "group": "Updates",
                "group_style": "card",
                "tooltip": "Runs rc-astro update --install after Check Updates reports a newer CLI version.",
                "enabled_when": f"{_UPDATE_AVAILABLE_PARAM_ID} == true",
                "timeout_ms": 300000,
            },
            {
                "id": _SETTINGS_CONSOLE_PARAM_ID,
                "type": "console_output",
                "label": "Console Output",
                "default": "",
                "placeholder": "Check Updates and Update output will appear here.",
                "group": "Updates",
                "group_style": "card",
                "persist": False,
                "min_lines": 18,
                "collapsed_when_empty": True,
            },
        ]

    def handle_settings_action(self, action_id, settings_snapshot):
        snapshot = dict(settings_snapshot or {})
        try:
            executable, snapshot = _resolve_cli_for_settings_action(snapshot)
        except Exception as exc:
            result = {"ok": False, "message": str(exc), "tone": "warning"}
            if action_id in {"detect_installation", "refresh_status"}:
                result["transient_updates"] = _activation_unavailable_updates(str(exc))
            return result

        try:
            if action_id == "detect_installation":
                updates = _tool_record_updates(snapshot, executable)
                device_updates = _device_option_setting_updates(executable, updates.get("resolved_cli_version", ""))
                settings_updates = {_CLI_SETTING_KEY: str(executable), **device_updates}
                selected_product = _selected_activation_product(snapshot, self.product)
                updates.update(device_updates)
                updates.update(_activation_status_updates(executable, selected_product))
                return {
                    "ok": True,
                    "message": (f"Detected RC-Astro CLI at {executable}. Version: {updates['resolved_cli_version']}."),
                    "tone": "success",
                    "settings_updates": settings_updates,
                    "transient_updates": updates,
                }
            if action_id == "refresh_status":
                updates = _tool_record_updates(snapshot, executable)
                device_updates = _device_option_setting_updates(executable, updates.get("resolved_cli_version", ""))
                selected_product = _selected_activation_product(snapshot, self.product)
                updates.update(device_updates)
                updates.update(_activation_status_updates(executable, selected_product))
                result = {
                    "ok": True,
                    "message": (
                        f"RC-Astro CLI is available ({updates['resolved_cli_version']}). "
                        "Product activation statuses refreshed."
                    ),
                    "tone": "success",
                    "transient_updates": updates,
                }
                if device_updates:
                    result["settings_updates"] = device_updates
                return result
            if action_id == "activate_selected":
                return self._activate_product(
                    executable,
                    _selected_activation_product(snapshot, self.product),
                    snapshot,
                )
            if action_id == "check_updates":
                current_version = str(snapshot.get("resolved_cli_version", "") or "").strip() or _cli_version(
                    executable
                )
                _clear_console_for_action(action_id)
                console_callback = _console_stream_callback_for_action(action_id)
                lines, console_output = _run_cli(
                    [executable, "update"],
                    timeout_seconds=_ACTION_TIMEOUT_SECONDS,
                    capture_console=True,
                    console_callback=console_callback,
                )
                update_info = _update_info_from_lines(lines, current_version=current_version)
                latest = update_info["latest_version"]
                if update_info["available"] and latest:
                    message = f"RC-Astro CLI {latest} is available."
                    tone = "warning"
                elif update_info["available"]:
                    message = "A newer RC-Astro CLI version is available."
                    tone = "warning"
                else:
                    message = "RC-Astro CLI is up to date."
                    tone = "success"
                return {
                    "ok": True,
                    "message": message,
                    "tone": tone,
                    "transient_updates": {
                        _UPDATE_AVAILABLE_PARAM_ID: update_info["available"],
                        _SETTINGS_CONSOLE_PARAM_ID: console_output,
                    },
                }
            if action_id in {"install_update", "download_update"}:
                console_output = []
                _clear_console_for_action(action_id)
                console_callback = _console_stream_callback_for_action(action_id)
                if not bool(snapshot.get(_UPDATE_AVAILABLE_PARAM_ID)):
                    current_version = str(snapshot.get("resolved_cli_version", "") or "").strip() or _cli_version(
                        executable
                    )
                    lines, check_console_output = _run_cli(
                        [executable, "update"],
                        timeout_seconds=_ACTION_TIMEOUT_SECONDS,
                        capture_console=True,
                        console_callback=console_callback,
                    )
                    console_output.extend(check_console_output)
                    update_info = _update_info_from_lines(lines, current_version=current_version)
                    if not update_info["available"]:
                        return {
                            "ok": False,
                            "message": "No RC-Astro CLI update is currently available.",
                            "tone": "warning",
                            "transient_updates": {
                                _UPDATE_AVAILABLE_PARAM_ID: False,
                                _SETTINGS_CONSOLE_PARAM_ID: console_output,
                            },
                        }
                lines, install_console_output = _run_cli(
                    [executable, "update", "--install"],
                    timeout_seconds=_UPDATE_TIMEOUT_SECONDS,
                    capture_console=True,
                    console_callback=console_callback,
                )
                console_output.extend(install_console_output)
                version = _cli_version(executable)
                message = "\n".join(lines[-5:]) or "RC-Astro update command completed."
                updates = {
                    _UPDATE_AVAILABLE_PARAM_ID: False,
                    _SETTINGS_CONSOLE_PARAM_ID: console_output,
                }
                if version:
                    updates["resolved_cli_version"] = version
                device_updates = _device_option_setting_updates(executable, version)
                updates.update(device_updates)
                result = {
                    "ok": True,
                    "message": message,
                    "tone": "success",
                    "transient_updates": updates,
                }
                if device_updates:
                    result["settings_updates"] = device_updates
                return result
        except Exception as exc:
            result = {"ok": False, "message": str(exc), "tone": "error"}
            console_output = getattr(exc, "console_output", None)
            if console_output:
                result["transient_updates"] = _console_updates_for_action(action_id, console_output)
            return result
        return {"ok": False, "message": f"Unsupported RC-Astro action: {action_id}", "tone": "warning"}

    def _activate_product(self, executable, product, snapshot):
        email = str(snapshot.get("activation_email", "") or "").strip()
        key = str(snapshot.get("activation_key", "") or "").strip()
        if not email or not key:
            return {
                "ok": False,
                "message": "Enter the activation email and key before activating.",
                "tone": "warning",
            }
        payload = f"{email}\n{key}\n"
        _clear_console_for_action("activate_selected")
        lines, console_output = _run_cli(
            [executable, product, "--activate"],
            timeout_seconds=_ACTION_TIMEOUT_SECONDS,
            stdin_payload=payload,
            capture_console=True,
            console_callback=_console_stream_callback_for_action("activate_selected"),
        )
        updates = _activation_status_updates(executable, product)
        updates["activation_email"] = ""
        updates["activation_key"] = ""
        updates[_ACTIVATION_CONSOLE_PARAM_ID] = console_output or _console_output_from_lines(lines)
        return {
            "ok": True,
            "message": f"{_PRODUCTS[product]['name']} activation command completed.",
            "tone": "success",
            "transient_updates": updates,
        }

    def on_process_launch(self):
        _log_info(f"RC-Astro {self.product.upper()} adapter started. The RC-Astro CLI and models are user-installed.")

    def _meta_params(self):
        product_info = _PRODUCTS[self.product]
        meta = ui.process_window_meta(
            size=(640, 460),
            fixed_size=True,
            target_selector=True,
            target_channel_filter=[1, 3],
            tool_configuration={
                **_tool_configuration(),
                "button_label": "Settings",
                "open_extension_settings": True,
                "show_configured_banner": False,
            },
        )
        meta["header_description"] = (
            f"{product_info['display']} adapter. It uses the host-resolved RC-Astro CLI path and "
            "keeps RC-Astro binaries, models, and license material outside this package."
        )
        return [meta]

    def _resolved_cli(self):
        return _resolved_cli_from_mapping(
            {
                _RESOLVED_CLI_KEY: self.settings.get(_RESOLVED_CLI_KEY, ""),
            }
        )

    def _schema_cli(self):
        snapshot = {
            _CLI_SETTING_KEY: self.settings.get(_CLI_SETTING_KEY, ""),
            _LEGACY_CLI_SETTING_KEY: self.settings.get(_LEGACY_CLI_SETTING_KEY, ""),
            _RESOLVED_CLI_KEY: self.settings.get(_RESOLVED_CLI_KEY, ""),
            "configured_folder": self.settings.get("configured_folder", ""),
            "resolution_source": self.settings.get("resolution_source", ""),
            "resolved_cli_version": self.settings.get("resolved_cli_version", ""),
            "resolver_diagnostic": self.settings.get("resolver_diagnostic", ""),
        }
        executable, _snapshot = _resolve_cli_for_settings_action(snapshot)
        return executable

    def get_params(self):
        params = self._meta_params()
        params.extend(_schema_params(_fast_product_schema(self.product, _device_options_from_settings(self.settings))))
        return params

    def validate_process(self, params, input_metadata):
        del params, input_metadata
        try:
            executable = self._schema_cli()
            state, status = _activation_state_for_product(executable, self.product)
        except Exception as exc:
            return [
                {
                    "ok": False,
                    "severity": "error",
                    "message": f"RC-Astro CLI is not ready: {exc}",
                }
            ]
        if state is False:
            return [_activation_validation_diagnostic(self.product, status)]
        return []

    def handle_param_action(self, action_id, target, src_image, params):
        del target, src_image, params
        if action_id not in {"list_models", "download_models", "force_redownload_models"}:
            return {}

        executable = self._schema_cli()
        schema = _load_product_schema(executable, self.product)
        if action_id == "list_models":
            return {_MODEL_STATUS_PARAM_ID: _model_status_text(schema, self.product)}

        command = [executable, "download-models"]
        if action_id == "force_redownload_models":
            command.append("--force")
        _run_cli(command, timeout_seconds=60.0)
        return {
            _MODEL_STATUS_PARAM_ID: (f"Model download command completed. {_model_status_text(schema, self.product)}")
        }

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None, output_masks=None):
        executable = self._resolved_cli()
        schema = _load_product_schema(executable, self.product)
        _require_activated_product(executable, self.product, schema)
        workspace = _Workspace()
        _progress_text(progress, f"Preparing {_PRODUCTS[self.product]['name']}...")
        original_metadata = _metadata_snapshot(src_image)
        io.save(src_image, workspace.input_path)
        command = _command_for_schema(
            executable,
            self.product,
            schema,
            workspace.input_path,
            workspace.output_path,
            workspace.stars_path,
            params or {},
        )
        output_lines = _run_cli(command, timeout_seconds=_RUN_TIMEOUT_SECONDS, progress=progress, cwd=workspace.root)
        if not workspace.output_path.exists():
            raise RcAstroError(f"RC-Astro did not produce the expected output: {workspace.output_path}")
        result = io.load(workspace.output_path)
        dst_image.copy_from(result)
        _restore_original_metadata(dst_image, original_metadata)
        if self.product == "sxt":
            for stars_path in _sxt_stars_output_paths(output_lines, workspace):
                try:
                    stars_image = io.load(stars_path)
                    _restore_original_metadata(stars_image, original_metadata)
                    ui.open_image(stars_image, title="RC-Astro SXT Stars")
                except Exception as exc:
                    _log_warning(f"Could not open SXT stars output: {exc}")
        _progress_value(progress, 100.0)
        _progress_text(progress, f"{_PRODUCTS[self.product]['name']} complete")


class RcAstroBxtExtension(_RcAstroBase):
    product = "bxt"


class RcAstroSxtExtension(_RcAstroBase):
    product = "sxt"


class RcAstroNxtExtension(_RcAstroBase):
    product = "nxt"

"""Cosmic Clarity process suite migrated to the extension runtime."""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import signal
import subprocess
import tempfile
import uuid

import afternight
from afternight import io, ui


_PROGRESS_RE = re.compile(r".*(?:Progress|PROGRESS):\s+([0-9.]+)%")

_COSMIC_CLARITY_SETTING_KEY = "executable_path"
_COSMIC_CLARITY_REQUIRED_EXECUTABLES = [
    "setiastrocosmicclarity_denoise",
    "setiastrocosmicclarity_superres",
    "setiastrocosmicclarity",
    "setiastrocosmicclarity_darkstar",
]
_SHARPENING_MODE_ARGS = {
    "both": "Both",
    "stellar_only": "Stellar Only",
    "non_stellar_only": "Non-Stellar Only",
}
_COSMIC_CLARITY_CUDA_FAILURE_MARKERS = (
    "cuda error",
    "no kernel image is available",
    "cuda kernel errors",
)
_COSMIC_CLARITY_AUTO_PSF_FAILURE_MARKERS = (
    "zero-size array to reduction operation maximum",
)
_MAX_CAPTURED_PROCESS_OUTPUT_LINES = 400
_MAX_PROCESS_FAILURE_OUTPUT_LINES = 40
_MAX_PROCESS_FAILURE_OUTPUT_CHARS = 6000


def _known_failure_hint(output_lines):
    output_text = "\n".join(output_lines).casefold()
    if "torch._c._sparse" in output_text and "_spsolve" in output_text:
        return (
            "Cosmic Clarity Super-Resolution failed while importing its bundled "
            "PyTorch runtime. This usually means the installed SuperRes executable "
            "or its bundled _internal files are incompatible/corrupted; update or "
            "reinstall the Cosmic Clarity suite."
        )
    return ""


def _process_failure_message(returncode, output_lines):
    hint = _known_failure_hint(output_lines)
    parts = [f"CosmicClarity exited with status {returncode}."]
    if hint:
        parts.append(hint)

    if output_lines:
        tail = "\n".join(output_lines[-_MAX_PROCESS_FAILURE_OUTPUT_LINES:])
        if len(tail) > _MAX_PROCESS_FAILURE_OUTPUT_CHARS:
            tail = "..." + tail[-_MAX_PROCESS_FAILURE_OUTPUT_CHARS:]
        parts.append(f"Last helper output:\n{tail}")
    else:
        parts.append("The helper did not write any output before exiting.")

    return "\n\n".join(parts)


def _is_cuda_failure(output_lines):
    output_text = "\n".join(output_lines).casefold()
    return any(marker in output_text for marker in _COSMIC_CLARITY_CUDA_FAILURE_MARKERS)


def _is_auto_psf_failure(output_lines):
    output_text = "\n".join(output_lines).casefold()
    return any(marker in output_text for marker in _COSMIC_CLARITY_AUTO_PSF_FAILURE_MARKERS)


def _sharpening_mode_from_args(args):
    try:
        mode_index = args.index("--sharpening_mode")
    except ValueError:
        return ""

    if mode_index + 1 >= len(args):
        return ""
    return str(args[mode_index + 1])


def _is_both_sharpening(args):
    return _sharpening_mode_from_args(args) == "Both"


def _sharpening_progress_phase(line, current_phase):
    marker = line.strip().casefold()
    if marker.startswith("non-stellar sharpening"):
        return 1
    if marker.startswith("stellar sharpening"):
        return 0
    return current_phase


def _reported_progress_percent(percent, two_pass_progress, phase):
    if not two_pass_progress:
        return percent
    if phase <= 0:
        return percent * 0.5
    return 50.0 + percent * 0.5


def _log_launch_banner(process_name, subtitle, *, component):
    afternight.log_info(
        "\n".join([
            "",
            "##############################################",
            f"# Cosmic Clarity - {process_name}",
            f"# {subtitle}",
            "# Wrapped process author: Seti Astro",
            "# AfterNight extension maintainer: Ezequiel Ruiz",
            "# Upstream: https://github.com/setiastro/cosmicclarity",
            "##############################################",
        ]),
        component=component,
    )


class _Workspace:
    def __init__(self, root=None):
        if root is None:
            base_dir = pathlib.Path(afternight.session_paths().temp_dir() or tempfile.gettempdir())
            self.root = base_dir / f"cosmic_clarity_{uuid.uuid4().hex}"
            self._owns_root = True
        else:
            self.root = pathlib.Path(root)
            self._owns_root = False
        self.input_dir = self.root / "input"
        self.output_dir = self.root / "output"
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._tracked_paths = []

    def track(self, *paths):
        self._tracked_paths.extend(pathlib.Path(path) for path in paths if path)

    def cleanup_outputs(self):
        for path in self._tracked_paths:
            path = pathlib.Path(path)
            if path.parent != self.output_dir:
                continue

            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def cleanup(self):
        if self._owns_root:
            shutil.rmtree(self.root, ignore_errors=True)
            return

        for path in self._tracked_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


class _CosmicClarityBase(ui.ProcessWindow):
    component = "extension.cosmic_clarity"
    window_size = (600, 400)
    process_name = "Cosmic Clarity"
    process_subtitle = "External astrophotography helper process"
    not_configured_text = (
        "Cosmic Clarity is not configured. Click Configure to select the installation folder."
    )

    def on_process_launch(self):
        _log_launch_banner(
            self.process_name,
            self.process_subtitle,
            component=self.component,
        )
        afternight.log_info(
            "Cosmic Clarity: helper executables run out-of-process from the "
            "user-configured suite folder.",
            component=self.component,
        )

    def get_settings_params(self):
        return [
            {
                "id": "executable_path",
                "type": "dir_path",
                "label": "Cosmic Clarity Folder",
                "default": "",
                "group": "Tool Configuration",
                "tooltip": (
                    "Path to the Cosmic Clarity installation folder. This extension-scoped "
                    "setting is shared by all Cosmic Clarity processes."
                ),
            },
            {
                "id": "gpu_enabled",
                "type": "bool",
                "label": "Use GPU Acceleration",
                "default": True,
                "group": "Tool Configuration",
                "tooltip": "Enable GPU acceleration when the packaged CosmicClarity build supports it.",
            },
        ]

    def _meta_params(self):
        meta = ui.process_window_meta(
            size=self.window_size,
            fixed_size=True,
            target_selector=True,
            target_channel_filter=[1, 3],
            tool_configuration={
                "settings_key": _COSMIC_CLARITY_SETTING_KEY,
                "label": "Cosmic Clarity",
                "button_label": "Configure",
                "dialog_title": "Select Cosmic Clarity Folder",
                "dialog_size": [600, 450],
                "not_configured_text": self.not_configured_text,
                "configured_text": "Cosmic Clarity is configured and ready to use.",
                "show_configured_banner": False,
                "required_executables": _COSMIC_CLARITY_REQUIRED_EXECUTABLES,
                "append_platform_executable_suffix": True,
                "require_executable": True,
                "download_page_url": "https://www.setiastro.com/cosmic-clarity",
                "download_note": (
                    "Initial Cosmic Clarity downloads are hosted by Seti Astro. "
                    "After downloading the current platform suite, unzip it and "
                    "select the folder that contains the Cosmic Clarity executables. "
                    "Existing installations can be checked and updated from the "
                    "platform release files."
                ),
                "install_instructions": (
                    "Select the Cosmic Clarity suite folder containing "
                    "SetiAstroCosmicClarity, SetiAstroCosmicClarity_denoise, "
                    "setiastrocosmicclarity_superres, and "
                    "setiastrocosmicclarity_darkstar."
                ),
                "update_page_url": "https://github.com/setiastro/cosmicclarity/releases",
                "platform_update_api_urls": {
                    "linux": (
                        "https://api.github.com/repos/setiastro/cosmicclarity/"
                        "releases/tags/Linux"
                    ),
                    "windows": (
                        "https://api.github.com/repos/setiastro/cosmicclarity/"
                        "releases/tags/Windows"
                    ),
                },
            },
        )
        meta["header_description"] = (
            "Seti Astro Cosmic Clarity helper wrapped by AfterNight. Configure the "
            "external suite folder once, then run the selected denoise, star, "
            "sharpening, or super-resolution process."
        )
        return [meta]

    def _tool_dir(self):
        raw_path = str(self.settings.get(_COSMIC_CLARITY_SETTING_KEY, "") or "").strip()
        if not raw_path:
            raise RuntimeError(
                "Cosmic Clarity is not configured. Use Configure in the process window "
                "and select the Cosmic Clarity installation folder."
            )

        tool_dir = pathlib.Path(raw_path)
        if not tool_dir.is_dir():
            raise RuntimeError(f"Configured CosmicClarity directory does not exist: {tool_dir}")
        afternight.log_info(
            f"Cosmic Clarity: using configured suite folder {tool_dir}.",
            component=self.component,
        )
        return tool_dir

    def _resolve_tool_executable(self, executable_name):
        tool_dir = self._tool_dir()
        executable = tool_dir / executable_name
        if executable.exists():
            return executable

        executable_name_key = executable_name.casefold()
        try:
            for candidate in tool_dir.iterdir():
                if candidate.is_file() and candidate.name.casefold() == executable_name_key:
                    return candidate
        except OSError as exc:
            raise RuntimeError(f"Could not inspect CosmicClarity directory: {tool_dir}") from exc

        return executable

    def _tool_executable(self, base_name):
        suffix = ".exe" if os.name == "nt" else ""
        executable = self._resolve_tool_executable(f"{base_name}{suffix}")
        if not executable.exists():
            raise RuntimeError(f"CosmicClarity executable not found: {executable}")
        return executable

    def _terminate_process_tree(self, process, reason="cancellation"):
        if process.poll() is not None:
            return

        reason_text = "after cancellation" if reason == "cancellation" else f"for {reason}"
        afternight.log_warning(
            f"Terminating CosmicClarity helper process tree {reason_text}.",
            component=self.component,
        )

        if os.name == "nt":
            ctrl_break = getattr(subprocess, "CTRL_BREAK_EVENT", None)
            creation_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            if ctrl_break is not None and creation_group:
                try:
                    process.send_signal(ctrl_break)
                    process.wait(timeout=2.0)
                except Exception:
                    pass
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=2.0)
            except Exception:
                pass

        if process.poll() is not None:
            return

        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                process.kill()

        try:
            process.wait(timeout=2.0)
        except Exception:
            pass

    def _retry_on_cpu(self, executable, args, workspace, progress, allow_auto_psf_retry):
        workspace.cleanup_outputs()
        afternight.log_warning(
            "CosmicClarity CUDA execution failed; retrying once on CPU "
            "(--disable_gpu).",
            component=self.component,
        )
        progress.set_text("Cosmic Clarity CUDA failed; retrying on CPU...")
        return self._run_process(
            executable,
            [*args, "--disable_gpu"],
            workspace,
            progress,
            allow_gpu_retry=False,
            allow_auto_psf_retry=allow_auto_psf_retry,
        )

    def _run_process(
        self,
        executable,
        args,
        workspace,
        progress,
        allow_gpu_retry=True,
        allow_auto_psf_retry=True,
    ):
        args = list(args)
        command = [str(executable), *args]
        afternight.log_info(
            f"Launching CosmicClarity helper: {' '.join(command)}",
            component=self.component,
        )
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(
            command,
            cwd=str(workspace.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )

        two_pass_progress = _is_both_sharpening(args)
        phase = 0
        last_reported_percent = 0.0
        output_lines = []
        try:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    afternight.log_debug(line, component=self.component)
                    output_lines.append(line)
                    if len(output_lines) > _MAX_CAPTURED_PROCESS_OUTPUT_LINES:
                        output_lines.pop(0)
                if progress.is_cancelled():
                    self._terminate_process_tree(process)
                    raise RuntimeError("CosmicClarity processing was cancelled.")

                if (
                    allow_gpu_retry
                    and "--disable_gpu" not in args
                    and _is_cuda_failure(output_lines)
                ):
                    self._terminate_process_tree(process, reason="CPU retry")
                    return self._retry_on_cpu(
                        executable,
                        args,
                        workspace,
                        progress,
                        allow_auto_psf_retry=allow_auto_psf_retry,
                    )

                if two_pass_progress:
                    phase = _sharpening_progress_phase(line, phase)

                match = _PROGRESS_RE.match(line)
                if not match:
                    continue

                percent = max(0.0, min(100.0, float(match.group(1))))
                reported_percent = _reported_progress_percent(
                    percent,
                    two_pass_progress,
                    phase,
                )
                if reported_percent >= last_reported_percent:
                    last_reported_percent = reported_percent
                    progress.set_value(reported_percent)

            process.wait()
            if process.returncode != 0:
                if (
                    allow_gpu_retry
                    and "--disable_gpu" not in args
                    and _is_cuda_failure(output_lines)
                ):
                    return self._retry_on_cpu(
                        executable,
                        args,
                        workspace,
                        progress,
                        allow_auto_psf_retry=allow_auto_psf_retry,
                    )
                if (
                    allow_auto_psf_retry
                    and "--auto_detect_psf" in args
                    and _is_auto_psf_failure(output_lines)
                ):
                    workspace.cleanup_outputs()
                    afternight.log_warning(
                        "CosmicClarity auto PSF detection failed; retrying once with fixed PSF "
                        "(--auto_detect_psf disabled).",
                        component=self.component,
                    )
                    progress.set_text("Cosmic Clarity auto PSF failed; retrying with fixed PSF...")
                    return self._run_process(
                        executable,
                        [arg for arg in args if arg != "--auto_detect_psf"],
                        workspace,
                        progress,
                        allow_gpu_retry=allow_gpu_retry,
                        allow_auto_psf_retry=False,
                    )
                raise RuntimeError(_process_failure_message(process.returncode, output_lines))
            afternight.log_info(
                f"CosmicClarity helper completed successfully: {pathlib.Path(executable).name}",
                component=self.component,
            )
        finally:
            if process.stdout is not None:
                process.stdout.close()

    def _copy_loaded_result(self, path, dst_image):
        if not path.exists():
            raise RuntimeError(f"CosmicClarity did not produce the expected output: {path}")

        result = io.load(path)
        dst_image.copy_from(result)
        afternight.log_info(
            f"Cosmic Clarity: loaded result image from {path}.",
            component=self.component,
        )

    def _resolve_output_path(self, expected_path, input_path, output_suffix):
        if expected_path.exists():
            return expected_path

        output_dir = pathlib.Path(expected_path).parent
        output_stem = f"{pathlib.Path(input_path).stem}{output_suffix}"
        try:
            matches = [
                candidate
                for candidate in output_dir.iterdir()
                if candidate.is_file() and candidate.stem.casefold() == output_stem.casefold()
            ]
        except OSError:
            return expected_path

        if not matches:
            return expected_path

        return max(matches, key=lambda candidate: candidate.stat().st_mtime)


class CosmicClarityDenoiseExtension(_CosmicClarityBase):
    process_name = "Denoise"
    process_subtitle = "Seti Astro noise reduction helper"
    not_configured_text = (
        "Cosmic Clarity Denoise 6.5+ is required. Click Configure to select the "
        "Cosmic Clarity installation folder."
    )

    def get_params(self):
        return self._meta_params() + [
            {"id": "general", "type": "section", "label": "Denoise"},
            {
                "id": "strength",
                "type": "float",
                "label": "Strength",
                "default": 0.9,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
            },
            {
                "id": "denoise_mode",
                "type": "choice",
                "label": "Denoise Mode",
                "default": "full",
                "options": [
                    ["Full", "full"],
                    ["Luminance", "luminance"],
                ],
            },
        ]

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None,
                output_masks=None):
        del target, masks, weights, output_masks
        progress.set_text("Preparing Cosmic Clarity Denoise...")
        afternight.log_info(
            f"Cosmic Clarity Denoise: strength={float(params.get('strength', 0.9)):.3f}, "
            f"mode={params.get('denoise_mode', 'full')}, "
            f"GPU={'enabled' if bool(self.settings.get('gpu_enabled', True)) else 'disabled'}.",
            component=self.component,
        )

        workspace = _Workspace(self._tool_dir())
        try:
            input_path = workspace.input_dir / f"afternight_{uuid.uuid4().hex}.tiff"
            output_path = workspace.output_dir / f"{input_path.stem}_denoised.tiff"
            workspace.track(input_path, output_path)
            io.save(src_image, input_path)

            args = [
                "--denoise_strength",
                str(float(params.get("strength", 0.9))),
                "--denoise_mode",
                str(params.get("denoise_mode", "full")),
            ]
            if not bool(self.settings.get("gpu_enabled", True)):
                args.append("--disable_gpu")

            self._run_process(
                self._tool_executable("setiastrocosmicclarity_denoise"),
                args,
                workspace,
                progress,
            )
            resolved_output_path = self._resolve_output_path(output_path, input_path, "_denoised")
            workspace.track(resolved_output_path)
            self._copy_loaded_result(resolved_output_path, dst_image)
        finally:
            workspace.cleanup()


class CosmicClarityDarkStarExtension(_CosmicClarityBase):
    process_name = "Dark Star"
    process_subtitle = "Seti Astro star separation helper"
    not_configured_text = (
        "Cosmic Clarity Dark Star is required. Click Configure to select the "
        "Cosmic Clarity installation folder."
    )

    def get_params(self):
        return self._meta_params() + [
            {"id": "general", "type": "section", "label": "Dark Star"},
            {
                "id": "pre_stretch_linear_image",
                "type": "bool",
                "label": "Pre-stretch Linear Image",
                "default": False,
            },
            {
                "id": "star_removal_mode",
                "type": "choice",
                "label": "Mode",
                "default": "additive",
                "options": [
                    ["Additive", "additive"],
                    ["Unscreen", "unscreen"],
                ],
            },
            {
                "id": "chunk_size",
                "type": "int",
                "label": "Chunk Size",
                "default": 256,
                "min": 64,
                "max": 2048,
            },
            {
                "id": "show_extracted_stars",
                "type": "bool",
                "label": "Save Extracted Stars Artifact",
                "default": False,
            },
        ]

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None,
                output_masks=None):
        del target, masks, weights, output_masks
        progress.set_text("Preparing Cosmic Clarity Dark Star...")
        afternight.log_info(
            f"Cosmic Clarity Dark Star: mode={params.get('star_removal_mode', 'additive')}, "
            f"chunk_size={int(params.get('chunk_size', 256))}, "
            f"pre_stretch={'enabled' if bool(params.get('pre_stretch_linear_image', False)) else 'disabled'}, "
            f"stars_artifact={'enabled' if bool(params.get('show_extracted_stars', False)) else 'disabled'}, "
            f"GPU={'enabled' if bool(self.settings.get('gpu_enabled', True)) else 'disabled'}.",
            component=self.component,
        )

        workspace = _Workspace(self._tool_dir())
        try:
            input_path = workspace.input_dir / f"afternight_{uuid.uuid4().hex}.tiff"
            output_path = workspace.output_dir / f"{input_path.stem}_starless.tiff"
            stars_path = workspace.output_dir / f"{input_path.stem}_stars_only.tiff"
            workspace.track(input_path, output_path, stars_path)
            io.save(src_image, input_path)

            args = [
                "--chunk_size",
                str(int(params.get("chunk_size", 256))),
                "--star_removal_mode",
                str(params.get("star_removal_mode", "additive")),
            ]
            if bool(params.get("pre_stretch_linear_image", False)):
                args.append("--pre_stretch")
            if bool(params.get("show_extracted_stars", False)):
                args.append("--show_extracted_stars")
            if not bool(self.settings.get("gpu_enabled", True)):
                args.append("--disable_gpu")

            self._run_process(
                self._tool_executable("setiastrocosmicclarity_darkstar"),
                args,
                workspace,
                progress,
            )
            resolved_output_path = self._resolve_output_path(output_path, input_path, "_starless")
            workspace.track(resolved_output_path)
            self._copy_loaded_result(resolved_output_path, dst_image)

            if bool(params.get("show_extracted_stars", False)) and stars_path.exists():
                artifacts_dir = afternight.session_paths().artifacts_dir()
                if artifacts_dir:
                    artifact_path = pathlib.Path(artifacts_dir) / stars_path.name
                    io.save(io.load(stars_path), artifact_path)
                    afternight.log_info(
                        f"Cosmic Clarity Dark Star: saved extracted stars artifact to {artifact_path}",
                        component=self.component,
                    )
        finally:
            workspace.cleanup()


class CosmicClaritySharpeningExtension(_CosmicClarityBase):
    window_size = (600, 400)
    process_name = "Sharpening"
    process_subtitle = "Seti Astro stellar and non-stellar sharpening helper"
    not_configured_text = (
        "Cosmic Clarity Sharpen 6.5+ is required. Click Configure to select the "
        "Cosmic Clarity installation folder."
    )

    def get_params(self):
        return self._meta_params() + [
            {"id": "general", "type": "section", "label": "Sharpening"},
            {
                "id": "sharpening_mode",
                "type": "choice",
                "label": "Mode",
                "default": "both",
                "options": [
                    ["Both", "both"],
                    ["Stellar Only", "stellar_only"],
                    ["Non-Stellar Only", "non_stellar_only"],
                ],
            },
            {
                "id": "non_stellar_strength",
                "type": "float",
                "label": "Non-Stellar Strength",
                "default": 3.0,
                "min": 0.1,
                "max": 12.0,
                "step": 0.1,
            },
            {
                "id": "non_stellar_amount",
                "type": "float",
                "label": "Non-Stellar Amount",
                "default": 0.5,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
            },
            {
                "id": "stellar_amount",
                "type": "float",
                "label": "Stellar Amount",
                "default": 0.5,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
            },
            {
                "id": "auto_detect_psf",
                "type": "bool",
                "label": "Auto Detect PSF",
                "default": True,
            },
            {
                "id": "process_rgb_channels",
                "type": "bool",
                "label": "Process RGB Channels",
                "default": False,
            },
        ]

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None,
                output_masks=None):
        del target, masks, weights, output_masks
        progress.set_text("Preparing Cosmic Clarity Sharpening...")
        afternight.log_info(
            f"Cosmic Clarity Sharpening: mode={params.get('sharpening_mode', 'both')}, "
            f"non_stellar_strength={float(params.get('non_stellar_strength', 3.0)):.3f}, "
            f"non_stellar_amount={float(params.get('non_stellar_amount', 0.5)):.3f}, "
            f"stellar_amount={float(params.get('stellar_amount', 0.5)):.3f}, "
            f"auto_psf={'enabled' if bool(params.get('auto_detect_psf', True)) else 'disabled'}, "
            f"rgb_channels={'enabled' if bool(params.get('process_rgb_channels', False)) else 'disabled'}, "
            f"GPU={'enabled' if bool(self.settings.get('gpu_enabled', True)) else 'disabled'}.",
            component=self.component,
        )

        workspace = _Workspace(self._tool_dir())
        try:
            input_path = workspace.input_dir / f"afternight_{uuid.uuid4().hex}.tiff"
            output_path = workspace.output_dir / f"{input_path.stem}_sharpened.tiff"
            workspace.track(input_path, output_path)
            io.save(src_image, input_path)

            sharpening_mode = _SHARPENING_MODE_ARGS.get(
                str(params.get("sharpening_mode", "both")),
                "Both",
            )

            args = [
                "--sharpening_mode",
                sharpening_mode,
                "--nonstellar_strength",
                str(float(params.get("non_stellar_strength", 3.0))),
            ]
            if sharpening_mode in ("Both", "Non-Stellar Only"):
                args.extend([
                    "--nonstellar_amount",
                    str(float(params.get("non_stellar_amount", 0.5))),
                ])
            if sharpening_mode in ("Both", "Stellar Only"):
                args.extend([
                    "--stellar_amount",
                    str(float(params.get("stellar_amount", 0.5))),
                ])
            if bool(params.get("auto_detect_psf", True)):
                args.append("--auto_detect_psf")
            if bool(params.get("process_rgb_channels", False)):
                args.append("--sharpen_channels_separately")
            if not bool(self.settings.get("gpu_enabled", True)):
                args.append("--disable_gpu")

            self._run_process(
                self._tool_executable("setiastrocosmicclarity"),
                args,
                workspace,
                progress,
            )
            resolved_output_path = self._resolve_output_path(output_path, input_path, "_sharpened")
            workspace.track(resolved_output_path)
            self._copy_loaded_result(resolved_output_path, dst_image)
        finally:
            workspace.cleanup()


class CosmicClaritySuperResExtension(_CosmicClarityBase):
    process_name = "Super Resolution"
    process_subtitle = "Seti Astro upscaling helper"
    not_configured_text = (
        "Cosmic Clarity Super-Resolution 1.1+ is required. Click Configure to select "
        "the Cosmic Clarity installation folder."
    )

    def get_params(self):
        return self._meta_params() + [
            {"id": "general", "type": "section", "label": "Super Resolution"},
            {
                "id": "scale",
                "type": "choice",
                "label": "Scale",
                "default": "2",
                "options": [
                    ["2x", "2"],
                    ["3x", "3"],
                    ["4x", "4"],
                ],
            },
        ]

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None,
                output_masks=None):
        del target, masks, weights, output_masks, dst_image
        progress.set_text("Preparing Cosmic Clarity Super Resolution...")
        scale = str(params.get("scale", "2"))
        afternight.log_info(
            f"Cosmic Clarity Super Resolution: scale={scale}x, "
            f"GPU={'enabled' if bool(self.settings.get('gpu_enabled', True)) else 'disabled'}.",
            component=self.component,
        )

        workspace = _Workspace()
        try:
            input_path = workspace.input_dir / f"afternight_{uuid.uuid4().hex}.tiff"
            output_path = workspace.output_dir / f"{input_path.stem}_upscaled{scale}x.fit"
            workspace.track(input_path, output_path)
            io.save(src_image, input_path)

            self._run_process(
                self._tool_executable("setiastrocosmicclarity_superres"),
                [
                    "--input",
                    str(input_path),
                    "--output_dir",
                    str(workspace.output_dir),
                    "--scale",
                    scale,
                ],
                workspace,
                progress,
                allow_gpu_retry=False,
            )

            resolved_output_path = self._resolve_output_path(
                output_path,
                input_path,
                f"_upscaled{scale}x",
            )
            workspace.track(resolved_output_path)

            if resolved_output_path.exists():
                result = io.load(resolved_output_path)
                ui.commit_image(
                    result,
                    history_step_name="Cosmic Clarity Super-Resolution",
                    history_step_description=f"Applied Cosmic Clarity {scale}x super-resolution",
                    metadata=result.metadata,
                    allow_resized_output=True,
                )
                progress.set_value(100.0)
                progress.set_text("Cosmic Clarity Super Resolution complete")
                afternight.log_info(
                    f"Cosmic Clarity Super Resolution: committed {scale}x result from {resolved_output_path}.",
                    component=self.component,
                )
                return

            raise RuntimeError(
                "CosmicClarity Super Resolution did not produce the expected output file."
            )
        finally:
            workspace.cleanup()

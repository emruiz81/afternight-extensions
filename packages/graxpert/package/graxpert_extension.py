"""GraXpert process suite migrated to the extension runtime."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import pathlib
import re
import shutil
import time
import zipfile

import afternight
from afternight import ui


class _ProgressAdapter:
    def __init__(self, progress):
        self._progress = progress
        self._value = 0.0

    def update(self, delta):
        if self._progress.is_cancelled():
            raise RuntimeError("GraXpert processing was cancelled.")

        self._value = max(0.0, min(100.0, self._value + float(delta)))
        self._progress.set_value(self._value)


def _run_callable_directly(fn):
    return fn()


def _log_launch_banner(process_name, subtitle, *, component):
    afternight.log_info(
        "\n".join([
            "",
            "##############################################",
            f"# GraXpert AI - {process_name}",
            f"# {subtitle}",
            "# Wrapped process authors: GraXpert Development Team",
            "# AfterNight extension maintainer: Ezequiel Ruiz",
            "# Upstream: https://github.com/Steffenhir/GraXpert",
            "##############################################",
        ]),
        component=component,
    )


class _GraXpertBase(ui.ProcessWindow):
    component = "extension.graxpert"
    _REMOTE_MODEL_CACHE_TTL_SECONDS = 12 * 60 * 60
    window_size = (600, 400)
    process_name = "GraXpert"
    process_subtitle = "AI astrophotography processing"

    def on_process_launch(self):
        _log_launch_banner(
            self.process_name,
            self.process_subtitle,
            component=self.component,
        )
        afternight.log_info(
            "GraXpert: model cache, GPU provider diagnostics, and download state "
            "are managed by the AfterNight extension host.",
            component=self.component,
        )

    def _patch_ai_model_handling(self, ai_model_handling):
        if getattr(ai_model_handling, "_afternight_run_in_process_patch", False):
            return

        # The extension host already isolates GraXpert in its own process, so
        # GraXpert's extra multiprocessing hop only adds Python 3.14 pickling
        # failures and can break initialized CUDA sessions.
        ai_model_handling.run_in_process = _run_callable_directly
        ai_model_handling._afternight_run_in_process_patch = True

    def _graxpert_user_data_dir(self):
        try:
            from platformdirs import user_data_dir

            return pathlib.Path(user_data_dir(appname="GraXpert"))
        except Exception:
            if os.name == "nt":
                base_dir = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                if base_dir:
                    return pathlib.Path(base_dir) / "GraXpert"
                return pathlib.Path.home() / "AppData" / "Local" / "GraXpert"

            base_dir = os.environ.get("XDG_DATA_HOME")
            if base_dir:
                return pathlib.Path(base_dir) / "GraXpert"

            return pathlib.Path.home() / ".local" / "share" / "GraXpert"

    def _model_dir_path(self, model_dir_key):
        dir_names = {
            "bge_ai_models_dir": "bge-ai-models",
            "denoise_ai_models_dir": "denoise-ai-models",
            "deconvolution_object_ai_models_dir": "deconvolution-object-ai-models",
            "deconvolution_stars_ai_models_dir": "deconvolution-stars-ai-models",
        }
        dir_name = dir_names.get(model_dir_key)
        if not dir_name:
            return None

        return self._graxpert_user_data_dir() / dir_name

    def _remote_model_cache_path(self):
        return self._graxpert_user_data_dir() / ".afternight_remote_model_versions.json"

    def _remote_model_cache(self):
        cache = getattr(self, "_remote_model_cache_data", None)
        if cache is not None:
            return cache

        cache_path = self._remote_model_cache_path()
        try:
            loaded_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            loaded_cache = {}

        if not isinstance(loaded_cache, dict):
            loaded_cache = {}

        entries = loaded_cache.get("entries")
        if not isinstance(entries, dict):
            loaded_cache["entries"] = {}

        self._remote_model_cache_data = loaded_cache
        return self._remote_model_cache_data

    def _write_remote_model_cache(self):
        cache = self._remote_model_cache()
        cache_path = self._remote_model_cache_path()
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_name(cache_path.name + ".tmp")
            temp_path.write_text(
                json.dumps(cache, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temp_path.replace(cache_path)
        except Exception:
            return

    def _cached_remote_model_versions(self, bucket_name):
        entry = self._remote_model_cache().get("entries", {}).get(bucket_name)
        if not isinstance(entry, dict):
            return [], False

        raw_versions = entry.get("versions")
        versions = [str(version) for version in raw_versions] if isinstance(raw_versions, list) else []
        try:
            fetched_at = float(entry.get("fetched_at", 0.0))
        except Exception:
            fetched_at = 0.0

        is_fresh = (time.time() - fetched_at) <= self._REMOTE_MODEL_CACHE_TTL_SECONDS
        return versions, is_fresh

    def _update_remote_model_cache(self, bucket_name, versions):
        cache = self._remote_model_cache()
        cache.setdefault("entries", {})[bucket_name] = {
            "fetched_at": time.time(),
            "versions": list(versions),
        }
        self._write_remote_model_cache()

    def _model_bucket_name_attr(self, model_dir_key):
        bucket_attrs = {
            "bge_ai_models_dir": "bge_bucket_name",
            "denoise_ai_models_dir": "denoise_bucket_name",
            "deconvolution_object_ai_models_dir": "deconvolution_object_bucket_name",
            "deconvolution_stars_ai_models_dir": "deconvolution_stars_bucket_name",
        }
        return bucket_attrs.get(model_dir_key)

    def _all_model_dir_keys(self):
        return [
            "bge_ai_models_dir",
            "denoise_ai_models_dir",
            "deconvolution_object_ai_models_dir",
            "deconvolution_stars_ai_models_dir",
        ]

    def _inference_model_dir_keys(self):
        return self._all_model_dir_keys()

    def _version_setting_key(self):
        return "ai_version"

    def _sorted_model_versions(self, versions):
        try:
            from packaging.version import InvalidVersion, Version

            def sort_key(version):
                try:
                    return (0, Version(version))
                except InvalidVersion:
                    return (1, version)

            return [
                version
                for version in sorted(versions, key=sort_key, reverse=True)
            ]
        except Exception:
            return sorted(versions, reverse=True)

    def _collect_local_model_versions(self, imported, model_dir_keys):
        del imported
        versions = set()

        for model_dir_key in model_dir_keys:
            model_dir = self._model_dir_path(model_dir_key)
            if model_dir is None or not model_dir.exists() or not model_dir.is_dir():
                continue

            for entry in model_dir.iterdir():
                if entry.name.startswith(".") or not entry.is_dir():
                    continue

                try:
                    has_payload = any(child for child in entry.iterdir())
                except Exception:
                    has_payload = False

                if has_payload:
                    versions.add(entry.name)

        return self._sorted_model_versions(versions)

    def _graxpert_package_root(self):
        try:
            spec = importlib.util.find_spec("graxpert")
        except Exception:
            return None

        if spec is None or not spec.submodule_search_locations:
            return None

        try:
            return pathlib.Path(next(iter(spec.submodule_search_locations)))
        except Exception:
            return None

    def _graxpert_s3_secrets(self):
        cache = getattr(self, "_graxpert_s3_secrets_cache", None)
        if cache is not None:
            return cache

        package_root = self._graxpert_package_root()
        if package_root is None:
            self._graxpert_s3_secrets_cache = None
            return None

        secrets_path = package_root / "s3_secrets.py"
        try:
            source = secrets_path.read_text(encoding="utf-8")
        except Exception:
            self._graxpert_s3_secrets_cache = None
            return None

        try:
            module = ast.parse(source, filename=str(secrets_path))
        except SyntaxError:
            self._graxpert_s3_secrets_cache = None
            return None

        secrets = {}
        for node in module.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            try:
                secrets[target.id] = ast.literal_eval(node.value)
            except Exception:
                continue

        self._graxpert_s3_secrets_cache = secrets or None
        return self._graxpert_s3_secrets_cache

    def _remote_model_version_from_object_name(self, object_name):
        match = re.search(r"(\d+\.\d+\.\d+)", str(object_name or ""))
        if match:
            return match.group(1)
        return None

    def _try_import_graxpert(self):
        if hasattr(self, "_graxpert_import_cache"):
            return self._graxpert_import_cache

        try:
            self._graxpert_import_cache = self._import_graxpert()
        except Exception:
            self._graxpert_import_cache = None
        return self._graxpert_import_cache

    def _collect_remote_model_versions(self, imported, model_dir_keys):
        del imported

        secrets = self._graxpert_s3_secrets()
        if not secrets:
            return []

        try:
            from minio import Minio
        except Exception:
            return []

        endpoint = secrets.get("endpoint")
        access_key = secrets.get("ro_access_key")
        secret_key = secrets.get("ro_secret_key")
        if not endpoint or not access_key or not secret_key:
            return []

        try:
            client = Minio(endpoint, access_key, secret_key)
        except Exception:
            return []

        versions = set()
        for model_dir_key in model_dir_keys:
            bucket_name_attr = self._model_bucket_name_attr(model_dir_key)
            if not bucket_name_attr:
                continue

            bucket_name = secrets.get(bucket_name_attr)
            if not bucket_name:
                continue

            cached_versions, cache_is_fresh = self._cached_remote_model_versions(bucket_name)
            if cache_is_fresh:
                versions.update(cached_versions)
                continue

            try:
                bucket_versions = set()
                for remote_object in client.list_objects(bucket_name):
                    version = self._remote_model_version_from_object_name(
                        getattr(remote_object, "object_name", "")
                    )
                    if version is None:
                        try:
                            tags = client.get_object_tags(bucket_name, remote_object.object_name)
                        except Exception:
                            continue
                        version = tags.get("ai-version") if tags else None
                    if version:
                        bucket_versions.add(str(version))
            except Exception:
                versions.update(cached_versions)
                continue

            sorted_bucket_versions = self._sorted_model_versions(bucket_versions)
            self._update_remote_model_cache(bucket_name, sorted_bucket_versions)
            versions.update(sorted_bucket_versions)

        return self._sorted_model_versions(versions)

    def _model_version_inventory(self, model_dir_keys):
        cache = getattr(self, "_model_versions_cache", None)
        if cache is None:
            cache = {}
            self._model_versions_cache = cache

        cache_key = tuple(model_dir_keys)
        cached_inventory = cache.get(cache_key)
        if cached_inventory is not None:
            return cached_inventory

        local_versions = tuple(self._collect_local_model_versions(None, model_dir_keys))
        remote_versions = tuple(self._collect_remote_model_versions(None, model_dir_keys))
        all_versions = tuple(
            self._sorted_model_versions(set(local_versions).union(remote_versions))
        )
        inventory = {
            "local": local_versions,
            "remote": remote_versions,
            "all": all_versions,
        }
        cache[cache_key] = inventory
        return inventory

    def _available_model_versions(self, model_dir_keys):
        return list(self._model_version_inventory(model_dir_keys)["all"])

    def _model_version_option_label(self, version, installed):
        if installed:
            return f"{version} (installed)"
        return f"{version} (available)"

    def _ai_version_options(self, model_dir_keys, current_version="latest"):
        options = [["Latest (auto)", "latest"]]
        inventory = self._model_version_inventory(model_dir_keys)
        versions = inventory["all"]
        installed_versions = set(inventory["local"])

        for version in versions:
            if version != "latest":
                options.append([
                    self._model_version_option_label(version, version in installed_versions),
                    version,
                ])

        current_value = str(current_version or "latest")
        if current_value != "latest" and all(value != current_value for _, value in options):
            options.append([current_value, current_value])

        return options

    def _stored_ai_version(self):
        setting_key = self._version_setting_key()
        stored_value = str(self.settings.get(setting_key, "") or "").strip()
        if stored_value:
            return stored_value

        if setting_key == "ai_version":
            return "latest"

        legacy_value = str(self.settings.get("ai_version", "") or "").strip()
        if not legacy_value:
            return "latest"
        if legacy_value == "latest":
            return legacy_value

        if legacy_value in self._available_model_versions(self._inference_model_dir_keys()):
            return legacy_value
        return "latest"

    def _ai_version_setting_params(self):
        return [
            {
                "id": "background_ai_version",
                "type": "choice",
                "label": "Background Model Version",
                "default": "latest",
                "group": "Inference",
                "tooltip": "Default model version for GraXpert background extraction.",
                "options": self._ai_version_options(["bge_ai_models_dir"]),
            },
            {
                "id": "denoise_ai_version",
                "type": "choice",
                "label": "Denoise Model Version",
                "default": "latest",
                "group": "Inference",
                "tooltip": "Default model version for GraXpert denoise.",
                "options": self._ai_version_options(["denoise_ai_models_dir"]),
            },
            {
                "id": "deconvolution_ai_version",
                "type": "choice",
                "label": "Deconvolution Model Version",
                "default": "latest",
                "group": "Inference",
                "tooltip": "Default model version for GraXpert deconvolution.",
                "options": self._ai_version_options([
                    "deconvolution_object_ai_models_dir",
                    "deconvolution_stars_ai_models_dir",
                ]),
            },
        ]

    def get_settings_params(self):
        return [
            {
                "id": "gpu_enabled",
                "type": "bool",
                "label": "GPU Acceleration",
                "default": True,
                "group": "Inference",
                "tooltip": "Use GPU acceleration when the GraXpert runtime can provide it.",
            },
            *self._ai_version_setting_params(),
            {
                "id": "default_batch_size",
                "type": "int",
                "label": "Default Batch Size",
                "default": 4,
                "min": 1,
                "max": 32,
                "group": "Inference",
                "tooltip": "Number of tiles to process in parallel.",
            },
        ]

    def _meta_params(self):
        return [
            ui.process_window_meta(
                size=self.window_size,
                fixed_size=True,
                target_selector=True,
                target_channel_filter=[1, 3],
            )
        ]

    def _inference_params(self):
        selected_version = self._stored_ai_version()
        return [
            {"id": "inference", "type": "section", "label": "Inference"},
            {
                "id": "ai_version",
                "type": "choice",
                "label": "AI Model Version",
                "default": selected_version,
                "tooltip": "Override the saved GraXpert model version for this run. Use 'latest' to resolve the newest available model.",
                "options": self._ai_version_options(self._inference_model_dir_keys(), selected_version),
            },
            {
                "id": "gpu_enabled",
                "type": "bool",
                "label": "GPU Acceleration",
                "default": bool(self.settings.get("gpu_enabled", True)),
                "tooltip": "Override the saved GPU acceleration preference for this run.",
            },
        ]

    def _import_graxpert(self):
        try:
            from graxpert import ai_model_handling, s3_secrets
            from graxpert.ai_model_handling import (
                ai_model_path_from_version,
                bge_ai_models_dir,
                deconvolution_object_ai_models_dir,
                deconvolution_stars_ai_models_dir,
                denoise_ai_models_dir,
                download_version,
                list_remote_versions,
                latest_version,
            )
        except Exception as exc:
            raise RuntimeError(
                "The GraXpert Python package is not available in this extension environment yet. "
                "Provision the GraXpert runtime dependencies before launching these processes."
            ) from exc

        self._patch_ai_model_handling(ai_model_handling)

        return {
            "ai_model_handling": ai_model_handling,
            "ai_model_path_from_version": ai_model_path_from_version,
            "bge_ai_models_dir": bge_ai_models_dir,
            "deconvolution_object_ai_models_dir": deconvolution_object_ai_models_dir,
            "deconvolution_stars_ai_models_dir": deconvolution_stars_ai_models_dir,
            "denoise_ai_models_dir": denoise_ai_models_dir,
            "download_version": download_version,
            "list_remote_versions": list_remote_versions,
            "latest_version": latest_version,
            "s3_secrets": s3_secrets,
        }

    def _clear_progress_value(self, progress):
        try:
            progress.set_value(float("nan"))
        except Exception:
            return

    def _download_model_version(self,
                                imported,
                                model_dir,
                                bucket_name,
                                target_version,
                                progress):
        try:
            from minio import Minio
        except Exception as exc:
            raise RuntimeError("GraXpert model downloads require the Minio client package.") from exc

        remote_version = None
        try:
            remote_versions = imported["list_remote_versions"](bucket_name)
        except Exception:
            remote_versions = []

        for candidate in remote_versions or []:
            if str((candidate or {}).get("version", "")) == str(target_version):
                remote_version = candidate
                break

        if not remote_version:
            raise RuntimeError(f"GraXpert could not find remote model version '{target_version}'.")

        remote_bucket = str(remote_version.get("bucket") or bucket_name)
        remote_object = str(remote_version.get("object") or "")
        if not remote_object:
            raise RuntimeError(
                f"GraXpert remote model metadata for '{target_version}' is missing an object name."
            )

        endpoint = getattr(imported["s3_secrets"], "endpoint", None)
        access_key = getattr(imported["s3_secrets"], "ro_access_key", None)
        secret_key = getattr(imported["s3_secrets"], "ro_secret_key", None)
        if not endpoint or not access_key or not secret_key:
            raise RuntimeError("GraXpert model download credentials are unavailable.")

        client = Minio(endpoint, access_key, secret_key)
        model_dir_path = pathlib.Path(model_dir) / str(target_version)
        model_dir_path.mkdir(parents=True, exist_ok=True)
        model_path = model_dir_path / "model.onnx"
        model_zip_path = model_dir_path / "model.zip"
        response = None
        afternight.log_info(
            f"GraXpert: downloading AI model '{target_version}' from bucket '{remote_bucket}'.",
            component=self.component,
        )

        try:
            total_bytes = 0
            try:
                stat = client.stat_object(remote_bucket, remote_object)
                total_bytes = max(0, int(getattr(stat, "size", 0) or 0))
            except Exception:
                total_bytes = 0

            response = client.get_object(remote_bucket, remote_object)
            progress.set_text(f"Downloading GraXpert model {target_version}...")
            progress.set_value(0.0)

            downloaded_bytes = 0
            with model_zip_path.open("wb") as output_stream:
                for chunk in response.stream(amt=1024 * 1024):
                    if not chunk:
                        continue

                    output_stream.write(chunk)
                    downloaded_bytes += len(chunk)

                    if progress.is_cancelled():
                        raise RuntimeError("GraXpert model download was cancelled.")

                    if total_bytes > 0:
                        progress.set_value((downloaded_bytes * 100.0) / total_bytes)

            with zipfile.ZipFile(model_zip_path, "r") as archive:
                archive.extractall(model_dir_path)

            if not model_path.exists():
                raise RuntimeError(
                    f"Could not find GraXpert model payload after extracting {model_zip_path}."
                )
        except Exception:
            shutil.rmtree(model_dir_path, ignore_errors=True)
            raise
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
                try:
                    response.release_conn()
                except Exception:
                    pass
            try:
                if model_zip_path.exists():
                    model_zip_path.unlink()
            except Exception:
                pass

        progress.set_value(100.0)
        self._clear_progress_value(progress)
        afternight.log_info(
            f"GraXpert: AI model '{target_version}' is installed at {model_path}.",
            component=self.component,
        )

    def _resolve_model_path(self, model_dir_key, bucket_name_attr, progress, params=None):
        imported = self._import_graxpert()
        model_dir = imported[model_dir_key]
        bucket_name = getattr(imported["s3_secrets"], bucket_name_attr)
        requested_version = str(
            (params or {}).get("ai_version", self._stored_ai_version())
            or "latest"
        )
        target_version = requested_version
        if requested_version == "latest":
            target_version = imported["latest_version"](model_dir, bucket_name)
        if not target_version:
            raise RuntimeError("GraXpert could not resolve an AI model version.")

        model_path = imported["ai_model_path_from_version"](model_dir, target_version)
        if model_path and pathlib.Path(model_path).exists():
            afternight.log_info(
                f"GraXpert: found installed AI model '{target_version}' at {model_path}.",
                component=self.component,
            )
            return model_path, target_version

        self._download_model_version(
            imported,
            model_dir,
            bucket_name,
            target_version,
            progress,
        )
        model_path = imported["ai_model_path_from_version"](model_dir, target_version)
        if not model_path or not pathlib.Path(model_path).exists():
            raise RuntimeError(f"GraXpert model '{target_version}' is not available after download.")
        return model_path, target_version

    def _source_array(self, src_image):
        try:
            import numpy as np
        except Exception as exc:
            raise RuntimeError("NumPy is required for GraXpert extensions.") from exc

        array = np.array(src_image.to_numpy(), dtype=np.float32, copy=True)
        if array.ndim == 2:
            return np.expand_dims(array, axis=-1)
        if array.ndim != 3 or array.shape[2] not in (1, 3):
            raise RuntimeError(
                f"GraXpert expects mono or RGB images, got array shape {array.shape}."
            )
        return array

    def _batch_size(self, params):
        value = params.get("batch_size", self.settings.get("default_batch_size", 4))
        return max(1, min(32, int(value)))

    def _gpu_enabled(self, params=None):
        return bool((params or {}).get("gpu_enabled", self.settings.get("gpu_enabled", True)))

    def _log_model_selection(self, operation_name, target_version, model_path, gpu_enabled):
        afternight.log_info(
            f"GraXpert {operation_name}: using AI model '{target_version}' from {model_path}. "
            f"GPU acceleration {'enabled' if gpu_enabled else 'disabled'} for this run.",
            component=self.component,
        )

    def _preload_onnxruntime_gpu_runtime(self, ort, operation_name):
        cached_result = getattr(self, "_onnxruntime_gpu_runtime_ready", None)
        if cached_result is not None:
            return bool(cached_result)

        if not hasattr(ort, "preload_dlls"):
            self._onnxruntime_gpu_runtime_ready = False
            return False

        try:
            ort.preload_dlls(cuda=True, cudnn=True, directory="")
        except Exception as exc:
            afternight.log_warning(
                f"GraXpert {operation_name}: could not preload CUDA/cuDNN runtime "
                "libraries from NVIDIA site-packages/default loader paths. "
                f"GPU session creation may fall back to CPU ({exc}).",
                component=self.component,
            )
            self._onnxruntime_gpu_runtime_ready = False
            return False

        self._onnxruntime_gpu_runtime_ready = True
        return True

    def _log_inference_backend(self, operation_name, gpu_enabled):
        providers = []
        try:
            import onnxruntime as ort

            if gpu_enabled:
                self._preload_onnxruntime_gpu_runtime(ort, operation_name)

            providers = list(ort.get_available_providers())
        except Exception as exc:
            if gpu_enabled:
                afternight.log_warning(
                    f"GraXpert {operation_name}: GPU acceleration was requested, but "
                    "onnxruntime provider discovery is unavailable in this environment. "
                    f"Provider diagnostics could not be collected ({exc}).",
                    component=self.component,
                )
            else:
                afternight.log_info(
                    f"GraXpert {operation_name}: GPU acceleration disabled for this run; "
                    "provider discovery unavailable.",
                    component=self.component,
                )
            return

        provider_text = ", ".join(providers) if providers else "none"
        if not gpu_enabled:
            afternight.log_info(
                f"GraXpert {operation_name}: GPU acceleration disabled for this run. "
                f"Available ONNX providers: {provider_text}.",
                component=self.component,
            )
            return

        if "CUDAExecutionProvider" in providers:
            afternight.log_info(
                f"GraXpert {operation_name}: requesting GPU acceleration with "
                f"CUDAExecutionProvider available. Available ONNX providers: {provider_text}.",
                component=self.component,
            )
            return

        afternight.log_warning(
            f"GraXpert {operation_name}: GPU acceleration was requested, but "
            "CUDAExecutionProvider is unavailable. CPU fallback is expected if the "
            f"GraXpert runtime proceeds. Available ONNX providers: {provider_text}.",
            component=self.component,
        )


class GraXpertBackgroundExtension(_GraXpertBase):
    process_name = "Background Extraction"
    process_subtitle = "AI background model generation and correction"

    def _inference_model_dir_keys(self):
        return ["bge_ai_models_dir"]

    def _version_setting_key(self):
        return "background_ai_version"

    def get_params(self):
        return self._meta_params() + [
            {"id": "general", "type": "section", "label": "Background Extraction"},
            {
                "id": "correction_mode",
                "type": "choice",
                "label": "Correction Mode",
                "default": "Subtraction",
                "options": [
                    ["Subtraction", "Subtraction"],
                    ["Division", "Division"],
                ],
            },
            {
                "id": "smoothing",
                "type": "float",
                "label": "Smoothing",
                "default": 0.0,
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
            },
            {
                "id": "output_background_model",
                "type": "bool",
                "label": "Generate Background Model Image",
                "default": False,
                "tooltip": "Save the generated background model artifact and open it in the main UI.",
            },
        ] + self._inference_params()

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None,
                output_masks=None):
        del masks, weights, output_masks
        progress.set_text("Running GraXpert AI Background Extraction...")

        model_path, target_version = self._resolve_model_path(
            "bge_ai_models_dir",
            "bge_bucket_name",
            progress,
            params,
        )
        progress_adapter = _ProgressAdapter(progress)
        gpu_enabled = self._gpu_enabled(params)
        correction_mode = str(params.get("correction_mode", "Subtraction"))
        smoothing = float(params.get("smoothing", 0.0))
        afternight.log_info(
            "GraXpert background extraction: "
            f"correction={correction_mode}, smoothing={smoothing:.3f}, "
            f"background artifact={'enabled' if bool(params.get('output_background_model', False)) else 'disabled'}.",
            component=self.component,
        )
        progress.set_text(f"Using GraXpert model {target_version} for background extraction...")
        self._log_model_selection("background extraction", target_version, model_path, gpu_enabled)
        self._log_inference_backend("background extraction", gpu_enabled)

        try:
            import numpy as np
            from graxpert.background_extraction import extract_background
        except Exception as exc:
            raise RuntimeError("GraXpert background extraction dependencies are unavailable.") from exc

        source_array = self._source_array(src_image)
        background_model = extract_background(
            source_array,
            np.zeros((0, 2), dtype=np.int32),
            "AI",
            float(params.get("smoothing", 0.0)),
            1,
            25,
            "thin_plate",
            3,
            correction_mode,
            model_path,
            progress=progress_adapter,
            ai_gpu_acceleration=gpu_enabled,
        )
        result_image = source_array
        dst_image.from_numpy(result_image)
        afternight.log_info(
            "GraXpert background extraction: correction image copied to destination.",
            component=self.component,
        )

        if bool(params.get("output_background_model", False)):
            artifacts_dir = afternight.session_paths().artifacts_dir()
            if artifacts_dir:
                background_image = afternight.core.from_numpy(
                    background_model,
                    metadata=src_image.metadata,
                )
                artifact_path = pathlib.Path(artifacts_dir) / "graxpert_background_model.fits"
                afternight.io.save(
                    background_image,
                    artifact_path,
                )
                view_name = getattr(target, "view_name", "") or "Image"
                ui.open_image(
                    background_image,
                    title=f"{view_name} - GraXpert Background Model",
                )
                afternight.log_info(
                    f"Saved GraXpert background model artifact to {artifact_path}",
                    component=self.component,
                )


class GraXpertDenoiseExtension(_GraXpertBase):
    process_name = "Denoise"
    process_subtitle = "AI noise reduction"

    def _inference_model_dir_keys(self):
        return ["denoise_ai_models_dir"]

    def _version_setting_key(self):
        return "denoise_ai_version"

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
                "id": "batch_size",
                "type": "int",
                "label": "Batch Size",
                "default": int(self.settings.get("default_batch_size", 4)),
                "min": 1,
                "max": 32,
            },
        ] + self._inference_params()

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None,
                output_masks=None):
        del target, masks, weights, output_masks
        progress.set_text("Running GraXpert AI Denoise...")

        model_path, target_version = self._resolve_model_path(
            "denoise_ai_models_dir",
            "denoise_bucket_name",
            progress,
            params,
        )
        progress_adapter = _ProgressAdapter(progress)
        gpu_enabled = self._gpu_enabled(params)
        strength = float(params.get("strength", 0.9))
        batch_size = self._batch_size(params)
        afternight.log_info(
            f"GraXpert denoise: strength={strength:.3f}, batch_size={batch_size}.",
            component=self.component,
        )
        progress.set_text(f"Using GraXpert model {target_version} for denoise...")
        self._log_model_selection("denoise", target_version, model_path, gpu_enabled)
        self._log_inference_backend("denoise", gpu_enabled)

        try:
            from graxpert.denoising import denoise
        except Exception as exc:
            raise RuntimeError("GraXpert denoise dependencies are unavailable.") from exc

        result = denoise(
            self._source_array(src_image),
            model_path,
            strength,
            batch_size=batch_size,
            progress=progress_adapter,
            ai_gpu_acceleration=gpu_enabled,
        )
        if result is None:
            raise RuntimeError("GraXpert denoise did not return an output image.")
        dst_image.from_numpy(result)
        afternight.log_info("GraXpert denoise: output image written.", component=self.component)


class GraXpertDeconvolutionExtension(_GraXpertBase):
    window_size = (600, 500)
    process_name = "Deconvolution"
    process_subtitle = "AI object and stellar deconvolution"

    def _inference_model_dir_keys(self):
        return [
            "deconvolution_object_ai_models_dir",
            "deconvolution_stars_ai_models_dir",
        ]

    def _version_setting_key(self):
        return "deconvolution_ai_version"

    def get_params(self):
        return self._meta_params() + [
            {"id": "general", "type": "section", "label": "Deconvolution"},
            {
                "id": "method",
                "type": "choice",
                "label": "Method",
                "default": "object_only",
                "options": [
                    ["Object-Only", "object_only"],
                    ["Stars-Only", "stars_only"],
                ],
            },
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
                "id": "batch_size",
                "type": "int",
                "label": "Batch Size",
                "default": int(self.settings.get("default_batch_size", 4)),
                "min": 1,
                "max": 32,
            },
            {
                "id": "auto_detect_fwhm",
                "type": "bool",
                "label": "Auto Detect FWHM",
                "default": True,
            },
            {
                "id": "fwhm",
                "type": "float",
                "label": "FWHM",
                "default": 3.0,
                "min": 0.5,
                "max": 20.0,
                "step": 0.1,
                "enabled_when": "auto_detect_fwhm == false",
            },
        ] + self._inference_params()

    def execute(self, target, src_image, dst_image, params, progress, masks=None, weights=None,
                output_masks=None):
        del target, masks, weights, output_masks
        progress.set_text("Running GraXpert AI Deconvolution...")

        method = str(params.get("method", "object_only"))
        model_dir_key = "deconvolution_object_ai_models_dir"
        bucket_name_attr = "deconvolution_object_bucket_name"
        if method == "stars_only":
            model_dir_key = "deconvolution_stars_ai_models_dir"
            bucket_name_attr = "deconvolution_stars_bucket_name"

        model_path, target_version = self._resolve_model_path(
            model_dir_key,
            bucket_name_attr,
            progress,
            params,
        )
        progress_adapter = _ProgressAdapter(progress)
        gpu_enabled = self._gpu_enabled(params)
        strength = float(params.get("strength", 0.9))
        batch_size = self._batch_size(params)
        afternight.log_info(
            f"GraXpert deconvolution: method={method}, strength={strength:.3f}, "
            f"batch_size={batch_size}, auto_fwhm={'enabled' if bool(params.get('auto_detect_fwhm', True)) else 'disabled'}.",
            component=self.component,
        )
        progress.set_text(f"Using GraXpert model {target_version} for deconvolution...")
        self._log_model_selection("deconvolution", target_version, model_path, gpu_enabled)
        self._log_inference_backend("deconvolution", gpu_enabled)

        try:
            from graxpert.deconvolution import deconvolve
        except Exception as exc:
            raise RuntimeError("GraXpert deconvolution dependencies are unavailable.") from exc

        fwhm = float(params.get("fwhm", 3.0))
        if bool(params.get("auto_detect_fwhm", True)):
            detected_fwhm = 0.0
            try:
                detected_fwhm = float(afternight.core.detect_fwhm(src_image))
            except Exception as exc:
                afternight.log_warning(
                    f"GraXpert auto-detect FWHM failed; falling back to the current FWHM value ({exc}).",
                    component=self.component,
                )

            if detected_fwhm > 0.0:
                fwhm = detected_fwhm
                afternight.log_info(
                    f"GraXpert auto-detected FWHM {fwhm:.3f} px using AfterNightEngine star profiling.",
                    component=self.component,
                )
            else:
                afternight.log_warning(
                    "GraXpert auto-detect FWHM did not find enough valid stars; "
                    "falling back to the current FWHM value.",
                    component=self.component,
                )

        result = deconvolve(
            self._source_array(src_image),
            model_path,
            strength,
            fwhm,
            batch_size=batch_size,
            progress=progress_adapter,
            ai_gpu_acceleration=gpu_enabled,
        )
        if result is None:
            raise RuntimeError("GraXpert deconvolution did not return an output image.")
        dst_image.from_numpy(result)
        afternight.log_info(
            f"GraXpert deconvolution: output image written with FWHM {fwhm:.3f} px.",
            component=self.component,
        )

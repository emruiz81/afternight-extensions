import fnmatch
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


SUPPORTED_RUNTIME_TARGETS = (
    "linux-clang-x86_64",
    "windows-msvc-x86_64",
)

SCHEMA_VERSION = 1
PACKAGE_FORMAT_VERSION = 1
PROTOCOL_VERSION = 1
SDK_VERSION = 1
DEFAULT_SDK_BACKEND = "runtime"
DEFAULT_SIGNATURE_STATE = "unsigned"

EXCLUDED_NAMES = {
    ".DS_Store",
    "Thumbs.db",
    "extension_package_receipt.json",
}

EXCLUDED_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.metadata.json",
)


class PackageToolError(RuntimeError):
    """Raised when repository package tooling rejects package metadata."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def build_package(package_dir, output_dir, compression_level=10, runtime_targets=None, asset_name=None):
    package_dir = Path(package_dir)
    output_dir = Path(output_dir)
    manifest = load_valid_manifest(package_dir)

    targets = _normalize_runtime_targets(
        runtime_targets if runtime_targets is not None else manifest.get("runtime_targets"),
        allow_empty=False,
    )
    extension_id = manifest["id"]
    version = manifest["version"]
    if asset_name is None:
        asset_name = f"{extension_id}-{version}-{_asset_target_slug(targets)}.tar.zst"
    _validate_asset_name(asset_name)

    level = _normalize_compression_level(compression_level)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / asset_name

    with tempfile.TemporaryDirectory() as temp:
        tar_path = Path(temp) / f"{asset_name[:-4]}.tar"
        _write_deterministic_tar(package_dir, tar_path, extension_id)
        _compress_with_zstd(tar_path, archive_path, level)

    package_hash = "sha256:" + sha256_file(archive_path)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "package_id": extension_id,
        "version": version,
        "name": asset_name,
        "path": archive_path.name,
        "package_hash": package_hash,
        "sha256": package_hash.removeprefix("sha256:"),
        "size_bytes": archive_path.stat().st_size,
        "runtime_targets": targets,
        "compression": "zstd",
        "compression_level": level,
    }
    write_json(_metadata_path(archive_path), metadata)
    return metadata


def generate_index(
    packages_root,
    assets_dir,
    repository="afternight-extensions",
    updated_at=None,
    base_url="",
    official=True,
):
    packages_root = Path(packages_root)
    assets_dir = Path(assets_dir)
    if updated_at is None:
        raise PackageToolError("updated_at is required for deterministic index generation")

    packages = []
    for package_source in sorted(packages_root.glob("*/package")):
        if (package_source / "extension.json").is_file():
            if not is_package_published(package_source.parent):
                continue
            packages.append(_generate_package_index_entry(package_source, assets_dir, base_url))

    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "official": bool(official),
        "updated_at": updated_at,
        "extensions": packages,
    }


def load_valid_manifest(package_dir):
    package_dir = Path(package_dir)
    manifest_path = package_dir / "extension.json"
    if not manifest_path.is_file():
        raise PackageToolError(f"missing manifest: {manifest_path}")

    manifest = read_json(manifest_path)
    required_strings = (
        "id",
        "name",
        "version",
        "summary",
        "description",
        "author",
        "license",
        "publisher_id",
        "type",
        "entry_point",
        "category",
        "launch_mode",
    )
    for key in required_strings:
        _require_string(manifest, key, manifest_path)

    for key, expected in (
        ("package_format_version", PACKAGE_FORMAT_VERSION),
        ("protocol_version", PROTOCOL_VERSION),
        ("sdk_version", SDK_VERSION),
    ):
        value = manifest.get(key)
        if not isinstance(value, int) or value != expected:
            raise PackageToolError(f"{manifest_path}: {key} must be integer {expected}")

    if manifest["type"] != "python":
        raise PackageToolError(f"{manifest_path}: only python extension packages are supported")
    if manifest["launch_mode"] not in ("single_image", "workflow"):
        raise PackageToolError(f"{manifest_path}: launch_mode must be single_image or workflow")
    if manifest.get("sdk_backend", DEFAULT_SDK_BACKEND) not in ("runtime", "rpc"):
        raise PackageToolError(f"{manifest_path}: sdk_backend must be runtime or rpc")

    _validate_identifier(manifest["id"], manifest_path)
    _validate_runtime_targets(manifest.get("runtime_targets"), manifest_path, allow_empty=True)
    _validate_tags(manifest.get("tags"), manifest_path)
    _validate_entry_point(package_dir, manifest["entry_point"])
    _validate_license(package_dir)
    return manifest


def is_package_published(package_root):
    repository_metadata_path = Path(package_root) / "repository.json"
    if not repository_metadata_path.is_file():
        return True
    repository_metadata = read_json(repository_metadata_path)
    return repository_metadata.get("publish", True) is not False


def _generate_package_index_entry(package_source, assets_dir, base_url):
    manifest = load_valid_manifest(package_source)
    package_root = package_source.parent
    repository_metadata_path = package_root / "repository.json"
    if not repository_metadata_path.is_file():
        raise PackageToolError(f"missing repository release metadata: {repository_metadata_path}")

    repository_metadata = read_json(repository_metadata_path)
    releases_metadata = repository_metadata.get("releases")
    if not isinstance(releases_metadata, list) or not releases_metadata:
        raise PackageToolError(f"{repository_metadata_path}: releases must be a non-empty array")

    all_assets = _load_asset_metadata(assets_dir)
    assets_by_version = {}
    for asset in all_assets:
        if asset.get("package_id") == manifest["id"]:
            assets_by_version.setdefault(asset.get("version"), []).append(asset)

    if not assets_by_version:
        raise PackageToolError(f"no built assets found for {manifest['id']} in {assets_dir}")

    releases = []
    for release_metadata in releases_metadata:
        release = _generate_release_entry(
            manifest,
            release_metadata,
            assets_by_version,
            repository_metadata_path,
            base_url,
        )
        releases.append(release)

    latest_version = repository_metadata.get("latest_version", manifest["version"])
    if not isinstance(latest_version, str) or not latest_version:
        raise PackageToolError(f"{repository_metadata_path}: latest_version must be a non-empty string")
    if latest_version not in {release["version"] for release in releases}:
        raise PackageToolError(
            f"{repository_metadata_path}: latest_version {latest_version} has no matching release"
        )

    package = {
        "id": manifest["id"],
        "name": manifest["name"],
        "summary": manifest["summary"],
        "description": manifest["description"],
        "author": manifest["author"],
        "license": manifest["license"],
        "publisher_id": manifest["publisher_id"],
        "latest_version": latest_version,
        "tags": manifest.get("tags", []),
        "releases": releases,
    }
    for key in ("homepage_url", "repository_url", "support_url", "icon_url"):
        if manifest.get(key):
            package[key] = manifest[key]
    return package


def _generate_release_entry(manifest, release_metadata, assets_by_version, metadata_path, base_url):
    version = release_metadata.get("version")
    if not isinstance(version, str) or not version:
        raise PackageToolError(f"{metadata_path}: release.version must be a non-empty string")
    min_app_version = release_metadata.get("min_app_version")
    if not isinstance(min_app_version, str) or not min_app_version:
        raise PackageToolError(f"{metadata_path}: release {version} must declare min_app_version")

    matching_assets = sorted(assets_by_version.get(version, []), key=lambda asset: asset["name"])
    if not matching_assets:
        raise PackageToolError(f"{metadata_path}: release {version} has no built assets")

    release_targets = sorted(
        {target for asset in matching_assets for target in asset.get("runtime_targets", [])}
    )
    if not release_targets:
        release_targets = _normalize_runtime_targets(manifest.get("runtime_targets"), allow_empty=False)

    assets = []
    for asset in matching_assets:
        targets = _normalize_runtime_targets(asset.get("runtime_targets"), allow_empty=False)
        asset_entry = {
            "name": asset["name"],
            "download_url": _download_url(base_url, asset["name"]),
            "package_hash": asset["package_hash"],
            "signature_state": release_metadata.get("signature_state", DEFAULT_SIGNATURE_STATE),
            "runtime_targets": targets,
        }
        if release_metadata.get("signature_detail"):
            asset_entry["signature_detail"] = release_metadata["signature_detail"]
        assets.append(asset_entry)

    release = {
        "version": version,
        "min_app_version": min_app_version,
        "package_format_version": PACKAGE_FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "sdk_version": SDK_VERSION,
        "sdk_backend": manifest.get("sdk_backend", DEFAULT_SDK_BACKEND),
        "launch_mode": manifest["launch_mode"],
        "runtime_targets": release_targets,
        "assets": assets,
    }
    for key in ("changelog", "published_at"):
        if release_metadata.get(key):
            release[key] = release_metadata[key]
    return release


def _write_deterministic_tar(package_dir, tar_path, archive_root):
    paths = _collect_package_paths(package_dir)
    with tarfile.open(tar_path, "w", format=tarfile.PAX_FORMAT) as archive:
        root_info = tarfile.TarInfo(archive_root)
        root_info.type = tarfile.DIRTYPE
        root_info.mode = 0o755
        _apply_stable_tar_metadata(root_info)
        archive.addfile(root_info)

        for path in paths:
            relative = path.relative_to(package_dir).as_posix()
            archive_name = f"{archive_root}/{relative}"
            _validate_archive_path(archive_name)
            stat = path.stat()
            info = tarfile.TarInfo(archive_name)
            _apply_stable_tar_metadata(info)
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
            elif path.is_file():
                info.type = tarfile.REGTYPE
                info.mode = 0o755 if stat.st_mode & 0o111 else 0o644
                info.size = stat.st_size
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                raise PackageToolError(f"unsupported package entry type: {path}")


def _collect_package_paths(package_dir):
    paths = []
    for path in Path(package_dir).rglob("*"):
        if _should_skip(path):
            continue
        if path.is_symlink():
            raise PackageToolError(f"symlinks are not allowed in packages: {path}")
        if not path.is_dir() and not path.is_file():
            raise PackageToolError(f"unsupported package entry type: {path}")
        paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(package_dir).as_posix())


def _apply_stable_tar_metadata(info):
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""


def _compress_with_zstd(tar_path, archive_path, compression_level):
    if shutil.which("zstd") is None:
        raise PackageToolError("zstd executable is required to build package assets")
    result = subprocess.run(
        [
            "zstd",
            "-q",
            "-f",
            "--no-progress",
            "-T1",
            f"-{compression_level}",
            "-o",
            str(archive_path),
            str(tar_path),
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise PackageToolError(f"zstd compression failed: {result.stderr.strip()}")


def _load_asset_metadata(assets_dir):
    assets_dir = Path(assets_dir)
    if not assets_dir.is_dir():
        raise PackageToolError(f"assets directory does not exist: {assets_dir}")

    assets = []
    for metadata_path in sorted(assets_dir.glob("*.metadata.json")):
        asset = read_json(metadata_path)
        archive_path = assets_dir / asset.get("name", "")
        if not archive_path.is_file():
            raise PackageToolError(f"{metadata_path}: referenced archive is missing")
        actual_hash = "sha256:" + sha256_file(archive_path)
        if asset.get("package_hash") != actual_hash:
            raise PackageToolError(f"{metadata_path}: package_hash does not match compressed archive")
        _normalize_runtime_targets(asset.get("runtime_targets"), allow_empty=False)
        if asset.get("compression") != "zstd":
            raise PackageToolError(f"{metadata_path}: compression must be zstd")
        assets.append(asset)
    return assets


def _require_string(data, key, source):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PackageToolError(f"{source}: {key} must be a non-empty string")


def _validate_identifier(value, source):
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    if any(character not in allowed for character in value) or value[0] in "-_":
        raise PackageToolError(
            f"{source}: id must use lowercase letters, numbers, dashes, or underscores"
        )


def _validate_runtime_targets(value, source=None, allow_empty=False):
    if value is None:
        return [] if allow_empty else list(SUPPORTED_RUNTIME_TARGETS)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        location = f"{source}: " if source else ""
        raise PackageToolError(f"{location}runtime_targets must be an array of strings")
    return _normalize_runtime_targets(value, allow_empty=allow_empty)


def _normalize_runtime_targets(value, allow_empty):
    if value is None:
        value = []
    targets = sorted(dict.fromkeys(value))
    if not targets and not allow_empty:
        targets = list(SUPPORTED_RUNTIME_TARGETS)
    unknown = sorted(set(targets) - set(SUPPORTED_RUNTIME_TARGETS))
    if unknown:
        raise PackageToolError(f"unsupported runtime target(s): {', '.join(unknown)}")
    return targets


def _validate_tags(value, source):
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise PackageToolError(f"{source}: tags must be an array of strings")


def _validate_entry_point(package_dir, entry_point):
    if ":" in entry_point:
        module_name = entry_point.split(":", 1)[0]
    else:
        module_name = entry_point
    module_path = Path(*module_name.split("."))
    module_file = package_dir / module_path.with_suffix(".py")
    package_init = package_dir / module_path / "__init__.py"
    if not module_file.is_file() and not package_init.is_file():
        raise PackageToolError(
            f"{package_dir / 'extension.json'}: entry_point does not resolve to a package file"
        )


def _validate_license(package_dir):
    if not any((package_dir / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")):
        raise PackageToolError(f"{package_dir}: package-local LICENSE file is required")


def _should_skip(path):
    if any(part == "__pycache__" for part in path.parts):
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_PATTERNS)


def _validate_archive_path(path):
    pure = Path(path)
    parts = pure.parts
    if pure.is_absolute() or ".." in parts or not parts:
        raise PackageToolError(f"unsafe archive path: {path}")
    if any(not part for part in parts):
        raise PackageToolError(f"unsafe archive path: {path}")
    if "\\" in path or ":" in path:
        raise PackageToolError(f"unsafe archive path: {path}")


def _validate_asset_name(name):
    if not name.endswith(".tar.zst"):
        raise PackageToolError("asset name must end in .tar.zst")
    _validate_archive_path(name)
    if "/" in name:
        raise PackageToolError("asset name must not include directories")


def _normalize_compression_level(value):
    try:
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise PackageToolError("compression level must be an integer") from exc
    if level < 1 or level > 19:
        raise PackageToolError("compression level must be between 1 and 19")
    return level


def _asset_target_slug(targets):
    if targets == list(SUPPORTED_RUNTIME_TARGETS):
        return "all"
    if len(targets) == 1:
        return targets[0]
    digest = hashlib.sha256(",".join(targets).encode("utf-8")).hexdigest()[:8]
    return f"multi-{digest}"


def _metadata_path(archive_path):
    return Path(str(archive_path) + ".metadata.json")


def _download_url(base_url, asset_name):
    if not base_url:
        return asset_name
    return base_url.rstrip("/") + "/" + asset_name

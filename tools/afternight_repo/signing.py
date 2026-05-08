# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Ezequiel Ruiz

import base64
import binascii
import json
from pathlib import Path


SIGNATURE_PAYLOAD_VERSION = "afternight-extension-asset-signature-v1"
SIGNATURE_ALGORITHM = "ed25519"
SIGNATURE_STATE_VERIFIED = "verified"
SIGNING_SECRET_ENV = "AFTERNIGHT_EXTENSION_SIGNING_KEY_ED25519_SEED_B64"
ED25519_SEED_BYTES = 32
ED25519_PUBLIC_KEY_BYTES = 32
ED25519_SIGNATURE_BYTES = 64


class SigningError(RuntimeError):
    """Raised when extension asset signing metadata is invalid."""


def _require_clean_field(name, value):
    if not isinstance(value, str) or not value:
        raise SigningError(f"{name} must be a non-empty string")
    if "\n" in value or "\r" in value:
        raise SigningError(f"{name} must not contain newlines")
    return value


def _normalize_package_hash(value):
    value = _require_clean_field("package_hash", value).lower()
    if value.startswith("sha256:"):
        digest = value.removeprefix("sha256:")
    else:
        digest = value
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SigningError("package_hash must be a SHA-256 digest, optionally prefixed by sha256:")
    return "sha256:" + digest


def _normalize_runtime_targets(runtime_targets):
    if not isinstance(runtime_targets, list) or not all(isinstance(item, str) for item in runtime_targets):
        raise SigningError("runtime_targets must be an array of strings")
    targets = sorted(dict.fromkeys(runtime_targets))
    for target in targets:
        _require_clean_field("runtime_target", target)
    return targets


def canonical_asset_signature_payload(
    *,
    package_id,
    version,
    asset_name,
    package_hash,
    runtime_targets,
    signature_key_id,
    signature_algorithm=SIGNATURE_ALGORITHM,
):
    """Return the exact UTF-8 payload signed for one release asset."""

    package_id = _require_clean_field("package_id", package_id)
    version = _require_clean_field("version", version)
    asset_name = _require_clean_field("asset_name", asset_name)
    package_hash = _normalize_package_hash(package_hash)
    signature_algorithm = _require_clean_field("signature_algorithm", signature_algorithm)
    signature_key_id = _require_clean_field("signature_key_id", signature_key_id)
    runtime_targets_text = ",".join(_normalize_runtime_targets(runtime_targets))

    payload = "\n".join(
        (
            SIGNATURE_PAYLOAD_VERSION,
            f"package_id={package_id}",
            f"version={version}",
            f"asset_name={asset_name}",
            f"package_hash={package_hash}",
            f"runtime_targets={runtime_targets_text}",
            f"signature_algorithm={signature_algorithm}",
            f"signature_key_id={signature_key_id}",
        )
    )
    return payload.encode("utf-8")


def decode_base64_exact(value, expected_size, label):
    value = _require_clean_field(label, value)
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise SigningError(f"{label} must be base64") from exc
    if len(decoded) != expected_size:
        raise SigningError(f"{label} must decode to {expected_size} bytes")
    return decoded


def encode_base64(value):
    return base64.b64encode(value).decode("ascii")


def _load_nacl_signing():
    try:
        from nacl import exceptions, signing  # type: ignore
    except ImportError as exc:
        raise SigningError("PyNaCl is required for signing; install tools/signing/requirements.lock") from exc
    return signing, exceptions


def derive_public_key_base64(seed_base64):
    signing, _exceptions = _load_nacl_signing()
    seed = decode_base64_exact(seed_base64, ED25519_SEED_BYTES, "signing seed")
    signing_key = signing.SigningKey(seed)
    return encode_base64(bytes(signing_key.verify_key))


def sign_payload_base64(payload, seed_base64):
    signing, _exceptions = _load_nacl_signing()
    seed = decode_base64_exact(seed_base64, ED25519_SEED_BYTES, "signing seed")
    signing_key = signing.SigningKey(seed)
    return encode_base64(signing_key.sign(payload).signature)


def verify_payload_signature(payload, public_key_base64, signature_base64):
    signing, exceptions = _load_nacl_signing()
    public_key = decode_base64_exact(public_key_base64, ED25519_PUBLIC_KEY_BYTES, "public key")
    signature = decode_base64_exact(signature_base64, ED25519_SIGNATURE_BYTES, "signature")
    verify_key = signing.VerifyKey(public_key)
    try:
        verify_key.verify(payload, signature)
    except exceptions.BadSignatureError:
        return False
    return True


def load_public_keys(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    keys = data.get("keys")
    if not isinstance(keys, list):
        raise SigningError(f"{path}: keys must be an array")

    result = {}
    for item in keys:
        if not isinstance(item, dict):
            raise SigningError(f"{path}: each key entry must be an object")
        key_id = _require_clean_field("key_id", item.get("key_id"))
        public_key = item.get("public_key_base64", item.get("public_key"))
        decode_base64_exact(public_key, ED25519_PUBLIC_KEY_BYTES, f"public key for {key_id}")
        if key_id in result:
            raise SigningError(f"{path}: duplicate key_id {key_id}")
        result[key_id] = public_key
    return result


def signing_payload_for_metadata(metadata, signature_key_id):
    return canonical_asset_signature_payload(
        package_id=metadata.get("package_id"),
        version=metadata.get("version"),
        asset_name=metadata.get("name"),
        package_hash=metadata.get("package_hash"),
        runtime_targets=metadata.get("runtime_targets"),
        signature_key_id=signature_key_id,
    )


def signed_metadata(metadata, *, signature_key_id, seed_base64, public_key_base64, signature_detail=None):
    payload = signing_payload_for_metadata(metadata, signature_key_id)
    signature = sign_payload_base64(payload, seed_base64)
    if not verify_payload_signature(payload, public_key_base64, signature):
        raise SigningError("generated signature did not verify with the configured public key")

    result = dict(metadata)
    result["signature_state"] = SIGNATURE_STATE_VERIFIED
    result["signature_algorithm"] = SIGNATURE_ALGORITHM
    result["signature_key_id"] = signature_key_id
    result["signature"] = signature
    result["signature_detail"] = (
        signature_detail or f"Verified official AfterNight package signature (Ed25519 key {signature_key_id})."
    )
    return result

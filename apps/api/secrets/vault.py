"""Encrypted credential vault — Phase 2 of the SaaS roadmap.

Connector credentials (OAuth tokens, API keys, DSNs) must never sit in
`Source.config_jsonb` (which is returned by GET /sources) or in logs. They go
through this vault: a small seam with a pluggable backend.

  * FernetVault  — real AEAD encryption (`cryptography`); the PRODUCTION backend.
                   Selected when `cryptography` imports and `SECRETS_KEY` is set.
  * DevVault     — stdlib-only encrypt-then-MAC (HMAC-CTR keystream + HMAC tag).
                   A fallback so the seam works where the native crypto build is
                   unavailable (CI/sandbox). Authenticated, but NOT a substitute
                   for a real KMS — do not use it for production secrets.

Swap in AWS KMS / GCP KMS / Vault by adding one more backend class; nothing above
this file changes. The chosen backend is recorded per secret (`backend` column)
so a stored blob is always decryptable and auditable.
"""
from __future__ import annotations

import abc
import base64
import hashlib
import hmac
import json
import logging
import os

logger = logging.getLogger("company_brain.vault")


def _key32(secret: str) -> bytes:
    """Derive a 32-byte key from an arbitrary secret string."""
    return hashlib.sha256(secret.encode()).digest()


def _secret_material() -> str:
    # A real deploy sets SECRETS_KEY. In dev/test we derive a stable-but-local key
    # and warn loudly, so nobody ships secrets under the default.
    from apps.api.config import get_settings

    s = get_settings().secrets_key
    if s:
        return s
    logger.warning("SECRETS_KEY not set — using a NON-SECRET dev key. Set SECRETS_KEY in production.")
    return "company-brain-dev-key-do-not-use-in-prod"


class Vault(abc.ABC):
    backend: str = "base"

    @abc.abstractmethod
    def encrypt(self, data: dict) -> str:
        """Serialize + encrypt a secrets dict to an opaque token string."""

    @abc.abstractmethod
    def decrypt(self, token: str) -> dict:
        """Reverse of encrypt. Raises on tamper / wrong key."""


class FernetVault(Vault):
    backend = "fernet"

    def __init__(self, secret: str) -> None:
        from cryptography.fernet import Fernet

        # Fernet wants a urlsafe-b64 32-byte key; derive one from any secret string.
        self._f = Fernet(base64.urlsafe_b64encode(_key32(secret)))

    def encrypt(self, data: dict) -> str:
        return self._f.encrypt(json.dumps(data).encode()).decode()

    def decrypt(self, token: str) -> dict:
        return json.loads(self._f.decrypt(token.encode()).decode())


class DevVault(Vault):
    """stdlib encrypt-then-MAC. Authenticated; dev/test only (no native crypto)."""

    backend = "dev-hmac"

    def __init__(self, secret: str) -> None:
        self._key = _key32(secret)

    def _keystream(self, nonce: bytes, n: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < n:
            block = hmac.new(self._key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
            out.extend(block)
            counter += 1
        return bytes(out[:n])

    def encrypt(self, data: dict) -> str:
        pt = json.dumps(data).encode()
        nonce = os.urandom(16)
        ct = bytes(a ^ b for a, b in zip(pt, self._keystream(nonce, len(pt))))
        tag = hmac.new(self._key, nonce + ct, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(nonce + ct + tag).decode()

    def decrypt(self, token: str) -> dict:
        blob = base64.urlsafe_b64decode(token.encode())
        nonce, ct, tag = blob[:16], blob[16:-32], blob[-32:]
        expect = hmac.new(self._key, nonce + ct, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expect):
            raise ValueError("vault: authentication failed (tampered or wrong key)")
        pt = bytes(a ^ b for a, b in zip(ct, self._keystream(nonce, len(ct))))
        return json.loads(pt.decode())


_VAULT: Vault | None = None


def get_vault() -> Vault:
    """Return the process vault: Fernet if the native crypto build works, else the
    stdlib dev fallback. Cached. The native import can hard-fail in some sandboxes,
    so we catch BaseException (pyo3 panics aren't plain Exceptions)."""
    global _VAULT
    if _VAULT is not None:
        return _VAULT
    secret = _secret_material()
    try:
        _VAULT = FernetVault(secret)
    except BaseException as e:  # noqa: BLE001 - native crypto may panic, not just raise
        logger.warning("Fernet unavailable (%s) — falling back to stdlib DevVault.", type(e).__name__)
        _VAULT = DevVault(secret)
    return _VAULT

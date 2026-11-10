"""
control_center/crypto.py — token encryption at rest and token masking.

Bot tokens are secrets. Two storage strategies are supported:

``encrypted``
    The token is encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using a
    key that lives outside the database (``BODA_SECRET_KEY`` or the
    generated ``Data/.secret_key``). This is the mode used when the
    ``cryptography`` package is installed.

``env reference``
    When no encryption key or no ``cryptography`` installation is available,
    the token is **not** copied into the database. Only a reference to the
    ``.env`` variable and a masked hint are stored, and the real value is
    read from the environment at runtime.

The module never logs or returns a full token to the UI layer — only
:func:`mask_token` output is ever exposed.
"""

import os
import re

from . import config

# Prefix written in front of every encrypted blob so the format stays
# self-describing and can be migrated later without guessing.
_PREFIX = "enc:v1:"


class SecretBox:
    """Encrypts and decrypts short secrets using Fernet."""

    def __init__(self, key: str | None = None):
        self._fernet = None
        self.error = ""
        raw = key if key is not None else config.secret_key()
        if not raw:
            self.error = "no encryption key configured"
            return
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            self.error = "cryptography package is not installed"
            return
        try:
            self._fernet = Fernet(raw.encode("ascii") if isinstance(raw, str) else raw)
        except Exception as exc:
            self.error = f"invalid encryption key: {exc}"

    @property
    def available(self) -> bool:
        """True when encryption/decryption is possible."""
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a secret. Raises when encryption is unavailable."""
        if not self.available:
            raise RuntimeError(f"encryption unavailable: {self.error}")
        if plaintext is None:
            raise ValueError("nothing to encrypt")
        return _PREFIX + self._fernet.encrypt(str(plaintext).encode("utf-8")).decode("ascii")

    def decrypt(self, blob: str) -> str:
        """Decrypt a blob produced by :meth:`encrypt`. Raises on failure."""
        if not self.available:
            raise RuntimeError(f"encryption unavailable: {self.error}")
        if not blob or not blob.startswith(_PREFIX):
            raise ValueError("value is not an encrypted blob")
        token = blob[len(_PREFIX):]
        return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")

    def encrypt_or_none(self, plaintext: str):
        """Encrypt, returning ``None`` instead of raising when unavailable."""
        if not self.available or not plaintext:
            return None
        try:
            return self.encrypt(plaintext)
        except Exception:
            return None


_box = None


def get_secret_box() -> SecretBox:
    """Shared :class:`SecretBox` instance."""
    global _box
    if _box is None:
        _box = SecretBox()
    return _box


def reset_secret_box() -> None:
    """Drop the cached box — test helper."""
    global _box
    _box = None


def mask_token(token: str) -> str:
    """
    Mask a bot token for display.

    ``1234567890:AAF-fake_token_value_here`` becomes
    ``1234••••••••••••here`` — enough for a human to recognise which token
    is configured, useless to an attacker.
    """
    if not token:
        return ""
    token = str(token)
    if ":" in token:
        head, _, tail = token.partition(":")
        visible_head = head[:4]
        visible_tail = tail[-4:] if len(tail) >= 4 else tail
        return f"{visible_head}{'•' * 8}{visible_tail}"
    if len(token) <= 8:
        return "•" * 8
    return f"{token[:4]}{'•' * 8}{token[-4:]}"


def token_hint(token: str) -> str:
    """A short, non-reversible hint stored next to the encrypted blob."""
    if not token:
        return ""
    tail = str(token).split(":")[-1]
    return tail[-4:] if len(tail) >= 4 else ""


def read_env_token(bot_id: str) -> str:
    """
    Read a bot token from the environment.

    Mirrors the legacy lookup used by ``Bots_Folder/bot_base.get_token``:
    ``BOT_<ID>_TOKEN``.
    """
    key = f"BOT_{str(bot_id).upper().replace('BOT_', '')}_TOKEN"
    value = os.getenv(key, "").strip()
    if value and value != "ضع_التوكن_هنا":
        return value
    return ""


def env_var_name(bot_id: str) -> str:
    """Name of the environment variable that holds a bot's token."""
    return f"BOT_{str(bot_id).upper().replace('BOT_', '')}_TOKEN"


_VALID_TOKEN_RE = re.compile(r"^\d{5,}:[\w-]{20,}$")


def looks_like_token(value: str) -> bool:
    """Format check for a Telegram bot token (no network call)."""
    return bool(value) and bool(_VALID_TOKEN_RE.match(value.strip()))

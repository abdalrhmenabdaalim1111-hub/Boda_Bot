"""
control_center/config.py — paths and settings for the Control Center.

Single source of truth for every path the control plane touches. All paths
are overridable through environment variables so tests can run fully isolated
and Docker can mount volumes elsewhere.

Environment variables
---------------------
BODA_DB_PATH            path of the shared SQLite file (default Data/boda_bot.db)
BODA_SECRET_KEY        Fernet key used to encrypt bot tokens at rest
BODA_CC_HOST           bind address of the Control Center API
BODA_CC_PORT           port of the Control Center API
BODA_CC_LOG_TAIL       number of log lines kept in memory per bot
BODA_CC_AUTO_RESTART   default auto-restart policy for managed bots (1/0)
BODA_CC_BACKOFF_MAX    maximum auto-restart backoff in seconds
"""

import os
from pathlib import Path

from . import ROOT_DIR

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = ROOT_DIR
BOTS_DIR = BASE_DIR / "Bots_Folder"
DATA_DIR = BASE_DIR / "Data"
LOGS_DIR = BASE_DIR / "Logs"
BACKUPS_DIR = BASE_DIR / "Backups"
WEBROOT_DIR = BASE_DIR / "webroot"
WEBAPPS_DIR = BASE_DIR / "webapps"
TOOLS_DIR = BASE_DIR / "tools"
DOCS_DIR = BASE_DIR / "docs"
REGISTRY_PATH = BASE_DIR / "bots_registry.json"
ENV_FILE = BASE_DIR / ".env"
SECRET_KEY_FILE = DATA_DIR / ".secret_key"

for _d in (DATA_DIR, LOGS_DIR, BACKUPS_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def db_path() -> str:
    """Path of the shared SQLite database (same file the bots use)."""
    return os.getenv("BODA_DB_PATH", "") or str(DATA_DIR / "boda_bot.db")


def secret_key() -> str:
    """
    Fernet key for token encryption.

    Order of preference:
      1. ``BODA_SECRET_KEY`` environment variable
      2. a generated key persisted in ``Data/.secret_key`` (mode 0600)

    Returns an empty string when no key can be established — callers must
    treat that as "encryption unavailable" and fall back to the .env token
    store instead of failing hard.
    """
    env_key = os.getenv("BODA_SECRET_KEY", "").strip()
    if env_key:
        return env_key
    try:
        if SECRET_KEY_FILE.exists():
            stored = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored
    except OSError:
        pass
    return ""


def ensure_secret_key() -> str:
    """Return the encryption key, generating and persisting one when missing."""
    existing = secret_key()
    if existing:
        return existing
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return ""
    key = Fernet.generate_key().decode("ascii")
    try:
        SECRET_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_KEY_FILE.write_text(key, encoding="utf-8")
        try:
            os.chmod(SECRET_KEY_FILE, 0o600)
        except OSError:
            pass  # not supported on Windows
    except OSError:
        return ""
    return key


# ── Server ──────────────────────────────────────────────────────────────────
def api_host() -> str:
    return os.getenv("BODA_CC_HOST", "127.0.0.1").strip() or "127.0.0.1"


def api_port() -> int:
    try:
        return int(os.getenv("BODA_CC_PORT", "8080"))
    except ValueError:
        return 8080


# ── Supervisor ──────────────────────────────────────────────────────────────
def log_tail_size() -> int:
    """How many log lines are kept in memory per bot."""
    try:
        return max(100, int(os.getenv("BODA_CC_LOG_TAIL", "2000")))
    except ValueError:
        return 2000


def auto_restart_default() -> bool:
    return os.getenv("BODA_CC_AUTO_RESTART", "1").strip().lower() in ("1", "true", "yes", "on")


def backoff_max() -> int:
    """Upper bound of the auto-restart exponential backoff, in seconds."""
    try:
        return max(5, int(os.getenv("BODA_CC_BACKOFF_MAX", "300")))
    except ValueError:
        return 300


def backoff_base() -> int:
    """Initial auto-restart backoff, in seconds."""
    try:
        return max(1, int(os.getenv("BODA_CC_BACKOFF_BASE", "5")))
    except ValueError:
        return 5


# ── Security ────────────────────────────────────────────────────────────────
def api_server_key() -> str:
    """Legacy shared key of the existing API (kept for backward compatibility)."""
    return os.getenv("API_SERVER_KEY", "").strip()


def session_ttl_seconds() -> int:
    """Lifetime of a Control Center session token."""
    try:
        return max(300, int(os.getenv("BODA_CC_SESSION_TTL", "28800")))
    except ValueError:
        return 28800


def login_max_attempts() -> int:
    """Failed logins allowed per account before a temporary lockout."""
    try:
        return max(3, int(os.getenv("BODA_CC_LOGIN_MAX_ATTEMPTS", "5")))
    except ValueError:
        return 5


def login_lockout_seconds() -> int:
    try:
        return max(30, int(os.getenv("BODA_CC_LOGIN_LOCKOUT", "300")))
    except ValueError:
        return 300


# ── Ads ─────────────────────────────────────────────────────────────────────
def ad_allowed_domains() -> list:
    """
    Allow-list of domains an ad snippet is allowed to reference.

    Configurable through ``BODA_AD_ALLOWED_DOMAINS`` (comma separated).
    An empty list means "no domain restriction" — but the safety checks
    (eval / document.write / obfuscation) still apply.
    """
    raw = os.getenv("BODA_AD_ALLOWED_DOMAINS", "").strip()
    if not raw:
        return []
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def ad_max_size_bytes() -> int:
    """Maximum size of a single ad snippet."""
    try:
        return max(1024, int(os.getenv("BODA_AD_MAX_BYTES", "65536")))
    except ValueError:
        return 65536


# ── Revenue (optional, owner-supplied rates) ────────────────────────────────
def ad_cpm_rate() -> float:
    """Revenue per 1000 impressions in USD. 0 = revenue not modelled."""
    try:
        return max(0.0, float(os.getenv("BODA_AD_CPM", "0") or 0))
    except ValueError:
        return 0.0

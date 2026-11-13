"""
control_center/ — Boda Bot Control Center backend

A thin, dependency-light control plane that sits *on top of* the existing
Boda Bot System. It never replaces existing modules: it reuses the same
SQLite database, the same bot registry, the same ad manager and the same
logging infrastructure.

Layout:
    config.py      paths + env-driven settings (single source of truth)
    db.py          database access helpers (same file as the bots use)
    migrations.py  reversible, numbered schema migrations
    audit.py       audit log (who did what, when)
    crypto.py      token encryption at rest + masking
    supervisor.py  bot process supervisor (start/stop/restart/backoff)
    http.py        tiny router + OpenAPI document + SSE helpers
    api.py         the /api/v1 route table
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
BOTS_DIR = ROOT_DIR / "Bots_Folder"

# The bots import each other as top-level modules (``from database import ...``),
# so the Bots_Folder must be importable exactly like the legacy entry points do.
for _p in (str(ROOT_DIR), str(BOTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__all__ = ["ROOT_DIR", "BOTS_DIR"]
__version__ = "1.0.0"

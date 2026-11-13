"""
control_center/audit.py — the audit log.

Every state change performed through the Control Center is recorded here:
who did it, what they did, to which object, when, and with what payload.

The audit trail is append-only from the application's point of view — there
is deliberately no update or delete API, only a retention purge.
"""

import json
from datetime import datetime, timedelta

from .db import get_db


def _now() -> str:
    return datetime.now().isoformat()


def record(actor: str, action: str, target_type: str = "", target_id: str = "",
           details=None, ip: str = "") -> int:
    """
    Append an entry to the audit log.

    Args:
        actor:       who performed the action ("admin", "system", "cli", ...)
        action:      dotted action name ("bot.restart", "ad.assign", ...)
        target_type: kind of object ("bot", "ad", "user", ...)
        target_id:   identifier of the object
        details:     any JSON-serialisable payload
        ip:          caller IP when known

    Returns the id of the new row, or ``-1`` when the write failed.
    The function never raises — auditing must not break the operation it
    is auditing.
    """
    db = get_db()
    if db is None:
        return -1
    payload = None
    if details is not None:
        try:
            payload = json.dumps(details, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            payload = json.dumps({"repr": repr(details)[:500]}, ensure_ascii=False)
    try:
        with db._get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_log
                    (occurred_at, actor, action, target_type, target_id, details, ip)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_now(), str(actor or "system"), str(action or ""),
                 str(target_type or ""), str(target_id or ""), payload, str(ip or "")),
            )
            return int(cur.lastrowid)
    except Exception:
        return -1


def query(limit: int = 100, offset: int = 0, action: str = "",
          actor: str = "", target_id: str = "", since: str = "") -> list:
    """Return audit entries, newest first, with optional filters."""
    db = get_db()
    if db is None:
        return []
    clauses, params = [], []
    if action:
        clauses.append("action LIKE ?")
        params.append(f"%{action}%")
    if actor:
        clauses.append("actor = ?")
        params.append(actor)
    if target_id:
        clauses.append("target_id = ?")
        params.append(target_id)
    if since:
        clauses.append("occurred_at >= ?")
        params.append(since)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT id, occurred_at, actor, action, target_type, target_id,
                       details, ip
                FROM audit_log
                {where}
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, max(1, min(int(limit), 1000)), max(0, int(offset))),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def count(limit: int = 100, offset: int = 0, action: str = "",
          actor: str = "", target_id: str = "") -> int:
    """Total number of audit entries matching the same filters as :func:`query`."""
    db = get_db()
    if db is None:
        return 0
    clauses, params = [], []
    if action:
        clauses.append("action LIKE ?")
        params.append(f"%{action}%")
    if actor:
        clauses.append("actor = ?")
        params.append(actor)
    if target_id:
        clauses.append("target_id = ?")
        params.append(target_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        with db._get_conn() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM audit_log {where}", params
            ).fetchone()
        return int(row["c"]) if row else 0
    except Exception:
        return 0


def purge(older_than_days: int = 90) -> int:
    """Delete audit entries older than N days. Returns the number removed."""
    db = get_db()
    if db is None:
        return 0
    cutoff = (datetime.now() - timedelta(days=max(1, older_than_days))).isoformat()
    try:
        with db._get_conn() as conn:
            cur = conn.execute("DELETE FROM audit_log WHERE occurred_at < ?", (cutoff,))
            return int(cur.rowcount or 0)
    except Exception:
        return 0


def stats() -> dict:
    """Small summary used by the Overview page."""
    db = get_db()
    if db is None:
        return {"total": 0, "last_24h": 0, "by_action": {}, "by_actor": {}}
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        with db._get_conn() as conn:
            total = int(conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"])
            recent = int(conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log WHERE occurred_at >= ?",
                (cutoff,)).fetchone()["c"])
            by_action = conn.execute(
                "SELECT action, COUNT(*) AS c FROM audit_log "
                "GROUP BY action ORDER BY c DESC LIMIT 20").fetchall()
            by_actor = conn.execute(
                "SELECT actor, COUNT(*) AS c FROM audit_log "
                "GROUP BY actor ORDER BY c DESC LIMIT 20").fetchall()
        return {
            "total": total,
            "last_24h": recent,
            "by_action": {r["action"]: int(r["c"]) for r in by_action},
            "by_actor": {r["actor"]: int(r["c"]) for r in by_actor},
        }
    except Exception:
        return {"total": 0, "last_24h": 0, "by_action": {}, "by_actor": {}}

# -*- coding: utf-8 -*-
import os
import time
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pathlib import Path

from control_center.registry import discover, get_bot_info
from control_center.supervisor import BotSupervisor
from control_center import config

app = FastAPI(title="Boda Control API V2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supervisor = BotSupervisor(
    base_dir=config.BASE_DIR,
    registry_path=config.REGISTRY_PATH
)
supervisor.start_monitor()

# نظام كاش بسيط لتسريع الـ API
_STATUS_CACHE = {"data": [], "last_updated": 0}

@app.get("/")
async def root():
    return {"status": "online", "version": "2.0.0"}

@app.get("/api/v2/bots")
async def list_bots():
    """عرض قائمة بجميع البوتات مع كاش 5 ثوانٍ لتجنب بطء ويندوز."""
    now = time.time()
    if now - _STATUS_CACHE["last_updated"] > 5:
        bots = discover()
        status_list = supervisor.status()
        
        result = []
        for bot_id, info in bots.items():
            bot_status = next((s for s in status_list if s["bot_id"] == bot_id), {})
            result.append({
                "id": bot_id,
                "name": info.name,
                "category": info.category,
                "source": info.source,
                "running": bot_status.get("running", False),
                "pid": bot_status.get("pid", 0),
                "uptime": bot_status.get("uptime_seconds", 0),
                "restarts": bot_status.get("restarts", 0),
                "enabled": bot_status.get("enabled", True),
                "last_error": bot_status.get("last_error", "")
            })
        _STATUS_CACHE["data"] = result
        _STATUS_CACHE["last_updated"] = now
        
    return _STATUS_CACHE["data"]

@app.post("/api/v2/bots/{bot_id}/action")
async def control_bot(bot_id: str, action: str):
    # مسح الكاش فوراً عند تنفيذ أي أمر
    _STATUS_CACHE["last_updated"] = 0
    if action == "start": return supervisor.start(bot_id, force=True)
    elif action == "stop": return supervisor.stop(bot_id)
    elif action == "restart": return supervisor.restart(bot_id)
    return {"ok": False, "error": "unknown action"}

@app.get("/api/v2/bots/{bot_id}/logs")
async def get_bot_logs(bot_id: str, limit: int = 50):
    return {"bot_id": bot_id, "logs": supervisor.logs(bot_id=bot_id, limit=limit)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)

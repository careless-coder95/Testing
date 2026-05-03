"""
Stark Deploy Bot - JSON Database
"""
import json
import os
import asyncio
from typing import Any, Dict, List, Optional
from config import DB_PATH

_lock = asyncio.Lock()


def _ensure_db() -> Dict:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if not os.path.exists(DB_PATH):
        _write_raw({"sudo_users": [], "deployments": []})
    with open(DB_PATH, "r") as f:
        return json.load(f)


def _write_raw(data: Dict):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


async def _read() -> Dict:
    async with _lock:
        return _ensure_db()


async def _write(data: Dict):
    async with _lock:
        _write_raw(data)


# ─── Sudo Users ───────────────────────────────────────────────────────────────

async def get_sudo_users() -> List[int]:
    db = await _read()
    return db.get("sudo_users", [])


async def add_sudo_user(user_id: int) -> bool:
    db = await _read()
    if user_id not in db["sudo_users"]:
        db["sudo_users"].append(user_id)
        await _write(db)
        return True
    return False


async def remove_sudo_user(user_id: int) -> bool:
    db = await _read()
    if user_id in db["sudo_users"]:
        db["sudo_users"].remove(user_id)
        await _write(db)
        return True
    return False


# ─── Deployments ──────────────────────────────────────────────────────────────

async def get_deployments(user_id: Optional[int] = None) -> List[Dict]:
    db = await _read()
    deployments = db.get("deployments", [])
    if user_id is not None:
        deployments = [d for d in deployments if d["user_id"] == user_id]
    return deployments


async def get_deployment(user_id: int, project_name: str) -> Optional[Dict]:
    deployments = await get_deployments(user_id)
    for d in deployments:
        if d["project_name"] == project_name:
            return d
    return None


async def save_deployment(deployment: Dict) -> bool:
    db = await _read()
    # Remove existing entry if any
    db["deployments"] = [
        d for d in db["deployments"]
        if not (d["user_id"] == deployment["user_id"] and
                d["project_name"] == deployment["project_name"])
    ]
    db["deployments"].append(deployment)
    await _write(db)
    return True


async def delete_deployment(user_id: int, project_name: str) -> bool:
    db = await _read()
    before = len(db["deployments"])
    db["deployments"] = [
        d for d in db["deployments"]
        if not (d["user_id"] == user_id and d["project_name"] == project_name)
    ]
    if len(db["deployments"]) < before:
        await _write(db)
        return True
    return False


async def update_deployment_status(user_id: int, project_name: str, status: str):
    db = await _read()
    for d in db["deployments"]:
        if d["user_id"] == user_id and d["project_name"] == project_name:
            d["status"] = status
            break
    await _write(db)

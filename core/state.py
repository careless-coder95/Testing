"""
Stark Deploy Bot - Centralized State Manager
"""
from typing import Any, Dict, Optional

# ─── State Keys ───────────────────────────────────────────────────────────────
WAIT_REPO = "WAIT_REPO"
WAIT_NAME = "WAIT_NAME"
WAIT_ENV = "WAIT_ENV"
WAIT_CMD = "WAIT_CMD"

# In-memory state store: {user_id: {"step": str, "data": dict}}
_states: Dict[int, Dict[str, Any]] = {}


def get_state(user_id: int) -> Optional[Dict[str, Any]]:
    return _states.get(user_id)


def set_state(user_id: int, step: str, data: Optional[Dict] = None):
    _states[user_id] = {
        "step": step,
        "data": data or {}
    }


def update_data(user_id: int, key: str, value: Any):
    if user_id not in _states:
        _states[user_id] = {"step": "", "data": {}}
    _states[user_id]["data"][key] = value


def get_data(user_id: int, key: str, default: Any = None) -> Any:
    state = _states.get(user_id)
    if not state:
        return default
    return state["data"].get(key, default)


def clear_state(user_id: int):
    _states.pop(user_id, None)


def has_state(user_id: int) -> bool:
    return user_id in _states

"""
Stark Deploy Bot - Security Module
"""
import re
from typing import Tuple
from config import BLOCKED_PATTERNS, MAX_DEPLOYMENTS_PER_USER, OWNER_ID
from database.db import get_sudo_users, get_deployments


async def is_authorized(user_id: int) -> bool:
    """Check if user is owner or sudo user."""
    if user_id == OWNER_ID:
        return True
    sudo_users = await get_sudo_users()
    return user_id in sudo_users


async def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


async def can_deploy(user_id: int) -> Tuple[bool, str]:
    """Check if user hasn't exceeded deployment limit."""
    deployments = await get_deployments(user_id)
    active = [d for d in deployments if d.get("status") != "stopped"]
    if len(active) >= MAX_DEPLOYMENTS_PER_USER:
        return False, (
            f"❌ You've reached the max deployment limit "
            f"({MAX_DEPLOYMENTS_PER_USER} active projects).\n"
            f"Stop an existing project first."
        )
    return True, ""


def validate_repo_url(url: str) -> Tuple[bool, str]:
    """Validate GitHub repository URL format."""
    url = url.strip()
    pattern = r'^https://github\.com/[\w\-\.]+/[\w\-\.]+(?:\.git)?$'
    if not re.match(pattern, url):
        return False, (
            "❌ Invalid GitHub URL.\n"
            "Expected format: `https://github.com/username/repo`"
        )
    return True, url


def validate_project_name(name: str) -> Tuple[bool, str]:
    """Validate project name (alphanumeric + hyphens/underscores)."""
    name = name.strip()
    if not re.match(r'^[a-zA-Z0-9_\-]{2,32}$', name):
        return False, (
            "❌ Invalid project name.\n"
            "Use 2–32 characters: letters, numbers, `-`, `_` only."
        )
    return True, name


def sanitize_command(cmd: str, project_path: str) -> Tuple[bool, str]:
    """
    Validate and sanitize the run command.
    - Block dangerous patterns
    - Replace 'python' / 'python3' with venv path
    """
    cmd = cmd.strip()

    # Block dangerous patterns
    cmd_lower = cmd.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in cmd_lower:
            return False, f"❌ Blocked pattern detected: `{pattern}`"

    # Block shell operators
    shell_ops = [';', '&&', '||', '|', '>', '<', '`', '$()']
    for op in shell_ops:
        if op in cmd:
            return False, f"❌ Shell operator not allowed: `{op}`"

    # Must start with python / python3
    if not (cmd.startswith("python") or cmd.startswith("python3")):
        return False, "❌ Run command must start with `python` or `python3`."

    # Replace python/python3 with venv path
    venv_python = f"{project_path}/venv/bin/python"
    cmd = re.sub(r'^python3?', venv_python, cmd)

    return True, cmd

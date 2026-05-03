"""
Stark Deploy Bot - Utility Functions
"""
import asyncio
import logging
import os
from typing import Optional, Tuple
from config import LOG_LINES, DEPLOY_BASE_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("StarkBot")


def get_project_path(user_id: int, project_name: str) -> str:
    return os.path.join(DEPLOY_BASE_PATH, str(user_id), project_name)


def get_pm2_name(user_id: int, project_name: str) -> str:
    return f"stark_{user_id}_{project_name}"


async def run_command(
    cmd: str,
    cwd: Optional[str] = None,
    timeout: int = 120,
) -> Tuple[int, str, str]:
    """
    Run a shell command asynchronously.
    Returns (returncode, stdout, stderr).
    """
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return (
            proc.returncode or 0,
            stdout.decode(errors="replace").strip(),
            stderr.decode(errors="replace").strip(),
        )
    except asyncio.TimeoutError:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def tail_output(text: str, lines: int = LOG_LINES) -> str:
    """Return last N lines of text output."""
    all_lines = text.splitlines()
    return "\n".join(all_lines[-lines:])


def truncate(text: str, max_len: int = 3500) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n… (truncated)"

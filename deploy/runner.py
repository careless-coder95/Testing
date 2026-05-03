"""
Stark Deploy Bot - PM2 Process Runner
Handles start, stop, restart, logs via PM2.
"""
from typing import Tuple

from core.utils import run_command, logger, get_pm2_name, tail_output


async def pm2_start(
    user_id: int,
    project_name: str,
    command: str,
    project_path: str,
) -> Tuple[bool, str]:
    """
    Start a process using PM2.
    `command` should already have python replaced with venv/bin/python.
    """
    pm2_name = get_pm2_name(user_id, project_name)

    # Stop existing if running
    await pm2_stop(user_id, project_name)

    cmd = (
        f'pm2 start "{command}" '
        f'--name "{pm2_name}" '
        f'--cwd "{project_path}" '
        f'--no-autorestart'
    )
    logger.info(f"PM2 start: {cmd}")
    returncode, stdout, stderr = await run_command(cmd, timeout=30)

    if returncode != 0:
        return False, f"PM2 start failed:\n{stderr or stdout}"

    # Save PM2 state
    await run_command("pm2 save", timeout=15)

    return True, f"Process `{pm2_name}` started."


async def pm2_stop(user_id: int, project_name: str) -> Tuple[bool, str]:
    """Stop a PM2 process (silent fail if not running)."""
    pm2_name = get_pm2_name(user_id, project_name)
    returncode, stdout, stderr = await run_command(
        f'pm2 stop "{pm2_name}"', timeout=15
    )
    await run_command("pm2 save", timeout=15)
    if returncode != 0:
        return False, f"Could not stop `{pm2_name}`: {stderr or stdout}"
    return True, f"Process `{pm2_name}` stopped."


async def pm2_restart(user_id: int, project_name: str) -> Tuple[bool, str]:
    """Restart a PM2 process."""
    pm2_name = get_pm2_name(user_id, project_name)
    returncode, stdout, stderr = await run_command(
        f'pm2 restart "{pm2_name}"', timeout=15
    )
    if returncode != 0:
        return False, f"Could not restart `{pm2_name}`: {stderr or stdout}"
    return True, f"Process `{pm2_name}` restarted."


async def pm2_logs(user_id: int, project_name: str, lines: int = 50) -> str:
    """Fetch last N lines of PM2 logs."""
    pm2_name = get_pm2_name(user_id, project_name)
    returncode, stdout, stderr = await run_command(
        f'pm2 logs "{pm2_name}" --lines {lines} --nostream',
        timeout=15,
    )
    output = stdout or stderr
    if not output:
        return "📭 No logs available yet."
    return tail_output(output, lines)


async def pm2_status(user_id: int, project_name: str) -> str:
    """Get PM2 process status."""
    pm2_name = get_pm2_name(user_id, project_name)
    returncode, stdout, stderr = await run_command(
        f'pm2 show "{pm2_name}"', timeout=10
    )
    return stdout or stderr or "Status unavailable."


async def pm2_delete(user_id: int, project_name: str):
    """Permanently delete a PM2 process."""
    pm2_name = get_pm2_name(user_id, project_name)
    await run_command(f'pm2 delete "{pm2_name}"', timeout=15)
    await run_command("pm2 save", timeout=15)

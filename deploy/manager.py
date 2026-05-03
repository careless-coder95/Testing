"""
Stark Deploy Bot - Deployment Manager
Handles cloning, venv setup, and dependency installation.
"""
import os
import shutil
from typing import Tuple

from core.utils import run_command, logger, get_project_path
from config import DEPLOY_BASE_PATH


async def clone_repo(
    repo_url: str,
    user_id: int,
    project_name: str,
) -> Tuple[bool, str]:
    """
    Clone a GitHub repository into /deployments/{user_id}/{project_name}.
    Returns (success, message).
    """
    project_path = get_project_path(user_id, project_name)

    # Remove if already exists
    if os.path.exists(project_path):
        shutil.rmtree(project_path, ignore_errors=True)

    # Create parent directory
    os.makedirs(os.path.dirname(project_path), exist_ok=True)

    # Normalize URL (ensure .git suffix removed for consistency)
    repo_url = repo_url.rstrip("/")
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]

    cmd = f"git clone --depth=1 {repo_url}.git {project_path}"
    logger.info(f"Cloning: {cmd}")

    returncode, stdout, stderr = await run_command(cmd, timeout=90)

    if returncode != 0:
        # Cleanup on failure
        shutil.rmtree(project_path, ignore_errors=True)
        return False, f"Git clone failed:\n{stderr or stdout}"

    return True, project_path


async def setup_venv(project_path: str) -> Tuple[bool, str]:
    """
    Create a virtual environment inside the project directory.
    """
    venv_path = os.path.join(project_path, "venv")
    cmd = f"python3 -m venv {venv_path}"
    logger.info(f"Creating venv at: {venv_path}")

    returncode, stdout, stderr = await run_command(cmd, cwd=project_path, timeout=60)

    if returncode != 0:
        return False, f"Failed to create venv:\n{stderr or stdout}"

    return True, venv_path


async def install_dependencies(project_path: str) -> Tuple[bool, str]:
    """
    Install Python dependencies via venv pip.
    Returns (success, output).
    """
    req_file = os.path.join(project_path, "requirements.txt")
    if not os.path.isfile(req_file):
        return False, "❌ `requirements.txt` not found in repository."

    pip_path = os.path.join(project_path, "venv", "bin", "pip")
    cmd = f"{pip_path} install -r {req_file} --no-cache-dir"
    logger.info(f"Installing deps: {cmd}")

    returncode, stdout, stderr = await run_command(cmd, cwd=project_path, timeout=300)
    output = stdout or stderr

    if returncode != 0:
        return False, f"Dependency installation failed:\n{output}"

    return True, output


async def cleanup_project(user_id: int, project_name: str):
    """Remove project files from disk."""
    project_path = get_project_path(user_id, project_name)
    if os.path.exists(project_path):
        shutil.rmtree(project_path, ignore_errors=True)
        logger.info(f"Cleaned up: {project_path}")

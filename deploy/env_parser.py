"""
Stark Deploy Bot - ENV File Parser
"""
import os
import re
from typing import Dict, List, Optional


ENV_SAMPLE_FILES = [".env.example", ".env.sample", ".env.template", "example.env", ".env"]


def find_env_sample(project_path: str) -> Optional[str]:
    """Find the env sample file in the project directory."""
    for filename in ENV_SAMPLE_FILES:
        path = os.path.join(project_path, filename)
        if os.path.isfile(path):
            return path
    return None


def extract_env_keys(env_file_path: str) -> List[str]:
    """
    Extract environment variable keys from an env file.
    - For .env files: only returns keys with EMPTY values (needs user input)
    - For .env.example / .env.sample: returns all keys
    """
    keys = []
    is_real_env = os.path.basename(env_file_path) == ".env"

    try:
        with open(env_file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)', line)
                if match:
                    key = match.group(1)
                    value = match.group(2).strip().strip('"').strip("'")
                    # For real .env: only ask for empty values
                    # For sample files: ask for all keys
                    if is_real_env and value:
                        continue  # already has a value, skip
                    keys.append(key)
    except Exception:
        pass
    return keys


def write_env_file(project_path: str, env_vars: Dict[str, str]):
    """Write the .env file to the project directory."""
    env_path = os.path.join(project_path, ".env")
    with open(env_path, "w") as f:
        for key, value in env_vars.items():
            # Quote values with spaces
            if " " in value or not value:
                f.write(f'{key}="{value}"\n')
            else:
                f.write(f"{key}={value}\n")
    return env_path

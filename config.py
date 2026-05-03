"""
Stark Deploy Bot - Configuration
"""
import os
from dotenv import load_dotenv

# ─── Load .env file automatically ─────────────────────────────────────────────
load_dotenv()

# ─── Bot Credentials ──────────────────────────────────────────────────────────
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ─── Owner ────────────────────────────────────────────────────────────────────
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

# ─── Database ─────────────────────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI", "")
DB_PATH = os.environ.get("DB_PATH", "database/stark_db.json")  # fallback if no Mongo

# ─── Deployment Limits ────────────────────────────────────────────────────────
MAX_DEPLOYMENTS_PER_USER = 3
DEPLOY_BASE_PATH = os.environ.get("DEPLOY_BASE_PATH", "/deployments")
LOG_LINES = 50

# ─── Security ─────────────────────────────────────────────────────────────────
BLOCKED_PATTERNS = [
    "rm -rf",
    "rm -r /",
    "shutdown",
    "reboot",
    ":(){ :|:& };:",   # fork bomb
    "mkfs",
    "dd if=",
    "> /dev/sd",
    "chmod -R 777 /",
    "wget",
    "curl",
    "nc ",
    "ncat",
    "/etc/passwd",
    "/etc/shadow",
]

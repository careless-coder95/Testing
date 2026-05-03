# ⚡ Stark Python Deploy System

A production-ready Telegram bot that deploys Python projects with virtual environments and PM2 process management — fully inline UI, zero commands needed after `/start`.

---

## 📁 Project Structure

```
stark_deploy_bot/
├── main.py                  # Entry point, handler registration
├── config.py                # All configuration & constants
├── .env.example             # Environment variable template
├── requirements.txt
│
├── core/
│   ├── state.py             # Centralized in-memory state machine
│   ├── security.py          # Auth checks, command sanitization, validation
│   └── utils.py             # Async subprocess, logging, path helpers
│
├── handlers/
│   ├── start.py             # /start command
│   ├── deploy.py            # Full 13-step deployment flow
│   ├── actions.py           # Logs, Restart, Stop, Delete, My Deployments
│   └── admin.py             # /addsudo /rmsudo /sudolist
│
├── deploy/
│   ├── env_parser.py        # .env.example key extraction & .env writer
│   ├── manager.py           # git clone, venv setup, pip install
│   └── runner.py            # PM2 start/stop/restart/logs wrapper
│
└── database/
    ├── db.py                # Async JSON database
    └── stark_db.json        # Auto-created on first run
```

---

## 🚀 Setup

### 1. Prerequisites

```bash
# Python 3.10+
python3 --version

# PM2 (Node.js process manager)
npm install -g pm2

# Git
git --version
```

### 2. Clone & Install

```bash
git clone https://github.com/yourrepo/stark_deploy_bot
cd stark_deploy_bot
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
nano .env
```

Fill in:

| Variable | Description |
|---|---|
| `API_ID` | From https://my.telegram.org/apps |
| `API_HASH` | From https://my.telegram.org/apps |
| `BOT_TOKEN` | From @BotFather |
| `OWNER_ID` | Your Telegram user ID |
| `DEPLOY_BASE_PATH` | Where projects are cloned (default: `/deployments`) |

### 4. Run

```bash
# Direct
python main.py

# Or with PM2 (recommended for production)
pm2 start "python main.py" --name stark-deploy-bot
pm2 save
pm2 startup
```

---

## 💬 Usage

### Start
Send `/start` to your bot. You'll see the main menu.

### Deploy Flow (13 Steps)
1. Press **🚀 Deploy New Bot**
2. Send GitHub repo URL
3. Send project name
4. Bot clones the repo automatically
5. Detects `.env.example` / `.env.sample`
6. Asks for each ENV variable one-by-one
7. Creates `.env` file
8. Sets up Python virtual environment
9. Installs `requirements.txt`
10. Ask for run command (`python main.py`)
11. Sanitizes & secures the command
12. Starts process with PM2
13. Shows success + management buttons

### Post-Deploy Buttons
| Button | Action |
|---|---|
| 📜 Logs | Last 50 lines of PM2 output |
| 🔄 Restart | PM2 restart |
| ⛔ Stop | PM2 stop |
| 🗑 Delete | Stop + delete files + remove from DB |

### Admin Commands (Owner only)
```
/addsudo 123456789     # Grant access to user
/rmsudo  123456789     # Revoke access
/sudolist              # List all sudo users
```

---

## 🔒 Security Features

- **Authorization**: Owner + sudo list only
- **Deployment limit**: Max 3 active projects per user
- **Command sanitization**: Blocks `rm -rf`, `shutdown`, `reboot`, fork bombs, shell operators
- **Python-only enforcement**: Run command must start with `python` or `python3`
- **Venv isolation**: Each project gets its own `venv/`
- **No shell injection**: Shell operators (`;`, `&&`, `|`, etc.) are blocked

---

## 🗄️ Database Schema

```json
{
  "sudo_users": [123456789],
  "deployments": [
    {
      "user_id": 123456789,
      "project_name": "my-bot",
      "repo_url": "https://github.com/user/repo",
      "path": "/deployments/123456789/my-bot",
      "command": "/deployments/123456789/my-bot/venv/bin/python main.py",
      "status": "running",
      "deployed_at": "2025-01-01T12:00:00"
    }
  ]
}
```

---

## 🔄 State Machine

| State | Description |
|---|---|
| `WAIT_REPO` | Waiting for GitHub URL |
| `WAIT_NAME` | Waiting for project name |
| `WAIT_ENV` | Collecting ENV values one-by-one |
| `WAIT_CMD` | Waiting for run command |

State is cleared on success or error.

---

## ⚠️ Requirements for Deployed Projects

The GitHub repos you deploy must have:
- `requirements.txt` in root
- Python-based entry point
- Optionally: `.env.example` or `.env.sample` for auto-ENV setup

---

## 📝 License

MIT

"""
Stark Deploy Bot - Deployment Flow Handler
Handles all steps of the deployment pipeline.
"""
import datetime
from pyrogram import Client
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from core import state as S
from core.security import (
    is_authorized, can_deploy,
    validate_repo_url, validate_project_name, sanitize_command,
)
from core.utils import get_project_path, truncate, logger
from database.db import get_deployment, save_deployment
from deploy.manager import clone_repo, setup_venv, install_dependencies
from deploy.env_parser import find_env_sample, extract_env_keys, write_env_file
from deploy.runner import pm2_start


# ─── Callback: Deploy Start ───────────────────────────────────────────────────

async def cb_deploy_start(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    ok, msg = await can_deploy(user_id)
    if not ok:
        await query.message.edit_text(msg)
        return

    S.set_state(user_id, S.WAIT_REPO)
    await query.message.edit_text(
        "**📡 Step 1 — GitHub Repository URL**\n\n"
        "Send the GitHub repo URL you want to deploy.\n\n"
        "**Format:** `https://github.com/username/repo`\n\n"
        "_(Only Python repositories supported)_"
    )


# ─── Message Router ───────────────────────────────────────────────────────────

async def deploy_message_handler(client: Client, message: Message):
    """Route incoming text messages to the correct deployment step."""
    user_id = message.from_user.id

    if not await is_authorized(user_id):
        return

    if not S.has_state(user_id):
        return  # Not in a flow

    current = S.get_state(user_id)
    step = current["step"]

    if step == S.WAIT_REPO:
        await _handle_repo(client, message)
    elif step == S.WAIT_NAME:
        await _handle_name(client, message)
    elif step == S.WAIT_ENV:
        await _handle_env(client, message)
    elif step == S.WAIT_CMD:
        await _handle_cmd(client, message)


# ─── Step Handlers ────────────────────────────────────────────────────────────

async def _handle_repo(client: Client, message: Message):
    user_id = message.from_user.id
    url = message.text.strip()

    valid, result = validate_repo_url(url)
    if not valid:
        await message.reply_text(result, quote=True)
        return

    S.update_data(user_id, "repo_url", result)
    S.get_state(user_id)["step"] = S.WAIT_NAME

    await message.reply_text(
        "✅ Repo URL saved!\n\n"
        "**📝 Step 2 — Project Name**\n\n"
        "Enter a unique name for this deployment.\n"
        "_(Letters, numbers, `-`, `_` only — max 32 chars)_",
        quote=True,
    )


async def _handle_name(client: Client, message: Message):
    user_id = message.from_user.id
    name = message.text.strip()

    valid, result = validate_project_name(name)
    if not valid:
        await message.reply_text(result, quote=True)
        return

    # Check uniqueness
    existing = await get_deployment(user_id, result)
    if existing:
        await message.reply_text(
            f"❌ Project `{result}` already exists.\n"
            "Choose a different name.",
            quote=True,
        )
        return

    S.update_data(user_id, "project_name", result)

    # ── Step 3: Clone ──
    status_msg = await message.reply_text(
        "⏳ **Step 3 — Cloning Repository...**\n"
        "`git clone` in progress, please wait...",
        quote=True,
    )

    repo_url = S.get_data(user_id, "repo_url")
    success, path = await clone_repo(repo_url, user_id, result)

    if not success:
        S.clear_state(user_id)
        await status_msg.edit_text(
            f"❌ **Clone Failed**\n\n```\n{truncate(path)}\n```"
        )
        return

    S.update_data(user_id, "project_path", path)
    logger.info(f"Cloned {repo_url} → {path}")

    # ── Step 4: Detect ENV ──
    await status_msg.edit_text(
        "✅ Repo cloned!\n\n"
        "🔍 **Step 4 — Detecting ENV configuration...**"
    )

    env_sample = find_env_sample(path)
    if env_sample:
        env_keys = extract_env_keys(env_sample)
    else:
        env_keys = []

    S.update_data(user_id, "env_keys", env_keys)
    S.update_data(user_id, "env_values", {})
    S.update_data(user_id, "env_index", 0)

    if env_keys:
        S.get_state(user_id)["step"] = S.WAIT_ENV
        await status_msg.edit_text(
            f"✅ Found **{len(env_keys)}** ENV variable(s) to configure.\n\n"
            f"**Step 5 — Configure ENV**\n\n"
            f"**[1/{len(env_keys)}]** Enter value for:\n"
            f"`{env_keys[0]}`"
        )
    else:
        await status_msg.edit_text(
            "ℹ️ No ENV file detected — skipping ENV setup.\n\n"
            "⏳ **Step 7 — Setting up virtual environment...**"
        )
        await _proceed_to_venv(client, message, status_msg)


async def _handle_env(client: Client, message: Message):
    user_id = message.from_user.id
    value = message.text.strip()

    env_keys = S.get_data(user_id, "env_keys", [])
    env_values = S.get_data(user_id, "env_values", {})
    idx = S.get_data(user_id, "env_index", 0)

    # Save current key value
    env_values[env_keys[idx]] = value
    S.update_data(user_id, "env_values", env_values)

    idx += 1
    S.update_data(user_id, "env_index", idx)

    if idx < len(env_keys):
        await message.reply_text(
            f"✅ Saved!\n\n"
            f"**[{idx + 1}/{len(env_keys)}]** Enter value for:\n"
            f"`{env_keys[idx]}`",
            quote=True,
        )
    else:
        # ── Step 6: Write .env ──
        project_path = S.get_data(user_id, "project_path")
        write_env_file(project_path, env_values)

        status_msg = await message.reply_text(
            "✅ **ENV file created!**\n\n"
            "⏳ **Step 7 — Setting up virtual environment...**",
            quote=True,
        )
        await _proceed_to_venv(client, message, status_msg)


async def _proceed_to_venv(client, message, status_msg):
    """Steps 7–9: venv, pip install, ask for run command."""
    user_id = message.from_user.id
    project_path = S.get_data(user_id, "project_path")

    # ── Step 7: Setup venv ──
    ok, venv_result = await setup_venv(project_path)
    if not ok:
        S.clear_state(user_id)
        await status_msg.edit_text(
            f"❌ **Venv Setup Failed**\n\n```\n{truncate(venv_result)}\n```"
        )
        return

    # ── Step 8: Install deps ──
    await status_msg.edit_text(
        "✅ Virtual environment ready!\n\n"
        "⏳ **Step 8 — Installing dependencies...**\n"
        "_This may take a minute..._"
    )

    ok, install_result = await install_dependencies(project_path)
    if not ok:
        S.clear_state(user_id)
        await status_msg.edit_text(
            f"❌ **Installation Failed**\n\n```\n{truncate(install_result)}\n```"
        )
        return

    # ── Step 9: Ask for run command ──
    S.get_state(user_id)["step"] = S.WAIT_CMD
    await status_msg.edit_text(
        "✅ Dependencies installed!\n\n"
        "**⚙️ Step 9 — Run Command**\n\n"
        "What command should be used to start your bot?\n\n"
        "**Examples:**\n"
        "• `python main.py`\n"
        "• `python3 bot.py`\n"
        "• `python src/app.py`\n\n"
        "_(Use `python` or `python3` — venv will be applied automatically)_"
    )


async def _handle_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    cmd_raw = message.text.strip()
    project_path = S.get_data(user_id, "project_path")
    project_name = S.get_data(user_id, "project_name")

    # ── Step 10: Sanitize command ──
    valid, cmd = sanitize_command(cmd_raw, project_path)
    if not valid:
        await message.reply_text(cmd, quote=True)
        return

    status_msg = await message.reply_text(
        "✅ Command validated!\n\n"
        "🚀 **Step 11 — Starting with PM2...**",
        quote=True,
    )

    # ── Step 11: PM2 Start ──
    ok, pm2_result = await pm2_start(user_id, project_name, cmd, project_path)
    if not ok:
        S.clear_state(user_id)
        await status_msg.edit_text(
            f"❌ **PM2 Start Failed**\n\n```\n{truncate(pm2_result)}\n```"
        )
        return

    # ── Step 12: Save deployment ──
    deployment = {
        "user_id": user_id,
        "project_name": project_name,
        "repo_url": S.get_data(user_id, "repo_url"),
        "path": project_path,
        "command": cmd,
        "status": "running",
        "deployed_at": datetime.datetime.utcnow().isoformat(),
    }
    await save_deployment(deployment)
    S.clear_state(user_id)

    # ── Step 13: Success UI ──
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📜 Logs", callback_data=f"logs:{project_name}"),
            InlineKeyboardButton("🔄 Restart", callback_data=f"restart:{project_name}"),
        ],
        [
            InlineKeyboardButton("⛔ Stop", callback_data=f"stop:{project_name}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{project_name}"),
        ],
        [InlineKeyboardButton("📦 My Deployments", callback_data="my_deployments")],
    ])

    await status_msg.edit_text(
        f"🎉 **Deployment Successful!**\n\n"
        f"**Project:** `{project_name}`\n"
        f"**Status:** 🟢 Running\n"
        f"**PM2 Name:** `stark_{user_id}_{project_name}`\n\n"
        f"Use the buttons below to manage your deployment:",
        reply_markup=keyboard,
    )

"""
Stark Deploy Bot - Post-Deploy Action Handlers
Handles: Logs, Restart, Stop, Delete, My Deployments
"""
from pyrogram import Client
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from core.security import is_authorized
from core.utils import truncate
from database.db import (
    get_deployments, get_deployment,
    delete_deployment, update_deployment_status,
)
from deploy.runner import pm2_logs, pm2_restart, pm2_stop, pm2_delete
from deploy.manager import cleanup_project


def _project_keyboard(project_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📜 Logs", callback_data=f"logs:{project_name}"),
            InlineKeyboardButton("🔄 Restart", callback_data=f"restart:{project_name}"),
        ],
        [
            InlineKeyboardButton("⛔ Stop", callback_data=f"stop:{project_name}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{project_name}"),
        ],
        [InlineKeyboardButton("◀️ Back", callback_data="my_deployments")],
    ])


# ─── My Deployments ───────────────────────────────────────────────────────────

async def cb_my_deployments(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    deployments = await get_deployments(user_id)
    if not deployments:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Deploy New Bot", callback_data="deploy_start")]
        ])
        await query.message.edit_text(
            "📭 **No deployments yet.**\n\n"
            "Start by deploying a new Python bot!",
            reply_markup=keyboard,
        )
        return

    buttons = []
    for d in deployments:
        status_icon = "🟢" if d.get("status") == "running" else "🔴"
        buttons.append([
            InlineKeyboardButton(
                f"{status_icon} {d['project_name']}",
                callback_data=f"project:{d['project_name']}"
            )
        ])

    buttons.append([InlineKeyboardButton("🚀 Deploy New Bot", callback_data="deploy_start")])

    await query.message.edit_text(
        f"📦 **Your Deployments** ({len(deployments)} total)\n\n"
        "Select a project to manage it:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ─── Project View ─────────────────────────────────────────────────────────────

async def cb_project_view(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    project_name = query.data.split(":", 1)[1]
    dep = await get_deployment(user_id, project_name)

    if not dep:
        await query.message.edit_text("❌ Deployment not found.")
        return

    status_icon = "🟢 Running" if dep.get("status") == "running" else "🔴 Stopped"

    await query.message.edit_text(
        f"**📦 {project_name}**\n\n"
        f"**Status:** {status_icon}\n"
        f"**Repo:** `{dep.get('repo_url', 'N/A')}`\n"
        f"**Deployed:** `{dep.get('deployed_at', 'N/A')[:10]}`\n\n"
        "Manage your deployment:",
        reply_markup=_project_keyboard(project_name),
    )


# ─── Logs ─────────────────────────────────────────────────────────────────────

async def cb_logs(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    project_name = query.data.split(":", 1)[1]
    await query.answer("Fetching logs...")
    await query.message.edit_text(f"⏳ Fetching logs for `{project_name}`...")

    logs = await pm2_logs(user_id, project_name)
    logs_text = truncate(logs, 3000)

    await query.message.edit_text(
        f"**📜 Logs — {project_name}**\n\n"
        f"```\n{logs_text}\n```",
        reply_markup=_project_keyboard(project_name),
    )


# ─── Restart ──────────────────────────────────────────────────────────────────

async def cb_restart(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    project_name = query.data.split(":", 1)[1]
    await query.answer("Restarting...")
    await query.message.edit_text(f"🔄 Restarting `{project_name}`...")

    ok, msg = await pm2_restart(user_id, project_name)
    if ok:
        await update_deployment_status(user_id, project_name, "running")

    await query.message.edit_text(
        f"{'✅' if ok else '❌'} {msg}",
        reply_markup=_project_keyboard(project_name),
    )


# ─── Stop ─────────────────────────────────────────────────────────────────────

async def cb_stop(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    project_name = query.data.split(":", 1)[1]
    await query.answer("Stopping...")
    await query.message.edit_text(f"⛔ Stopping `{project_name}`...")

    ok, msg = await pm2_stop(user_id, project_name)
    if ok:
        await update_deployment_status(user_id, project_name, "stopped")

    await query.message.edit_text(
        f"{'✅' if ok else '❌'} {msg}",
        reply_markup=_project_keyboard(project_name),
    )


# ─── Delete ───────────────────────────────────────────────────────────────────

async def cb_delete_confirm(client: Client, query: CallbackQuery):
    """Ask for confirmation before deleting."""
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    project_name = query.data.split(":", 1)[1]

    await query.message.edit_text(
        f"⚠️ **Are you sure?**\n\n"
        f"This will permanently delete `{project_name}` and remove all files.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, Delete", callback_data=f"delete_confirmed:{project_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"project:{project_name}"),
            ]
        ]),
    )


async def cb_delete_confirmed(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not await is_authorized(user_id):
        await query.answer("❌ Unauthorized", show_alert=True)
        return

    project_name = query.data.split(":", 1)[1]
    await query.answer("Deleting...")
    await query.message.edit_text(f"🗑 Deleting `{project_name}`...")

    # Stop & delete PM2 process
    await pm2_stop(user_id, project_name)
    await pm2_delete(user_id, project_name)

    # Delete files from disk
    await cleanup_project(user_id, project_name)

    # Remove from database
    await delete_deployment(user_id, project_name)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 My Deployments", callback_data="my_deployments")],
        [InlineKeyboardButton("🚀 Deploy New Bot", callback_data="deploy_start")],
    ])

    await query.message.edit_text(
        f"✅ `{project_name}` has been deleted successfully.",
        reply_markup=keyboard,
    )

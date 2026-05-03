"""
Stark Deploy Bot - Main Entry Point
"""
import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from core.utils import logger

# ─── Import Handlers ──────────────────────────────────────────────────────────
from handlers.start import start_handler
from handlers.deploy import (
    cb_deploy_start,
    deploy_message_handler,
)
from handlers.actions import (
    cb_my_deployments,
    cb_project_view,
    cb_logs,
    cb_restart,
    cb_stop,
    cb_delete_confirm,
    cb_delete_confirmed,
)
from handlers.admin import addsudo_handler, rmsudo_handler, sudolist_handler
from core.security import is_authorized


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_config():
    errors = []
    if not API_ID:
        errors.append("API_ID is not set")
    if not API_HASH:
        errors.append("API_HASH is not set")
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is not set")
    if not OWNER_ID:
        errors.append("OWNER_ID is not set")
    if errors:
        for e in errors:
            logger.error(f"Config error: {e}")
        sys.exit(1)


# ─── App ──────────────────────────────────────────────────────────────────────

validate_config()

app = Client(
    "stark_deploy_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


# ─── Register Command Handlers ────────────────────────────────────────────────

@app.on_message(filters.command("start") & filters.private)
async def on_start(client: Client, message: Message):
    await start_handler(client, message)


@app.on_message(filters.command("addsudo") & filters.private)
async def on_addsudo(client: Client, message: Message):
    await addsudo_handler(client, message)


@app.on_message(filters.command("rmsudo") & filters.private)
async def on_rmsudo(client: Client, message: Message):
    await rmsudo_handler(client, message)


@app.on_message(filters.command("sudolist") & filters.private)
async def on_sudolist(client: Client, message: Message):
    await sudolist_handler(client, message)


# ─── Register Callback Handlers ───────────────────────────────────────────────

@app.on_callback_query(filters.regex("^deploy_start$"))
async def on_deploy_start(client: Client, query: CallbackQuery):
    await cb_deploy_start(client, query)


@app.on_callback_query(filters.regex("^my_deployments$"))
async def on_my_deployments(client: Client, query: CallbackQuery):
    await cb_my_deployments(client, query)


@app.on_callback_query(filters.regex("^project:"))
async def on_project_view(client: Client, query: CallbackQuery):
    await cb_project_view(client, query)


@app.on_callback_query(filters.regex("^logs:"))
async def on_logs(client: Client, query: CallbackQuery):
    await cb_logs(client, query)


@app.on_callback_query(filters.regex("^restart:"))
async def on_restart(client: Client, query: CallbackQuery):
    await cb_restart(client, query)


@app.on_callback_query(filters.regex("^stop:"))
async def on_stop(client: Client, query: CallbackQuery):
    await cb_stop(client, query)


@app.on_callback_query(filters.regex("^delete:"))
async def on_delete(client: Client, query: CallbackQuery):
    await cb_delete_confirm(client, query)


@app.on_callback_query(filters.regex("^delete_confirmed:"))
async def on_delete_confirmed(client: Client, query: CallbackQuery):
    await cb_delete_confirmed(client, query)


# ─── Text Message Handler ─────────────────────────────────────────────────────

@app.on_message(filters.text & filters.private & ~filters.command(
    ["start", "addsudo", "rmsudo", "sudolist"]
))
async def on_text(client: Client, message: Message):
    await deploy_message_handler(client, message)


# ─── Startup ──────────────────────────────────────────────────────────────────

async def main():
    logger.info("⚡ Stark Deploy Bot starting...")
    logger.info(f"Owner ID: {OWNER_ID}")

    # Ensure deploy base path exists
    os.makedirs("/deployments", exist_ok=True)

    async with app:
        me = await app.get_me()
        logger.info(f"Bot started: @{me.username} ({me.id})")
        logger.info("Listening for messages...")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

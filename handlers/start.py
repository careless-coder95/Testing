"""
Stark Deploy Bot - /start Handler
"""
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from core.security import is_authorized
from core.state import clear_state


async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if not await is_authorized(user_id):
        await message.reply_text(
            "🔒 Access Denied.\n"
            "You are not authorized to use this bot.",
            quote=True,
        )
        return

    # Clear any dangling state
    clear_state(user_id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Deploy New Bot", callback_data="deploy_start")],
        [InlineKeyboardButton("📦 My Deployments", callback_data="my_deployments")],
    ])

    await message.reply_text(
        "⚡ **Stark Python Deploy System**\n\n"
        "Welcome! This platform lets you deploy Python bots "
        "safely with virtual environments and PM2 process management.\n\n"
        "**Features:**\n"
        "• Auto venv per project\n"
        "• ENV file configuration\n"
        "• PM2 process management\n"
        "• Logs · Restart · Stop\n\n"
        "Choose an option below:",
        reply_markup=keyboard,
        quote=True,
    )

"""
Stark Deploy Bot - Admin Command Handlers
Owner-only commands: /addsudo, /rmsudo, /sudolist
"""
from pyrogram import Client, filters
from pyrogram.types import Message

from core.security import is_owner
from database.db import add_sudo_user, remove_sudo_user, get_sudo_users


async def addsudo_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if not await is_owner(user_id):
        await message.reply_text("❌ Only the bot owner can use this command.", quote=True)
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply_text("**Usage:** `/addsudo {user_id}`", quote=True)
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.reply_text("❌ Invalid user ID. Must be a number.", quote=True)
        return

    added = await add_sudo_user(target_id)
    if added:
        await message.reply_text(
            f"✅ User `{target_id}` added to sudo list.", quote=True
        )
    else:
        await message.reply_text(
            f"ℹ️ User `{target_id}` is already in the sudo list.", quote=True
        )


async def rmsudo_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if not await is_owner(user_id):
        await message.reply_text("❌ Only the bot owner can use this command.", quote=True)
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply_text("**Usage:** `/rmsudo {user_id}`", quote=True)
        return

    try:
        target_id = int(parts[1])
    except ValueError:
        await message.reply_text("❌ Invalid user ID.", quote=True)
        return

    removed = await remove_sudo_user(target_id)
    if removed:
        await message.reply_text(
            f"✅ User `{target_id}` removed from sudo list.", quote=True
        )
    else:
        await message.reply_text(
            f"ℹ️ User `{target_id}` was not in the sudo list.", quote=True
        )


async def sudolist_handler(client: Client, message: Message):
    user_id = message.from_user.id

    if not await is_owner(user_id):
        await message.reply_text("❌ Only the bot owner can use this command.", quote=True)
        return

    sudo_users = await get_sudo_users()
    if not sudo_users:
        await message.reply_text("📭 No sudo users configured.", quote=True)
        return

    user_list = "\n".join([f"• `{uid}`" for uid in sudo_users])
    await message.reply_text(
        f"**👥 Sudo Users ({len(sudo_users)})**\n\n{user_list}",
        quote=True,
    )

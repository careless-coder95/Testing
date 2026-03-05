import os
import asyncio
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Force Playwright to look in the correct location on Render -> MUST BE BEFORE IMPORT
if "RENDER" in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/render/project/src/browsers"

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from playwright.async_api import async_playwright
from pymongo import MongoClient

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID", "")
OWNER_NAME = os.getenv("OWNER_NAME", "Owner")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
LOG_GROUP_ID = -1003642420485  # Fixed log group

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # Silence httpx logs
logger = logging.getLogger(__name__)

# Base URL for fetching info
BASE_URL = "https://zionix.xo.je/znnum?number={uid}"

# Bot state
MAINTENANCE_MODE = False

# ═══════════════════════════════════════════════════════════════
# 💾 MONGODB CONNECTION
# ═══════════════════════════════════════════════════════════════

try:
    client = MongoClient(MONGO_URI)
    db = client["uid_bot"]
    
    # Collections
    sudo_col = db["sudo_users"]
    banned_col = db["banned_users"]
    premium_col = db["premium_users"]
    users_col = db["users"]
    config_col = db["config"]
    stats_col = db["stats"]
    history_col = db["history"]
    
    logger.info("MongoDB connected successfully!")
except Exception as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise


# ═══════════════════════════════════════════════════════════════
# 💾 DATABASE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

# Sudo Users
def get_sudo_users() -> set:
    users = sudo_col.find_one({"_id": "sudo_list"})
    return set(users.get("users", [])) if users else set()

def save_sudo_users(users: set):
    sudo_col.update_one({"_id": "sudo_list"}, {"$set": {"users": list(users)}}, upsert=True)

# Banned Users
def get_banned_users() -> set:
    users = banned_col.find_one({"_id": "banned_list"})
    return set(users.get("users", [])) if users else set()

def save_banned_users(users: set):
    banned_col.update_one({"_id": "banned_list"}, {"$set": {"users": list(users)}}, upsert=True)

# Premium Users
def get_premium_users() -> dict:
    users = premium_col.find_one({"_id": "premium_list"})
    return users.get("data", {}) if users else {}

def save_premium_users(data: dict):
    premium_col.update_one({"_id": "premium_list"}, {"$set": {"data": data}}, upsert=True)

# All Users
def get_all_users() -> set:
    users = users_col.find_one({"_id": "all_users"})
    return set(users.get("users", [])) if users else set()

def add_user(user_id: int):
    users = get_all_users()
    users.add(str(user_id))
    users_col.update_one({"_id": "all_users"}, {"$set": {"users": list(users)}}, upsert=True)

# Stats
def get_stats() -> dict:
    stats = stats_col.find_one({"_id": "bot_stats"})
    if stats:
        return stats.get("data", {})
    return {
        "total_lookups": 0,
        "successful": 0,
        "failed": 0,
        "daily": {},
        "user_lookups": {},
        "user_daily": {}
    }

def save_stats(stats: dict):
    stats_col.update_one({"_id": "bot_stats"}, {"$set": {"data": stats}}, upsert=True)

def record_lookup(user_id: int, query: str, success: bool):
    stats = get_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    
    stats["total_lookups"] = stats.get("total_lookups", 0) + 1
    if success:
        stats["successful"] = stats.get("successful", 0) + 1
    else:
        stats["failed"] = stats.get("failed", 0) + 1
    
    if "daily" not in stats:
        stats["daily"] = {}
    stats["daily"][today] = stats["daily"].get(today, 0) + 1
    
    if "user_lookups" not in stats:
        stats["user_lookups"] = {}
    uid_str = str(user_id)
    stats["user_lookups"][uid_str] = stats["user_lookups"].get(uid_str, 0) + 1
    
    save_stats(stats)

# History
def get_user_history(user_id: int) -> list:
    history = history_col.find_one({"_id": str(user_id)})
    return history.get("data", [])[-20:] if history else []

def add_to_history(user_id: int, query: str, result: str):
    history = get_user_history(user_id)
    history.append({
        "query": query,
        "time": datetime.now().isoformat(),
        "result_preview": result[:100] if result else "No data"
    })
    history = history[-50:]  # Keep last 50
    history_col.update_one({"_id": str(user_id)}, {"$set": {"data": history}}, upsert=True)

# Daily Limits
def get_user_daily_lookups(user_id: int) -> int:
    stats = get_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    user_daily = stats.get("user_daily", {}).get(today, {})
    return user_daily.get(str(user_id), 0)

def increment_user_daily(user_id: int):
    stats = get_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    if "user_daily" not in stats:
        stats["user_daily"] = {}
    if today not in stats["user_daily"]:
        stats["user_daily"][today] = {}
    uid_str = str(user_id)
    stats["user_daily"][today][uid_str] = stats["user_daily"][today].get(uid_str, 0) + 1
    save_stats(stats)

def get_daily_limit(user_id: int) -> int:
    if str(user_id) == OWNER_ID:
        return 999999
    premium = get_premium_users()
    if str(user_id) in premium:
        tier = premium[str(user_id)].get("tier", "basic")
        if tier == "vip":
            return 100
        elif tier == "pro":
            return 50
        else:
            return 25
    if str(user_id) in get_sudo_users():
        return 20
    return 5


# ═══════════════════════════════════════════════════════════════
# 🔐 AUTHORIZATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def is_owner(user_id: int) -> bool:
    return str(user_id) == OWNER_ID

def is_sudo(user_id: int) -> bool:
    return str(user_id) in get_sudo_users()

def is_premium(user_id: int) -> bool:
    premium = get_premium_users()
    if str(user_id) in premium:
        expiry = premium[str(user_id)].get("expiry")
        if expiry:
            if datetime.fromisoformat(expiry) > datetime.now():
                return True
    return False

def is_banned(user_id: int) -> bool:
    return str(user_id) in get_banned_users()

def is_authorized(user_id: int) -> bool:
    if is_banned(user_id):
        return False
    return is_owner(user_id) or is_sudo(user_id) or is_premium(user_id)


# ═══════════════════════════════════════════════════════════════
# 🎨 STYLING FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def stylize(text: str) -> str:
    if not text:
        return ""
    mapping = {
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ',
        'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ',
        'o': 'ᴏ', 'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ',
        'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ', 'z': 'ᴢ',
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4',
        '5': '5', '6': '6', '7': '7', '8': '8', '9': '9'
    }
    return "".join(mapping.get(c, c) for c in text.lower())

def get_user_mention(user) -> str:
    name = escape_html(user.first_name or "User")
    return f'<a href="tg://openmessage?user_id={user.id}">{name}</a>'

def panel(title: str, content: str) -> str:
    styled_title = stylize(title)
    return f"""╭───────────────────╮
│ <b>{styled_title}</b> │
╰───────────────────╯

{content}"""

def get_owner_footer() -> str:
    owner_link = f"tg://openmessage?user_id={OWNER_ID}"
    return f"\n◈ ━━━━━━ ⸙ ━━━━━━ ◈\n👑 {stylize('Owner')}: <a href=\"{owner_link}\">{stylize(OWNER_NAME)}</a>"


# ═══════════════════════════════════════════════════════════════
# 📋 BASIC COMMANDS
# ═══════════════════════════════════════════════════════════════

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug command to show user's ID"""
    user = update.effective_user
    is_own = "✅ YES" if str(user.id) == OWNER_ID else "❌ NO"
    content = f"""👤 <b>Your ID:</b> <code>{user.id}</code>
🔧 <b>Env OWNER_ID:</b> <code>{OWNER_ID}</code>
✅ <b>Is Owner:</b> {is_own}"""
    await update.message.reply_text(panel("🆔 Your Info", content), parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id)
    
    if MAINTENANCE_MODE and not is_owner(user.id):
        await update.message.reply_text(panel("🔧 Maintenance", "Bot is under maintenance. Please try again later."), parse_mode="HTML")
        return
    
    if is_banned(user.id):
        await update.message.reply_text(panel("🚫 Banned", "You are banned from using this bot."), parse_mode="HTML")
        return
    
    if is_authorized(user.id):
        tier = "👑 Owner" if is_owner(user.id) else "⭐ Premium" if is_premium(user.id) else "🔓 Sudo"
        limit = get_daily_limit(user.id)
        used = get_user_daily_lookups(user.id)
        
        content = f"""✨ <b>Welcome back, {escape_html(user.first_name)}!</b>

🎫 <b>Tier:</b> {tier}
📊 <b>Daily Limit:</b> {used}/{limit}

🔍 <i>Send any mobile number to fetch info.</i>
{get_owner_footer()}"""
        
        keyboard = [
    [
        InlineKeyboardButton("📖 ˹ʜєʟᴘ & ɢᴜɪᴅє˼", callback_data="help"),
        InlineKeyboardButton("🖥️ ˹ʙσᴛ sᴛᴧᴛs˼", callback_data="mystats")
    ],
    [
        InlineKeyboardButton("📜 ˹sєᴧʀᴄʜ ʜɪsᴛσʀʏ˼", callback_data="history")
    ],
    [
        InlineKeyboardButton("💬 ˹sᴜᴘᴘσʀᴛ ɢʀσᴜᴘ˼", url="https://t.me/II_StarkxRich_II"),
        InlineKeyboardButton("📢 ˹σғғɪᴄɪᴧʟ ᴄʜᴧηηєʟ˼", url="https://t.me/ll_CarelessxCoder_ll")
    ],
    [
        InlineKeyboardButton("🚀 ˹ᴜᴘᴅᴧᴛє ᴄʜᴧηηєʟ˼", url="https://t.me/ROLEX_MODS_45")
    ]
        ]
        await update.message.reply_text(panel("🔐 Premium Access", content), parse_mode="HTML", 
                                         reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
    else:
        content = f"""⚠️ <b>You are not authorized!</b>

📩 Contact the owner for access.
{get_owner_footer()}"""
        keyboard = [
    [
        InlineKeyboardButton("👑 ˹ᴄσηᴛᴧᴄᴛ σᴡηєʀ˼", url=f"tg://openmessage?user_id={OWNER_ID}")
    ],
    [
        InlineKeyboardButton("💬 ˹sᴜᴘᴘσʀᴛ ɢʀσᴜᴘ˼", url="https://t.me/+tnYU-nYOsRFlNmRl")
    ],
    [
        InlineKeyboardButton("📢 ˹σғғɪᴄɪᴧʟ ᴄʜᴧηηєʟ˼", url="https://t.me/About_Spector"),
        InlineKeyboardButton("🚀 ˹ᴜᴘᴅᴧᴛє ᴄʜᴧηηєʟ˼", url="https://t.me/+tnYU-nYOsRFlNmRl")
    ]
        ]
        await update.message.reply_text(panel("🚫 Access Denied", content), parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_owner(user_id):
        content = """<b>👑 Owner Commands:</b>
• /owner - View all owner commands

<b>📋 User Commands:</b>
• /start - Welcome
• /help - This menu
• /mystats - Your stats
• /history - Lookup history
• /limit - Check daily limit

<b>🔍 Usage:</b>
Send any number to lookup."""
    elif is_authorized(user_id):
        content = """<b>📋 Commands:</b>
• /start - Welcome
• /help - This menu
• /mystats - Your stats
• /history - Lookup history
• /limit - Check daily limit

<b>🔍 Usage:</b>
Send any number to lookup."""
    else:
        content = "⚠️ You are not authorized!"
    
    await update.message.reply_text(panel("📖 Help Menu", content + get_owner_footer()), 
                                     parse_mode="HTML", disable_web_page_preview=True)


async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    content = """<b>👑 Owner Commands:</b>

<b>🔐 Sudo Management:</b>
• /addsudo [id] - Add sudo user
• /rmsudo [id] - Remove sudo
• /sudolist - View all sudos

<b>🚫 Ban Management:</b>
• /ban [id] - Ban user
• /unban [id] - Unban user
• /banlist - View banned

<b>⭐ Premium Management:</b>
• /addpremium [id] [days] [tier]
• /rmpremium [id] - Remove premium
• /premiumlist - View premium users

<b>📊 Analytics:</b>
• /stats - Bot statistics

<b>⚙️ Admin Tools:</b>
• /broadcast [msg] - Broadcast to all
• /maintenance - Toggle maintenance"""
    
    await update.message.reply_text(panel("👑 Owner Panel", content), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🔐 SUDO MANAGEMENT
# ═══════════════════════════════════════════════════════════════

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    target_id = None
    if update.message.reply_to_message:
        target_id = str(update.message.reply_to_message.from_user.id)
    elif context.args:
        target_id = context.args[0]
    
    if not target_id or not target_id.isdigit():
        await update.message.reply_text("⚠️ Usage: /addsudo [user_id]", parse_mode="HTML")
        return
    
    users = get_sudo_users()
    if target_id in users:
        await update.message.reply_text(f"ℹ️ User <code>{target_id}</code> is already sudo.", parse_mode="HTML")
        return
    
    users.add(target_id)
    save_sudo_users(users)
    
    await update.message.reply_text(panel("✅ Sudo Added", f"👤 <b>ID:</b> <code>{target_id}</code>"), parse_mode="HTML")
    
    try:
        dm = panel("🎉 Congratulations", f"You've been granted sudo access!\n\nSend /start to begin.{get_owner_footer()}")
        await context.bot.send_message(int(target_id), dm, parse_mode="HTML", disable_web_page_preview=True)
    except:
        pass


async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    target_id = None
    if update.message.reply_to_message:
        target_id = str(update.message.reply_to_message.from_user.id)
    elif context.args:
        target_id = context.args[0]
    
    if not target_id:
        await update.message.reply_text("⚠️ Usage: /rmsudo [user_id]", parse_mode="HTML")
        return
    
    users = get_sudo_users()
    users.discard(target_id)
    save_sudo_users(users)
    
    await update.message.reply_text(panel("🗑️ Sudo Removed", f"👤 <b>ID:</b> <code>{target_id}</code>"), parse_mode="HTML")


async def sudo_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    users = get_sudo_users()
    if users:
        user_list = "\n".join([f"  • <code>{uid}</code>" for uid in users])
        content = f"<b>Total:</b> {len(users)}\n\n{user_list}"
    else:
        content = "<i>No sudo users.</i>"
    
    await update.message.reply_text(panel("📋 Sudo List", content), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🚫 BAN MANAGEMENT
# ═══════════════════════════════════════════════════════════════

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    target_id = None
    if update.message.reply_to_message:
        target_id = str(update.message.reply_to_message.from_user.id)
    elif context.args:
        target_id = context.args[0]
    
    if not target_id:
        await update.message.reply_text("⚠️ Usage: /ban [user_id]", parse_mode="HTML")
        return
    
    users = get_banned_users()
    users.add(target_id)
    save_banned_users(users)
    
    await update.message.reply_text(panel("🚫 User Banned", f"👤 <b>ID:</b> <code>{target_id}</code>"), parse_mode="HTML")


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    target_id = None
    if update.message.reply_to_message:
        target_id = str(update.message.reply_to_message.from_user.id)
    elif context.args:
        target_id = context.args[0]
    
    if not target_id:
        await update.message.reply_text("⚠️ Usage: /unban [user_id]", parse_mode="HTML")
        return
    
    users = get_banned_users()
    users.discard(target_id)
    save_banned_users(users)
    
    await update.message.reply_text(panel("✅ User Unbanned", f"👤 <b>ID:</b> <code>{target_id}</code>"), parse_mode="HTML")


async def ban_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    users = get_banned_users()
    if users:
        user_list = "\n".join([f"  • <code>{uid}</code>" for uid in users])
        content = f"<b>Total:</b> {len(users)}\n\n{user_list}"
    else:
        content = "<i>No banned users.</i>"
    
    await update.message.reply_text(panel("🚫 Ban List", content), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# ⭐ PREMIUM MANAGEMENT
# ═══════════════════════════════════════════════════════════════

async def add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    target_id = None
    days = 30  # Default 30 days
    
    # Get target user
    if update.message.reply_to_message:
        target_id = str(update.message.reply_to_message.from_user.id)
        if context.args:
            try:
                days = int(context.args[0])
            except:
                pass
    elif context.args:
        target_id = context.args[0]
        if len(context.args) > 1:
            try:
                days = int(context.args[1])
            except:
                pass
    
    if not target_id:
        await update.message.reply_text("⚠️ Usage: /addpremium [user_id] [days]\nOr reply to a user's message", parse_mode="HTML")
        return
    
    # Show tier selection buttons
    content = f"""👤 <b>User ID:</b> <code>{target_id}</code>
⏰ <b>Duration:</b> {days} days

<b>Select Premium Tier:</b>"""
    
    keyboard = [
        [
            InlineKeyboardButton("🥉 Basic (25/day)", callback_data=f"premium_{target_id}_{days}_basic"),
            InlineKeyboardButton("🥈 Pro (50/day)", callback_data=f"premium_{target_id}_{days}_pro"),
        ],
        [
            InlineKeyboardButton("🥇 VIP (100/day)", callback_data=f"premium_{target_id}_{days}_vip"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="premium_cancel"),
        ]
    ]
    
    await update.message.reply_text(panel("⭐ Add Premium", content), parse_mode="HTML", 
                                     reply_markup=InlineKeyboardMarkup(keyboard))


async def remove_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /rmpremium [user_id]", parse_mode="HTML")
        return
    
    target_id = context.args[0]
    premium = get_premium_users()
    if target_id in premium:
        del premium[target_id]
        save_premium_users(premium)
    
    await update.message.reply_text(panel("🗑️ Premium Removed", f"👤 <b>ID:</b> <code>{target_id}</code>"), parse_mode="HTML")


async def premium_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    premium = get_premium_users()
    if premium:
        lines = []
        for uid, data in premium.items():
            tier = data.get("tier", "basic")
            expiry = data.get("expiry", "N/A")[:10]
            lines.append(f"  • <code>{uid}</code> [{tier}] exp: {expiry}")
        content = f"<b>Total:</b> {len(premium)}\n\n" + "\n".join(lines)
    else:
        content = "<i>No premium users.</i>"
    
    await update.message.reply_text(panel("⭐ Premium List", content), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 📊 STATS & ANALYTICS
# ═══════════════════════════════════════════════════════════════

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    stats = get_stats()
    all_users = get_all_users()
    sudo_users = get_sudo_users()
    premium = get_premium_users()
    banned = get_banned_users()
    
    today = datetime.now().strftime("%Y-%m-%d")
    today_lookups = stats.get("daily", {}).get(today, 0)
    
    content = f"""<b>📈 Overview:</b>
  • Total Users: {len(all_users)}
  • Sudo Users: {len(sudo_users)}
  • Premium: {len(premium)}
  • Banned: {len(banned)}

<b>🔍 Lookups:</b>
  • Total: {stats.get('total_lookups', 0)}
  • Today: {today_lookups}
  • Success: {stats.get('successful', 0)}
  • Failed: {stats.get('failed', 0)}"""
    
    await update.message.reply_text(panel("📊 Bot Statistics", content), parse_mode="HTML")


async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    stats = get_stats()
    lookups = stats.get("user_lookups", {}).get(str(user_id), 0)
    today_used = get_user_daily_lookups(user_id)
    limit = get_daily_limit(user_id)
    
    tier = "Owner" if is_owner(user_id) else "Premium" if is_premium(user_id) else "Sudo"
    
    content = f"""<b>Your Statistics:</b>

🎫 <b>Tier:</b> {tier}
📊 <b>Total Lookups:</b> {lookups}
📅 <b>Today:</b> {today_used}/{limit}"""
    
    await update.message.reply_text(panel("📊 My Stats", content), parse_mode="HTML")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    history = get_user_history(user_id)
    
    if history:
        lines = []
        for h in history[-10:]:
            q = h.get("query", "?")[:15]
            t = h.get("time", "")[:10]
            lines.append(f"  • <code>{q}</code> ({t})")
        content = "\n".join(lines)
    else:
        content = "<i>No history yet.</i>"
    
    await update.message.reply_text(panel("📜 Lookup History", content), parse_mode="HTML")


async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    used = get_user_daily_lookups(user_id)
    limit = get_daily_limit(user_id)
    remaining = max(0, limit - used)
    
    content = f"""📊 <b>Daily:</b> {used}/{limit}
⏳ <b>Remaining:</b> {remaining}
🔄 <b>Resets:</b> Midnight"""
    
    await update.message.reply_text(panel("📊 Daily Limit", content), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# ⚙️ ADMIN TOOLS
# ═══════════════════════════════════════════════════════════════




async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /broadcast [message]", parse_mode="HTML")
        return
    
    message = " ".join(context.args)
    users = get_all_users()
    
    sent = 0
    failed = 0
    
    status = await update.message.reply_text("📤 Broadcasting...")
    
    for uid in users:
        try:
            await context.bot.send_message(int(uid), panel("📢 Broadcast", message + get_owner_footer()), 
                                           parse_mode="HTML", disable_web_page_preview=True)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    
    await status.edit_text(panel("✅ Broadcast Complete", f"✅ Sent: {sent}\n❌ Failed: {failed}"), parse_mode="HTML")


async def maintenance_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if not is_owner(update.effective_user.id):
        return
    
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    status = "ON 🔴" if MAINTENANCE_MODE else "OFF 🟢"
    await update.message.reply_text(panel("🔧 Maintenance Mode", f"Status: {status}"), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🔍 INFO FETCHER
# ═══════════════════════════════════════════════════════════════

def parse_and_decorate(text: str, requested_by: str = None) -> str:
    import re
    import json as json_lib
    
    data_list = []
    
    try:
        # 1. Try finding JSON array [ ... ]
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            data_list = json_lib.loads(json_match.group())
        else:
            # 2. Try finding JSON object { ... }
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                parsed = json_lib.loads(json_match.group())
                if "result" in parsed and isinstance(parsed["result"], list):
                    data_list = parsed["result"]
                else:
                    data_list = [parsed]
            else:
                raise ValueError("No JSON found")
    except Exception:
        # 3. Robust Regex Fallback (handles strings and numbers)
        # Matches "key": "value" OR "key": 123
        pattern = r'"(\w+)":\s*(?:"([^"]*)"|(\d+)|true|false|null)'
        matches = re.findall(pattern, text)
        if matches:
            # Clean up matches: (key, val_str, val_int) -> (key, val)
            cleaned_data = {}
            for k, v_str, v_int in matches:
                cleaned_data[k] = v_str if v_str else v_int
            data_list = [cleaned_data]
            
    if not data_list:
        return escape_html(text)
    
    skip_keys = {'header', 'total_records', 'success', 'result', 'data', 'creator', 'developer'}

    
    field_labels = {
    'mobile': '📱 ᴍᴏʙɪʟᴇ',
    'name': '👤 ɴᴀᴍᴇ',
    'fname': '👨 ғᴀᴛʜᴇʀ',
    'address': '📍 ᴀᴅᴅʀᴇss',
    'circle': '📡 ᴄɪʀᴄʟᴇ',
    'email': '📧 ᴇᴍᴀɪʟ',
    'alt': '📞 ᴀʟᴛ',
    'id': '📝 ɪᴅ'
}
    
    formatted_output = []
    
    for i, data in enumerate(data_list, 1):
        lines = ["╭───────────────────╮", f"│🔍 <b>{stylize('User Information')}</b> #{i}│", "╰───────────────────╯\n"]
        
        for key, value in data.items():
            if key.lower() in skip_keys or not str(value).strip():
                continue
                
            label = field_labels.get(key.lower(), f"📝 {stylize(key)}")
            lines.append(f"{label}: <code>{escape_html(str(value))}</code>")
        
        formatted_output.append("\n".join(lines))
    
    final_output = "\n\n".join(formatted_output)
    
    final_output += "\n\n◈ ━━━━━━ ⸙ ━━━━━━ ◈"
    if requested_by:
        final_output += f"\n👤 {stylize('By')}: {requested_by}"
    final_output += f"\n👑 {stylize('Owner')}: <a href=\"tg://openmessage?user_id={OWNER_ID}\">{stylize(OWNER_NAME)}</a>"
    
    return final_output


async def fetch_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    user = update.effective_user
    uid = update.message.text.strip()
    
    if MAINTENANCE_MODE and not is_owner(user.id):
        await update.message.reply_text(panel("🔧 Maintenance", "Try again later."), parse_mode="HTML")
        return
    
    if is_banned(user.id):
        await update.message.reply_text(panel("🚫 Banned", "You are banned."), parse_mode="HTML")
        return
    
    if not is_authorized(user.id):
        content = f"⚠️ Not authorized!\n📩 Contact owner for access.{get_owner_footer()}"
        keyboard = [
    [
        InlineKeyboardButton("👑 ˹ᴄσηᴛᴧᴄᴛ σᴡηєʀ˼", url=f"tg://openmessage?user_id={OWNER_ID}")
    ],
    [
        InlineKeyboardButton("💬 ˹sᴜᴘᴘσʀᴛ ɢʀσᴜᴘ˼", url="https://t.me/II_StarkxRich_II")
    ],
    [
        InlineKeyboardButton("📢 ˹σғғɪᴄɪᴧʟ ᴄʜᴧηηєʟ˼", url="https://t.me/ll_CarelessxCoder_ll"),
        InlineKeyboardButton("🚀 ˹ᴜᴘᴅᴧᴛє ᴄʜᴧηηєʟ˼", url="https://t.me/ROLEX_MODS_45")
    ]
        ]

        await update.message.reply_text(panel("🚫 Access Denied", content), parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
        return
    
    used = get_user_daily_lookups(user.id)
    limit = get_daily_limit(user.id)
    if used >= limit:
        await update.message.reply_text(panel("⏳ Limit Reached", f"Daily limit ({limit}) exceeded.\nTry again tomorrow."), parse_mode="HTML")
        return
    
    if not uid or len(uid) < 3:
        return
    
    loading_msg = await update.message.reply_text(
        panel("⏳ Processing", "<i>Fetching data... Please wait.</i>"), parse_mode="HTML"
    )
    
    try:
        url = BASE_URL.format(uid=uid)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'])
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000) # Reduced timeout
            except:
                pass
            await asyncio.sleep(4) 
            text = await page.inner_text("body")
            await browser.close()
        
        if text and text.strip():
            increment_user_daily(user.id)
            record_lookup(user.id, uid, True)
            add_to_history(user.id, uid, text)
            
            user_mention = get_user_mention(user)
            decorated = parse_and_decorate(text, user_mention)
            
            keyboard = [
                [InlineKeyboardButton("🔄 New Search", callback_data="new"),
                 InlineKeyboardButton("📜 Search History", callback_data="history")]
            ]
            
            await loading_msg.edit_text(decorated, parse_mode="HTML", 
                                        reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
            
            # Log to fixed group
            try:
                log_header = f"🔍 <b>Query:</b> <code>{escape_html(uid)}</code>\n👤 <b>By:</b> {user_mention} (<code>{user.id}</code>)\n\n"
                await context.bot.send_message(LOG_GROUP_ID, log_header + decorated, 
                                               parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                logger.warning(f"Log error: {e}")
        else:
            record_lookup(user.id, uid, False)
            await loading_msg.edit_text(panel("⚠️ No Data", f"No info for <code>{escape_html(uid)}</code>"), parse_mode="HTML")
    
    except Exception as e:
        record_lookup(user.id, uid, False)
        logger.error(f"Fetch error: {e}")
        await loading_msg.edit_text(panel("❌ Error", escape_html(str(e)[:200])), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
# 🔘 CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = query.from_user
    
    if data == "help":
        if is_owner(user.id):
            content = """<b>👑 Owner:</b> /owner

<b>📋 Commands:</b>
/start, /help, /mystats
/history, /limit

Send any number to lookup."""
        else:
            content = """<b>📋 Commands:</b>
/start, /help, /mystats
/history, /limit

Send any number to lookup."""
        await query.edit_message_text(panel("📖 Help", content + get_owner_footer()), 
                                       parse_mode="HTML", disable_web_page_preview=True)
    
    elif data == "mystats":
        stats = get_stats()
        lookups = stats.get("user_lookups", {}).get(str(user.id), 0)
        today_used = get_user_daily_lookups(user.id)
        limit = get_daily_limit(user.id)
        content = f"📊 Total: {lookups}\n📅 Today: {today_used}/{limit}"
        await query.edit_message_text(panel("📊 My Stats", content), parse_mode="HTML")
    
    elif data == "history":
        history = get_user_history(user.id)
        if history:
            lines = [f"• <code>{h['query'][:15]}</code>" for h in history[-10:]]
            content = "\n".join(lines)
        else:
            content = "<i>No history.</i>"
        await query.edit_message_text(panel("📜 History", content), parse_mode="HTML")
    
    elif data == "new":
        await query.edit_message_text(panel("🔍 New Search", "Send any number to lookup."), parse_mode="HTML")
    
    elif data == "premium_cancel":
        await query.edit_message_text(panel("❌ Cancelled", "Premium operation cancelled."), parse_mode="HTML")
    
    elif data.startswith("premium_"):
        # Only owner can use premium buttons
        if not is_owner(user.id):
            await query.answer("❌ Only owner can do this!", show_alert=True)
            return
        
        # Parse: premium_userid_days_tier
        parts = data.split("_")
        if len(parts) == 4:
            _, target_id, days_str, tier = parts
            days = int(days_str)
            
            # Add premium
            premium = get_premium_users()
            expiry = (datetime.now() + timedelta(days=days)).isoformat()
            premium[target_id] = {"expiry": expiry, "tier": tier}
            save_premium_users(premium)
            
            tier_emoji = {"basic": "🥉", "pro": "🥈", "vip": "🥇"}.get(tier, "⭐")
            tier_limits = {"basic": "25", "pro": "50", "vip": "100"}.get(tier, "25")
            
            content = f"""✅ <b>Premium Activated!</b>

👤 <b>User ID:</b> <code>{target_id}</code>
{tier_emoji} <b>Tier:</b> {tier.upper()}
📊 <b>Daily Limit:</b> {tier_limits}/day
⏰ <b>Duration:</b> {days} days"""
            
            await query.edit_message_text(panel("⭐ Premium Added", content), parse_mode="HTML")
            
            # Send DM to user
            try:
                dm = panel("🎉 Premium Activated", f"You've got {tier_emoji} {tier.upper()} premium for {days} days!\n\n📊 Daily Limit: {tier_limits}/day{get_owner_footer()}")
                await context.bot.send_message(int(target_id), dm, parse_mode="HTML", disable_web_page_preview=True)
            except:
                pass


# ═══════════════════════════════════════════════════════════════
# 🚀 MAIN
# ═══════════════════════════════════════════════════════════════

def create_app():
    """Create and configure the application"""
    from telegram.ext import ApplicationBuilder
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    
    app = ApplicationBuilder().token(BOT_TOKEN).request(request).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("owner", owner_command))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("rmsudo", remove_sudo))
    app.add_handler(CommandHandler("sudolist", sudo_list))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("banlist", ban_list))
    app.add_handler(CommandHandler("addpremium", add_premium))
    app.add_handler(CommandHandler("rmpremium", remove_premium))
    app.add_handler(CommandHandler("premiumlist", premium_list))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("mystats", my_stats))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("limit", limit_command))
    app.add_handler(CommandHandler("limit", limit_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("maintenance", maintenance_toggle))
    
    # Callbacks & Messages
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fetch_info))
    
    # Error Handler
    app.add_error_handler(error_handler)
    
    return app


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle specific Telegram errors."""
    
    # Handle Conflict: terminated by other getUpdates request
    if "terminated by other getUpdates request" in str(context.error):
        logger.warning("⚠️ Conflict detected: Another instance is running (Polling overlapping).")
        print("ℹ️ Sleeping for 10s to let the other instance stop...")
        await asyncio.sleep(10)
        return

    # Handle Network Errors
    if "Timed out" in str(context.error) or "ConnectTimeout" in str(context.error):
        logger.warning(f"⚠️ Network timeout: {context.error}")
        return

    logger.error(f"Exception while handling an update: {context.error}")


def start_web_server():
    """Starts a dummy web server to keep Render happy."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running!")
    
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"🌍 Web server started on port {port}")


def check_and_install_playwright():
    """Ensure Playwright browsers are installed at runtime."""
    import subprocess
    try:
        # Check if we can run python
        print("🔍 Checking Playwright browser installation...")
        subprocess.run(["playwright", "install", "chromium"], check=True)
        print("✅ Playwright browsers installed/verified.")
    except Exception as e:
        print(f"⚠️ Failed to install Playwright browsers: {e}")


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not found!")
        return
    
    if not OWNER_ID:
        print("⚠️ OWNER_ID not set!")

    # Start dummy web server for Render
    start_web_server()
    
    # Verify/Install Playwright Runtime
    check_and_install_playwright()
    
    print("🚀 Bot starting with MongoDB...")
    logger.info("Bot started!")
    
    app = create_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()

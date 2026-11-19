import asyncio
import os
import sqlite3
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

TOKEN = os.environ.get("BOT_TOKEN", "8669831808:AAGppcCwyaxfR4g4w9MLbZt4iLwb4v6sPLA")
CHANNEL_USERNAME = "@smartsartaroshxona"
ADMIN_ID = 8052376816
ADMIN_USERNAME = "@norboyevadmen"
WEB_PANEL_URL = os.environ.get("WEB_PANEL_URL", "https://sartaroshuz.onrender.com")
APK_PATH = Path(__file__).parent / "app-release.apk"
API_SECRET = os.environ.get("BOT_API_SECRET", "smart_sartarosh_secret_key")


# --- BAZA ---
def init_db():
    conn = sqlite3.connect("bot_base.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            status TEXT DEFAULT 'active'
        )
    """)
    conn.commit()
    conn.close()


init_db()


def get_db():
    return sqlite3.connect("bot_base.db")


bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- YORDAMCHI FUNKSIYALAR ---
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


def get_bottom_menu(user_id: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📱 Smart Sartaroshxona yuklash")],
        [
            KeyboardButton(text="🌐 Web Panel"),
            KeyboardButton(text="💬 Adminga murojaat"),
        ],
    ]
    if user_id == ADMIN_ID:
        rows.append([KeyboardButton(text="👑 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_web_panel_markup() -> InlineKeyboardMarkup:
    clean_url = WEB_PANEL_URL.strip()
    if clean_url.startswith("https://"):
        btn = InlineKeyboardButton(text="🌐 Web Panelni ochish", web_app=WebAppInfo(url=clean_url))
    else:
        btn = InlineKeyboardButton(text="🌐 Web Panelni ochish", url="https://t.me/smartsartaroshxona")
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


async def show_main_menu(chat_id: int, user_id: int):
    await bot.send_message(
        chat_id,
        f"Assalomu alaykum! Xush kelibsiz.\n"
        f"🆔 Sizning Telegram ID: `{user_id}`\n\n"
        f"Pastki menyudan kerakli bo'limni tanlang:",
        reply_markup=get_bottom_menu(user_id),
        parse_mode="Markdown",
    )


# --- /start VA MAJBURIY OBUNA ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username or ""

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, full_name, username, status) VALUES (?, ?, ?, ?)",
            (user_id, full_name, username, "active"),
        )
    else:
        cursor.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    if not await check_subscription(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Kanalga obuna bo'lish",
                    url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}",
                )
            ],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")],
        ])
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanalimizga obuna bo'lishingiz kerak:",
            reply_markup=keyboard,
        )
        return

    await show_main_menu(message.chat.id, user_id)


@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        await show_main_menu(callback.message.chat.id, callback.from_user.id)
    else:
        await callback.answer("Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)


# --- PASTKI MENYU TUGMALARI ---
@dp.message(F.text == "📱 Smart Sartaroshxona yuklash")
async def menu_download_apk(message: Message):
    user_id = message.from_user.id

    if not await check_subscription(user_id):
        await cmd_start(message)
        return

    if not APK_PATH.exists():
        await message.answer(
            f"❌ APK fayl topilmadi. Admin bilan bog'laning: {ADMIN_USERNAME}"
        )
        return

    await message.answer_document(
        document=FSInputFile(APK_PATH),
        caption="📱 Smart Sartaroshxona dasturi.\nO'rnatish uchun faylni oching.",
        reply_markup=get_bottom_menu(user_id),
    )


@dp.message(F.text == "🌐 Web Panel")
async def menu_web_panel(message: Message):
    user_id = message.from_user.id

    if not await check_subscription(user_id):
        await cmd_start(message)
        return

    await message.answer(
        f"🌐 **Smart Sartaroshxona Web Panel**\n\n"
        f"Manzil: {WEB_PANEL_URL}\n"
        f"Quyidagi tugma orqali Web Panelni ochishingiz mumkin:",
        reply_markup=get_web_panel_markup(),
        parse_mode="Markdown",
    )


@dp.message(F.text == "💬 Adminga murojaat")
async def menu_contact_admin(message: Message):
    user_id = message.from_user.id
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✉️ Adminga yozish",
                url=f"https://t.me/{ADMIN_USERNAME.replace('@', '')}",
            )
        ]
    ])
    await message.answer(
        f"💬 **Adminga murojaat**\n\n"
        f"Savol, taklif yoki muammo bo'yicha adminga murojaat qiling:\n"
        f"👤 Admin: {ADMIN_USERNAME}\n"
        f"🆔 Sizning ID: `{user_id}`",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@dp.message(F.text == "👑 Admin Panel")
async def menu_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Siz admin emassiz!")
        return

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
    active_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'blocked'")
    blocked_users = cursor.fetchone()[0]
    conn.close()

    text = (
        f"👑 **Admin Panel**\n\n"
        f"📊 **Statistika:**\n"
        f"👥 Jami kirganlar: {total_users}\n"
        f"✅ Hozirda faollar: {active_users}\n"
        f"❌ Botni tark etganlar/bloklaganlar: {blocked_users}"
    )
    await message.answer(text, reply_markup=get_bottom_menu(message.from_user.id), parse_mode="Markdown")


# --- WEB SERVER VA 6 XONALI KOD YUBORISH ENDPOINTI ---
async def handle(request):
    return web.Response(text="Bot ishlayapti!")


async def send_verification_code(request: web.Request):
    secret = request.headers.get("X-Bot-Secret", "")
    if secret != API_SECRET:
        return web.json_response({"ok": False, "error": "Ruxsat berilmagan"}, status=401)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Noto'g'ri JSON"}, status=400)

    telegram_id = data.get("telegramId")
    phone = data.get("phone", "")
    code = str(data.get("code", "")).strip()

    if not telegram_id or not code or len(code) != 6:
        return web.json_response(
            {"ok": False, "error": "telegramId va 6 xonali code majburiy"},
            status=400,
        )

    try:
        await bot.send_message(
            chat_id=int(telegram_id),
            text=(
                f"🔐 *Smart Sartaroshxona* tasdiqlash kodi:\n\n"
                f"📱 Raqam: `{phone}`\n"
                f"🔑 6 xonali kod: *`{code}`*\n\n"
                f"⏱ Kod 3 daqiqa amal qiladi. Uni hech kimga bermang."
            ),
            parse_mode="Markdown",
        )
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=400)


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_post("/send-code", send_verification_code)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()


async def main():
    await web_server()
    print("Bot va veb-server muvaffaqiyatli ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import os
import re
import sqlite3
import tempfile
from pathlib import Path

import aiohttp
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BASE_DIR = Path(__file__).parent
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "bot_base.db"))
LOCAL_APK_PATH = Path(os.environ.get("APK_PATH", BASE_DIR / "app-release.apk")
# Token faqat Render Environment'dan olinadi (kod ichida yozilmaydi)
TOKEN = os.environ.get("8669831808:AAGtVxPVrhtuVCoL--ZZly0SsA0VAimyQnA", "").strip()
if not TOKEN:
    raise SystemExit("BOT_TOKEN environment variable kiritilmagan!")

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@smartsartaroshxona")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8052376816"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "@norboyevadmen")
WEB_PANEL_URL = os.environ.get("WEB_PANEL_URL", "https://sartaroshuz.onrender.com")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://sartaroshuz.onrender.com").rstrip("/")
APK_GITHUB_URL = os.environ.get(
    "APK_GITHUB_URL",
    "https://github.com/USERNAME/REPO/releases/latest/download/app-release.apk",
)
API_SECRET = os.environ.get("5446d3ff161880da938d2c56a07f208c", "").strip()
if not API_SECRET:
    logging.warning("BOT_API_SECRET kiritilmagan! Raqamni backend'ga ulash ishlamaydi.")

# --- MENYU TUGMALARI ---
BTN_SHARE = "📱 Raqamni ulashish"
BTN_APK = "📲 Smart Sartaroshxona yuklash"
BTN_WEB = "🌐 Web Panel"
BTN_CONTACT = "💬 Adminga murojaat"
BTN_ADMIN = "👑 Admin Panel"


# --- BAZA ---
def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                status TEXT DEFAULT 'active'
            )
            """
        )
        # Eski bazada phone ustuni bo'lmasa, qo'shamiz
        cols = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        if "phone" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        conn.commit()


def get_db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def get_phone(user_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return row[0] if row and row[0] else None


def set_phone(user_id: int, phone: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()


init_db()

bot = Bot(token=TOKEN)
dp = Dispatcher()


# --- YORDAMCHI FUNKSIYALAR ---
async def check_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in {"member", "administrator", "creator"}
    except Exception as e:
        logging.warning(f"Obunani tekshirishda xato (user_id={user_id}, kanal={CHANNEL_USERNAME}): {e}")
        return False


async def backend_is_linked(chat_id: int) -> bool:
    """Backend'da bu chat_id uchun raqam saqlanganmi (baza o'chib ketgan holat uchun)."""
    if not API_SECRET:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BACKEND_URL}/api/tg-linked",
                params={"chatId": chat_id},
                headers={"X-Bot-Secret": API_SECRET},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    logging.warning(f"tg-linked javobi: {resp.status}")
                    return False
                data = await resp.json()
                return bool(data.get("linked"))
    except Exception as e:
        logging.warning(f"Backend'dan ulanganlikni tekshirishda xato: {e!r}")
        return False


async def link_phone_to_backend(phone: str, chat_id: int) -> bool:
    """Raqam va chat_id ni backend (PostgreSQL) ga yozadi. Vaqtinchalik xatoda 3 marta urinadi."""
    if not API_SECRET:
        logging.error("BOT_API_SECRET yo'q, so'rov yuborilmadi!")
        return False

    for attempt in range(1, 4):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BACKEND_URL}/api/tg-link",
                    json={"phone": phone, "chatId": chat_id},
                    headers={"X-Bot-Secret": API_SECRET},
                    timeout=aiohttp.ClientTimeout(total=60),  # Render uxlab qolgan bo'lsa uyg'onishi uchun
                ) as resp:
                    body = await resp.text()
                    logging.info(f"tg-link javobi (urinish {attempt}): {resp.status} {body[:200]}")
                    if resp.status == 200:
                        return True
                    # 4xx xatolar (401 secret mos emas, 400 noto'g'ri ma'lumot) qayta urinish bilan tuzalmaydi
                    if 400 <= resp.status < 500:
                        return False
        except Exception as e:
            logging.error(f"Raqamni backend'ga ulashda xato (urinish {attempt}): {e!r}")

        if attempt < 3:
            await asyncio.sleep(3)

    return False


def get_bottom_menu(user_id: int) -> ReplyKeyboardMarkup:
    """
    Raqam ulanmagan: foydalanuvchi 4 ta, admin 5 ta tugma.
    Raqam ulangan: "Raqamni ulashish" tugmasi yo'qoladi (3 ta / 4 ta).
    """
    rows = []
    if not get_phone(user_id):
        rows.append([KeyboardButton(text=BTN_SHARE, request_contact=True)])
    rows.append([KeyboardButton(text=BTN_APK)])
    rows.append([KeyboardButton(text=BTN_WEB), KeyboardButton(text=BTN_CONTACT)])
    if user_id == ADMIN_ID:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_web_panel_markup() -> InlineKeyboardMarkup:
    clean_url = WEB_PANEL_URL.strip()
    if clean_url.startswith("https://"):
        btn = InlineKeyboardButton(text="🌐 Web Panelni ochish", web_app=WebAppInfo(url=clean_url))
    else:
        btn = InlineKeyboardButton(text="🌐 Web Panelni ochish", url="https://sartaroshuz.onrender.com")
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


def get_admin_panel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Statistikani yangilash", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🌐 Web Panel", web_app=WebAppInfo(url=WEB_PANEL_URL))],
        ]
    )


def build_subscribe_keyboard() -> InlineKeyboardMarkup:
    channel_slug = CHANNEL_USERNAME.lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{channel_slug}")],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")],
        ]
    )


async def show_main_menu(chat_id: int, user_id: int) -> None:
    if get_phone(user_id):
        hint = "Pastki menyudan kerakli bo'limni tanlang:"
    else:
        hint = (
            "Saytda ro'yxatdan o'tish uchun avval «📱 Raqamni ulashish» tugmasini bosing.\n"
            "Pastki menyudan kerakli bo'limni tanlang:"
        )
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "Assalomu alaykum! Xush kelibsiz.\n"
            f"🆔 Sizning Telegram ID: `{user_id}`\n\n"
            f"{hint}"
        ),
        reply_markup=get_bottom_menu(user_id),
        parse_mode="Markdown",
    )


def get_stats_text() -> str:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'active'")
        active_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE status = 'blocked'")
        blocked_users = cursor.fetchone()[0]

    return (
        "👑 **Admin Panel**\n\n"
        "📊 **Statistika:**\n"
        f"👥 Jami kirganlar: {total_users}\n"
        f"✅ Hozirda faollar: {active_users}\n"
        f"❌ Botni tark etganlar/bloklaganlar: {blocked_users}\n"
        f"🌐 Web Panel: {WEB_PANEL_URL}\n"
        f"👤 Admin: {ADMIN_USERNAME}"
    )


# --- /start VA MAJBURIY OBUNA ---
@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username or ""

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (user_id, full_name, username, status) VALUES (?, ?, ?, ?)",
                (user_id, full_name, username, "active"),
            )
        else:
            cursor.execute(
                "UPDATE users SET full_name = ?, username = ?, status = 'active' WHERE user_id = ?",
                (full_name, username, user_id),
            )
        conn.commit()

    if not await check_subscription(user_id):
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanalimizga obuna bo'lishingiz kerak:",
            reply_markup=build_subscribe_keyboard(),
        )
        return

    # Bazada raqam yo'q bo'lsa, backend'da borligini tekshiramiz (baza o'chib ketgan bo'lishi mumkin)
    if not get_phone(user_id) and await backend_is_linked(message.chat.id):
        set_phone(user_id, "linked")

    await show_main_menu(message.chat.id, user_id)


@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return

    if await check_subscription(callback.from_user.id):
        try:
            await callback.message.delete()
        except Exception:
            pass
        user_id = callback.from_user.id
        if not get_phone(user_id) and await backend_is_linked(callback.message.chat.id):
            set_phone(user_id, "linked")
        await show_main_menu(callback.message.chat.id, user_id)
        await callback.answer()
    else:
        await callback.answer("Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)


# --- RAQAMNI ULASHISH ---
@dp.message(F.contact)
async def on_contact(message: Message) -> None:
    if not message.from_user or not message.contact:
        return

    user_id = message.from_user.id
    contact = message.contact

    if contact.user_id != user_id:
        await message.answer("Faqat o'z raqamingizni ulashing.", reply_markup=get_bottom_menu(user_id))
        return

    if not await check_subscription(user_id):
        await cmd_start(message)
        return

    phone = re.sub(r"\D", "", contact.phone_number or "")
    ok = await link_phone_to_backend(phone, message.chat.id)

    if ok:
        set_phone(user_id, phone)  # shundan keyin "Raqamni ulashish" tugmasi menyudan yo'qoladi
        await message.answer(
            "✅ Raqamingiz saqlandi.\nEndi saytga qaytib, «Kod yuborish» tugmasini bosing.",
            reply_markup=get_bottom_menu(user_id),
        )
    else:
        await message.answer(
            "❌ Raqamni saqlab bo'lmadi. Birozdan keyin qayta urinib ko'ring.",
            reply_markup=get_bottom_menu(user_id),
        )


# --- PASTKI MENYU TUGMALARI ---
@dp.message(F.text == BTN_APK)
async def menu_download_apk(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    if not await check_subscription(user_id):
        await cmd_start(message)
        return

    if LOCAL_APK_PATH.exists():
        await message.answer_document(
            document=FSInputFile(LOCAL_APK_PATH),
            caption="📱 Smart Sartaroshxona dasturi.\nO'rnatish uchun faylni oching.",
            reply_markup=get_bottom_menu(user_id),
        )
        return

    if APK_GITHUB_URL and "USERNAME/REPO" not in APK_GITHUB_URL:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(APK_GITHUB_URL, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as tmp:
                            tmp.write(await resp.read())
                            tmp_path = Path(tmp.name)
                        try:
                            await message.answer_document(
                                document=FSInputFile(tmp_path, filename="Smart_Sartaroshxona.apk"),
                                caption="📱 Smart Sartaroshxona dasturi (GitHub).\nO'rnatish uchun faylni oching.",
                                reply_markup=get_bottom_menu(user_id),
                            )
                            return
                        finally:
                            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            logging.warning(f"GitHub APK yuklashda xato: {e}")

        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📥 APK ni GitHub'dan yuklash", url=APK_GITHUB_URL)]]
        )
        await message.answer(
            "📱 **Smart Sartaroshxona APK**\n\n"
            "Dasturni yuklab olish uchun quyidagi GitHub havolasiga kiring:",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return

    await message.answer(
        f"❌ APK havolasi sozlanmagan. Admin bilan bog'laning: {ADMIN_USERNAME}",
        reply_markup=get_bottom_menu(user_id),
    )


@dp.message(F.text == BTN_WEB)
async def menu_web_panel(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    if not await check_subscription(user_id):
        await cmd_start(message)
        return

    await message.answer(
        "🌐 **Smart Sartaroshxona Web Panel**\n\n"
        f"Manzil: {WEB_PANEL_URL}\n"
        "Quyidagi tugma orqali Web Panelni ochishingiz mumkin:",
        reply_markup=get_web_panel_markup(),
        parse_mode="Markdown",
    )


@dp.message(F.text == BTN_CONTACT)
async def menu_contact_admin(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    admin_slug = ADMIN_USERNAME.lstrip("@")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✉️ Adminga yozish", url=f"https://t.me/{admin_slug}")]]
    )
    await message.answer(
        "💬 **Adminga murojaat**\n\n"
        "Savol, taklif yoki muammo bo'yicha adminga murojaat qiling:\n"
        f"👤 Admin: {ADMIN_USERNAME}\n"
        f"🆔 Sizning ID: `{user_id}`",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


@dp.message(F.text == BTN_ADMIN)
async def menu_admin_panel(message: Message) -> None:
    if not message.from_user:
        return

    if message.from_user.id != ADMIN_ID:
        await message.answer("Siz admin emassiz!")
        return

    await message.answer(
        get_stats_text(),
        reply_markup=get_admin_panel_markup(),
        parse_mode="Markdown",
    )


@dp.callback_query(F.data == "admin_stats")
async def callback_admin_stats(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return

    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            get_stats_text(),
            reply_markup=get_admin_panel_markup(),
            parse_mode="Markdown",
        )
    except Exception:
        pass
    await callback.answer("Statistika yangilandi")


# --- WEB SERVER ---
async def handle(request: web.Request) -> web.Response:
    return web.Response(text="Bot ishlayapti!")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.info(f"Veb-server {port}-portda ishga tushdi.")
    return runner


async def main() -> None:
    runner = await start_web_server()
    try:
        logging.info("Bot polling ishga tushmoqda...")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import datetime
import logging
import os
import sqlite3
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

TOKEN = "8669831808:AAF0sraDDj6xMMOgd9exy8iHym9XgEP6xE0"  # Eski tokenni BotFather orqali yangilang
CHANNEL_USERNAME = "@smartsartaroshxona"
ADMIN_ID = 8052376816
ADMIN_USERNAME = "@norboyevtg"
CARD_NUMBER = "5614 6820 2750 2089"
CARD_HOLDER = "Xomidjonov Q"
APK_PATH = Path(__file__).parent / "app-release.apk"
MONTHLY_PRICE = 9000


# Bazani sozlash
def init_db():
    conn = sqlite3.connect("bot_base.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            balance INTEGER DEFAULT 0,
            trial_end TEXT,
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


class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()


async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


def has_access(balance: int, trial_end_str: str) -> bool:
    trial_end = datetime.datetime.strptime(trial_end_str, "%Y-%m-%d %H:%M:%S")
    return datetime.datetime.now() <= trial_end or balance >= MONTHLY_PRICE


async def show_main_menu(chat_id: int, user_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Hisobim", callback_data="my_account"),
         InlineKeyboardButton(text="📱 APK yuklash", callback_data="get_apk")]
    ])
    if user_id == ADMIN_ID:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_panel")]
        )
    await bot.send_message(
        chat_id, "Assalomu alaykum! Xush kelibsiz. Kerakli bo'limni tanlang:",
        reply_markup=keyboard
    )


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
        trial_end = (datetime.datetime.now() + datetime.timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO users (user_id, full_name, username, trial_end, status) VALUES (?, ?, ?, ?, ?)",
            (user_id, full_name, username, trial_end, "active")
        )
    else:
        cursor.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    if not await check_subscription(user_id):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish",
                                  url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
        ])
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanalimizga obuna bo'lishingiz kerak:",
            reply_markup=keyboard
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


@dp.callback_query(F.data == "my_account")
async def my_account(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance, trial_end FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        await callback.answer("Avval /start buyrug'ini yuboring.", show_alert=True)
        return

    balance, trial_end_str = user
    trial_end = datetime.datetime.strptime(trial_end_str, "%Y-%m-%d %H:%M:%S")
    if datetime.datetime.now() < trial_end:
        left_days = (trial_end - datetime.datetime.now()).days
        trial_status = f"🎁 Bepul sinov muddati: {left_days} kun qoldi\n"
    else:
        trial_status = "❌ Bepul sinov muddati tugagan\n"

    text = (
        f"👤 **Sizning ma'lumotlaringiz:**\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"💰 Balansingiz: **{balance} so'm**\n"
        f"{trial_status}"
        f"📌 Oylik to'lov: **{MONTHLY_PRICE:,} so'm / oy**"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", callback_data="top_up")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query(F.data == "top_up")
async def top_up_menu(callback: CallbackQuery):
    text = (
        f"💳 **Hisobni to'ldirish uchun:**\n\n"
        f"Quyidagi karta raqamiga **{MONTHLY_PRICE:,} so'm** (yoki kerakli miqdor) o'tkazing:\n\n"
        f"💳 Karta: `{CARD_NUMBER}`\n"
        f"👤 Egasi: `{CARD_HOLDER}`\n\n"
        f"Pulni o'tkazgandan so'ng chekni adminga yuboring va ID raqamingizni ayting: {ADMIN_USERNAME}\n\n"
        f"🆔 Sizning ID raqamingiz: `{callback.from_user.id}`"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="my_account")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


# APK yuborish
@dp.callback_query(F.data == "get_apk")
async def get_apk(callback: CallbackQuery):
    user_id = callback.from_user.id

    if not await check_subscription(user_id):
        await callback.answer("Avval kanalga obuna bo'ling!", show_alert=True)
        return

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT balance, trial_end FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        await callback.answer("Avval /start buyrug'ini yuboring.", show_alert=True)
        return

    balance, trial_end_str = user
    if not has_access(balance, trial_end_str):
        await callback.answer(
            "❌ Sinov muddati tugagan yoki balans yetarli emas. Hisobni to'ldiring.",
            show_alert=True
        )
        return

    if not APK_PATH.exists():
        await callback.answer("Fayl topilmadi, admin bilan bog'laning.", show_alert=True)
        return

    await callback.answer()
    await bot.send_document(
        chat_id=callback.message.chat.id,
        document=FSInputFile(APK_PATH),
        caption="📱 Smart Sartaroshxona dasturi.\nO'rnatish uchun faylni oching.",
    )


@dp.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery):
    await callback.message.delete()
    await show_main_menu(callback.message.chat.id, callback.from_user.id)


# --- ADMIN PANEL ---
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!", show_alert=True)
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Foydalanuvchiga pul qo'shish", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="🔙 Asosiy menyu", callback_data="back_home")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query(F.data == "admin_add_balance")
async def admin_add_balance_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("Foydalanuvchining ID raqamini kiriting:")
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.answer()


@dp.message(AdminStates.waiting_for_user_id)
async def admin_get_user_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        target_id = int(message.text)
        await state.update_data(target_id=target_id)
        await message.answer("Qancha pul qo'shmoqchisiz? (Masalan: 9000):")
        await state.set_state(AdminStates.waiting_for_amount)
    except ValueError:
        await message.answer("Iltimos, to'g'ri ID raqamini kiriting (faqat raqam):")


@dp.message(AdminStates.waiting_for_amount)
async def admin_get_amount(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("Iltimos, summani raqam bilan kiriting:")
        return

    data = await state.get_data()
    target_id = data["target_id"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()

    await message.answer(f"✅ Foydalanuvchi (`{target_id}`) balansiga {amount} so'm qo'shildi!")
    await state.clear()

    try:
        await bot.send_message(target_id, f"🎉 Hisobingizga admin tomonidan {amount} so'm qo'shildi!")
    except Exception:
        pass


# --- RENDER UCHUN PORT OCHUVCHI WEB SERVER ---
async def handle(request):
    return web.Response(text="Bot ishlayapti!")


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
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

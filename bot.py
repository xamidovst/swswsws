import asyncio
import json
import os

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

# Render'da Environment Variables bo'limiga yozing:
# BOT_TOKEN, SHOP_ID, SHOP_KEY
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHOP_ID = os.getenv("SHOP_ID", "1")
SHOP_KEY = os.getenv("SHOP_KEY")
PORT = int(os.getenv("PORT", "10000"))
API_URL = "https://bymuslim.shop/API/check.php"

router = Router()


class Pay(StatesGroup):
    amount = State()
    card = State()


async def check_payment(amount: int, last4: str) -> dict:
    payload = {
        "shop_id": str(SHOP_ID),
        "shop_key": SHOP_KEY,
        "amount": str(amount),
        "card": last4,
    }
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(API_URL, json=payload) as resp:
            text = await resp.text()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"status": "error", "message": f"JSON emas: {text[:300]}"}


@router.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Salom! Bu to'lov API uchun test bot.\n\n"
        "/test - to'lovni tekshirish\n"
        "/cancel - bekor qilish"
    )


@router.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Bekor qilindi.")


@router.message(Command("test"))
async def test(m: Message, state: FSMContext):
    await state.set_state(Pay.amount)
    await m.answer("To'lov summasini yozing (masalan: 1000):")


@router.message(Pay.amount)
async def get_amount(m: Message, state: FSMContext):
    text = (m.text or "").replace(" ", "")
    if not text.isdigit() or int(text) <= 0:
        return await m.answer("Summani faqat raqamda yozing, masalan: 1000")
    await state.update_data(amount=int(text))
    await state.set_state(Pay.card)
    await m.answer("To'lov qilgan kartangizning OXIRGI 4 raqamini yozing:")


@router.message(Pay.card, F.text.regexp(r"^\d{4}$"))
async def get_card(m: Message, state: FSMContext):
    data = await state.get_data()
    amount = data["amount"]
    last4 = m.text

    wait = await m.answer("⏳ Tekshirilmoqda...")
    try:
        result = await check_payment(amount, last4)
    except Exception as e:
        await wait.edit_text(f"❌ So'rovda xatolik: {e}")
        await state.clear()
        return

    pretty = json.dumps(result, ensure_ascii=False, indent=2)
    status = str(result.get("status", "")).lower()
    head = (
        "✅ To'lov tasdiqlandi!"
        if status in ("success", "ok", "paid", "true")
        else "❌ To'lov topilmadi yoki xatolik."
    )

    await wait.edit_text(
        f"{head}\n\nSumma: {amount}\nKarta: *{last4}\n\n"
        f"API javobi:\n<pre>{pretty}</pre>",
        parse_mode="HTML",
    )
    await state.clear()


@router.message(Pay.card)
async def bad_card(m: Message):
    await m.answer("Aynan 4 ta raqam yozing, masalan: 5567")


async def start_web_server():
    """Render Web Service port kutadi, shuning uchun kichik server."""
    async def health(request):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()


async def main():
    if not BOT_TOKEN or not SHOP_KEY:
        raise SystemExit("BOT_TOKEN va SHOP_KEY environment variable kerak.")
    await start_web_server()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import settings
import core.database as database
import core.sub_check as sub_check

from bot.handlers.keyboard import router as ReplyKbRouter
from bot.handlers.search import router as searchFilmRouter
from bot.handlers.favorites import router as showLikedRouter
from bot.handlers.admin import router as adminRouter

async def start_userbot():
    await sub_check.userbot.connect()
    if not await sub_check.userbot.is_user_authorized():
        print("⚠️ Userbot не авторизован. Введите номер телефона и код вручную:")   
        await sub_check.userbot.start() 
    print("✅ Userbot успешно запущен!")

async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    await database.init_pools()

    dp.include_router(ReplyKbRouter)
    dp.include_router(showLikedRouter)
    dp.include_router(searchFilmRouter)
    dp.include_router(adminRouter)

    try:
        await start_userbot()
        print("✅ Userbot успешно подключён!")
    except Exception as e:
        print(f"❌ Ошибка запуска userbot: {e}")

    print("🚀 Bot is starting...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
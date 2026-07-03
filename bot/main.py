import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import settings
from core.logger import get_logger

from db.session import engine
from db.models import Base

from bot.handlers.keyboard import router as ReplyKbRouter
from bot.handlers.search import router as searchFilmRouter
from bot.handlers.favorites import router as showLikedRouter
from bot.handlers.admin import router as adminRouter

logger = get_logger(__name__)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def main():
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(ReplyKbRouter)
    dp.include_router(showLikedRouter)
    dp.include_router(searchFilmRouter)
    dp.include_router(adminRouter)

    await init_db()
    logger.info("База данных инициализирована.")

    logger.info("Бот запущен и готов к работе.")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())

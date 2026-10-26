import asyncio
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from core.config import settings
from core.logger import get_logger
from core.botohub import BotoHubClient
from bot.subscriptions import install_subscription_gate

from db.session import engine
from db.models import Base
from db.crud import database

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
    try:
        async with aiohttp.ClientSession() as session:
            client = BotoHubClient(session, settings.BOTOHUB_TOKEN.get_secret_value(),
                                   cache_seconds=settings.BOTOHUB_CACHE_SECONDS)
            dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
            install_subscription_gate(dp, client, database.add_user)
            dp.include_routers(ReplyKbRouter, showLikedRouter, searchFilmRouter, adminRouter)

            await init_db()
            logger.info("База данных инициализирована.")
            logger.info("BotoHub: обязательные подписки включены.")
            logger.info("Бот запущен и готов к работе.")
            await dp.start_polling(bot, close_bot_session=False,
                                   allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())

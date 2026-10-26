"""A single entry gate for all private messages and callback queries."""

import logging
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.botohub import BotoHubClient, BotoHubUnavailable, SubscriptionResult

CHECK_CALLBACK = "bh_check"
PROMPT = ("Чтобы пользоваться FILMWORKS, подпишись на спонсоров ниже 👇\n\n"
          "После подписки нажми «Проверить подписки».")
RETRY_PROMPT = ("Сейчас не удалось проверить подписки. Попробуй ещё раз чуть позже, "
                "нажав кнопку ниже.")
logger = logging.getLogger(__name__)


def subscription_keyboard(result: SubscriptionResult | None) -> InlineKeyboardMarkup:
    rows = []
    if result is not None:
        for index, task in enumerate(result.tasks, start=1):
            label = f"{'✅' if task.completed else '➕'} Спонсор {index}"
            rows.append([InlineKeyboardButton(text=label, url=task.url)])
    rows.append([InlineKeyboardButton(text="✅ Проверить подписки", callback_data=CHECK_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_prompt(event: Message | CallbackQuery, result: SubscriptionResult | None):
    text = PROMPT if result is not None else RETRY_PROMPT
    markup = subscription_keyboard(result)
    if isinstance(event, CallbackQuery):
        message = event.message
        if not isinstance(message, Message):
            return
        if event.data == CHECK_CALLBACK:
            try:
                await message.edit_text(text, reply_markup=markup)
                return
            except TelegramBadRequest as error:
                if "message is not modified" in error.message.lower():
                    return
                # A stale/photo message may not be editable. Send a fresh prompt.
        await message.answer(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, client: BotoHubClient,
                 register_user: Callable[[int, str, str], Awaitable[None]]):
        self.client = client
        self.register_user = register_user

    async def __call__(self, handler, event: Message | CallbackQuery, data):
        message = event.message if isinstance(event, CallbackQuery) else event
        if not isinstance(message, Message) or message.chat.type != "private":
            if isinstance(event, CallbackQuery):
                await event.answer("Открой бота в личных сообщениях.")
            return None
        user = event.from_user
        if user is None or user.is_bot:
            return None
        # Keep statistics inclusive of people who have not yet completed OP.
        await self.register_user(user.id, user.username or "Unknown", user.first_name or "Unknown")
        checking = isinstance(event, CallbackQuery) and event.data == CHECK_CALLBACK
        if checking:
            # Acknowledge immediately, including if the sponsor API is slow.
            await event.answer()
        try:
            result = await self.client.check(user.id, force=checking)
        except BotoHubUnavailable as error:
            logger.warning("BotoHub check unavailable: %s", error)
            if isinstance(event, CallbackQuery) and not checking:
                await event.answer("Проверка подписок временно недоступна.")
            await show_prompt(event, None)
            return None
        if result.allowed:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and not checking:
            await event.answer("Сначала подпишись на спонсоров.")
        await show_prompt(event, result)
        return None


async def subscriptions_verified(callback: CallbackQuery, state: FSMContext):
    from bot.handlers.keyboard import show_home

    # The middleware has just checked this exact Telegram user with force=True.
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text("✅ Подписки проверены. Доступ открыт!")
        except TelegramBadRequest as error:
            if "message is not modified" not in error.message.lower():
                await callback.message.answer("✅ Подписки проверены. Доступ открыт!")
        await show_home(callback.message, state, callback.from_user)


def install_subscription_gate(dp: Dispatcher, client: BotoHubClient, register_user):
    middleware = SubscriptionMiddleware(client, register_user)
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    router = Router(name="botohub")
    router.callback_query.register(subscriptions_verified, F.data == CHECK_CALLBACK)
    dp.include_router(router)

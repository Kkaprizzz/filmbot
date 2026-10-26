from datetime import datetime, timezone
from itertools import count
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, SendPhoto
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.subscriptions import CHECK_CALLBACK, install_subscription_gate, subscription_keyboard
from core.botohub import BotoHubUnavailable, Sponsor, SubscriptionResult

PENDING = SubscriptionResult((Sponsor("https://t.me/channel", "-1001", False),), False, False)
SUCCESS = SubscriptionResult((), True, False)
SKIP = SubscriptionResult((), False, True)
ids = count(1)


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.edit_error = None

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, EditMessageText) and self.edit_error:
            raise TelegramBadRequest(method, self.edit_error)
        if isinstance(method, (SendMessage, SendPhoto)):
            return Message(message_id=next(ids), date=datetime.now(timezone.utc),
                           chat=Chat(id=int(method.chat_id), type="private"),
                           from_user=User(id=bot.id, is_bot=True, first_name="FilmWorks"),
                           text=getattr(method, "text", None))
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""


@pytest_asyncio.fixture
async def app(monkeypatch):
    registrar = AsyncMock()
    home_registrar = AsyncMock()
    monkeypatch.setattr("bot.handlers.keyboard.database.add_user", home_registrar)
    client = SimpleNamespace(check=AsyncMock(return_value=PENDING))
    session = FakeSession()
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", session=session)
    dp = Dispatcher(storage=MemoryStorage(), events_isolation=SimpleEventIsolation())
    install_subscription_gate(dp, client, registrar)
    reached = []
    router = Router()

    @router.message()
    async def message_handler(message: Message):
        reached.append(message.text)

    @router.callback_query()
    async def callback_handler(callback: CallbackQuery):
        reached.append(callback.data)

    dp.include_router(router)
    yield SimpleNamespace(dp=dp, bot=bot, client=client, session=session, reached=reached,
                          registrar=registrar, home_registrar=home_registrar)
    await dp.storage.close()
    await dp.fsm.events_isolation.close()
    await bot.session.close()


async def send_message(app, text, user_id=777, chat_type="private"):
    msg = Message(message_id=next(ids), date=datetime.now(timezone.utc),
                  chat=Chat(id=user_id, type=chat_type),
                  from_user=User(id=user_id, is_bot=False, first_name="User"), text=text)
    await app.dp.feed_update(app.bot, Update(update_id=next(ids), message=msg))


async def send_callback(app, data, user_id=777):
    # Callback message author is the BOT. OP must check the HUMAN who clicked.
    msg = Message(message_id=next(ids), date=datetime.now(timezone.utc),
                  chat=Chat(id=user_id, type="private"),
                  from_user=User(id=app.bot.id, is_bot=True, first_name="Bot"), text="old")
    callback = CallbackQuery(id=str(next(ids)), chat_instance="test", data=data, message=msg,
                             from_user=User(id=user_id, is_bot=False, first_name="User"))
    await app.dp.feed_update(app.bot, Update(update_id=next(ids), callback_query=callback))


@pytest.mark.parametrize("text", ["/start", "🔎 Поиск по коду", "4382", "🎬 Твоя Кинотека", "/admin"])
async def test_unsubscribed_users_cannot_reach_any_message_handler(app, text):
    await send_message(app, text)
    assert app.reached == []
    app.client.check.assert_awaited_once_with(777, force=False)
    assert any(isinstance(call, SendMessage) and call.reply_markup for call in app.session.calls)
    app.registrar.assert_awaited_once_with(777, "Unknown", "User")


@pytest.mark.parametrize("data", ["like_4382", "dislike_4382", "fav:1", "dislikeInF_4382", "admin_add"])
async def test_existing_buttons_cannot_bypass_op(app, data):
    await send_callback(app, data)
    assert app.reached == []
    assert any(isinstance(call, AnswerCallbackQuery) for call in app.session.calls)


@pytest.mark.parametrize("result", [SUCCESS, SKIP])
async def test_completed_or_no_offers_reaches_handlers(app, result):
    app.client.check.return_value = result
    await send_message(app, "4382")
    await send_callback(app, "like_4382")
    assert app.reached == ["4382", "like_4382"]


async def test_retry_refreshes_status_without_authorizing_pending_user(app):
    await send_callback(app, CHECK_CALLBACK)
    assert app.reached == []
    app.client.check.assert_awaited_once_with(777, force=True)
    assert isinstance(app.session.calls[0], AnswerCallbackQuery)
    assert any(isinstance(call, EditMessageText) for call in app.session.calls)


async def test_successful_verification_opens_home_for_human_not_bot(app):
    app.client.check.return_value = SUCCESS
    await send_callback(app, CHECK_CALLBACK)
    app.client.check.assert_awaited_once_with(777, force=True)
    app.home_registrar.assert_awaited_once_with(777, "Unknown", "User")
    assert app.reached == []
    assert any(isinstance(call, SendPhoto) for call in app.session.calls)


@pytest.mark.parametrize("callback", [False, True])
async def test_service_error_blocks_access_but_gives_retry_button(app, callback, caplog):
    app.client.check.side_effect = BotoHubUnavailable("http_401")
    if callback:
        await send_callback(app, CHECK_CALLBACK)
    else:
        await send_message(app, "/start")
    assert app.reached == []
    prompts = [call for call in app.session.calls if isinstance(call, (SendMessage, EditMessageText))]
    assert prompts[-1].reply_markup.inline_keyboard[-1][0].callback_data == CHECK_CALLBACK
    assert "test-integration-token" not in caplog.text


async def test_unchanged_prompt_is_not_an_error(app):
    app.session.edit_error = "Bad Request: message is not modified"
    await send_callback(app, CHECK_CALLBACK)
    assert app.reached == []


async def test_uneditable_prompt_gets_fresh_message(app):
    app.session.edit_error = "Bad Request: there is no text in the message to edit"
    await send_callback(app, CHECK_CALLBACK)
    assert any(isinstance(call, SendMessage) for call in app.session.calls)


async def test_group_messages_cannot_bypass_private_gate(app):
    await send_message(app, "4382", chat_type="group")
    assert app.reached == []
    app.client.check.assert_not_called()


def test_individual_completion_marks_and_all_sponsors_are_displayed():
    result = SubscriptionResult((Sponsor("https://t.me/done", "1", True),
                                 Sponsor("https://t.me/pending", "2", False)), False, False)
    markup = subscription_keyboard(result)
    assert markup.inline_keyboard[0][0].text.startswith("✅")
    assert markup.inline_keyboard[1][0].text.startswith("➕")
    assert markup.inline_keyboard[-1][0].callback_data == CHECK_CALLBACK

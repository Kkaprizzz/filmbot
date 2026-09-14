from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from bot.handlers.search import clear_state
from core.config import settings
from db.crud import database

router = Router()

@router.message(CommandStart())
async def StartHandler(message: Message, state: FSMContext):
    await clear_state(state)
    
    user_id = message.from_user.id
    user_name = message.from_user.username or "Unknown"
    first_name = message.from_user.first_name or "Unknown"
    await database.add_user(user_id, user_name, first_name)
    
    buttons = []
    buttons.append([KeyboardButton(text="🔎 Поиск по коду"), KeyboardButton(text="🎬 Твоя Кинотека")])
    buttons.append([KeyboardButton(text="На главную🏠")])

    if user_id in settings.ADMIN_IDS:
        buttons.append([KeyboardButton(text="📊 Админ панель")])

    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

    await message.reply_photo(photo=FSInputFile("files/adminBanner.jpg"), caption="""🎬 <b>Тот самый бот из рекомендаций</b>\n\n📌 Увидел код вроде 4382 в TikTok или под видео?\n📥 Отправь его сюда — я за секунды найду фильм: название, постер и описание без спойлеров.\n\n💾 Понравился? Добавь в избранное одним нажатием и вернись к нему позже.\n\n<b>Просто. Удобно. По делу.</b> 🍿""",
                              reply_markup=kb, parse_mode="HTML")
    
@router.message(F.text.contains("На главную🏠"))
async def HomeHandler(message: Message, state: FSMContext):
    await StartHandler(message, state)
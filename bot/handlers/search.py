from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import core.database as database
import core.sub_check as sub_check

router = Router()

class SearchStates(StatesGroup):
    Searching = State()
    NotSearching = State()

MENU_BUTTONS = ["🔎 Поиск по коду", "🎬 Твоя Кинотека", "📊 Админ панель", "🏠 На главную"]

async def clear_state(state: FSMContext):
    await state.set_state(SearchStates.NotSearching)

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if await sub_check.check_all_subscriptions(user_id):
        await callback.message.delete()
        await state.set_state(SearchStates.Searching)
        await callback.message.answer("✅ <b>Отлично!</b>\nТеперь введи код фильма в формате (1234) ниже ⬇️", parse_mode="HTML")
    else:
        await callback.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)

@router.message(F.text.contains("🔎 Поиск по коду"))
async def search_film_handler(message: Message, state: FSMContext):
    user_id = message.from_user.id
    sponsors = await database.get_sponsors(only_required=True)
    
    if sponsors:
        if not await sub_check.check_all_subscriptions(user_id):
            buttons = []
            for spon in sponsors:
                url = spon['channelurl_private'] or spon['channelurl_pub']
                buttons.append([InlineKeyboardButton(text=f"Канал {spon['channelname']}", url=url)])
            
            buttons.append([InlineKeyboardButton(text="✅ Я подписался на все каналы", callback_data='check_subscription')])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await message.reply_photo(
                photo="https://ibb.co/BVZVtP91", 
                caption="📌 Перед началом работы необходимо подтвердить подписку...",
                reply_markup=keyboard
            )
            return

    await message.answer("Напиши код ниже в формате (ХХХХ)⬇️", parse_mode="HTML")
    await state.set_state(SearchStates.Searching)

@router.message(SearchStates.Searching)
async def search_handler(message: Message, state: FSMContext):
    code_text = message.text.strip()
    
    # Если нажата кнопка меню - сбрасываем поиск и выходим
    if any(btn in code_text for btn in MENU_BUTTONS):
        await state.clear()
        # Повторно триггерим обработку сообщения, чтобы сработал хендлер кнопки
        return

    if not code_text.isdigit():
        await message.answer("Код должен быть только из цифр! 🔢")
        return
    
    code = int(code_text)
    user_id = message.from_user.id
    result = await database.get_movie_by_code(code)

    if result:
        try:
            title = result['title']
            description = result['description']
            image_url = result['image_url']
            
            liked_codes = await database.get_liked_movies(user_id)
            
            kb_btns = []
            if code not in liked_codes:
                kb_btns.append([InlineKeyboardButton(text="❤️ Добавить в избранное", callback_data=f"like_{code}")])
            else:
                kb_btns.append([InlineKeyboardButton(text="💔 Убрать из избранного", callback_data=f"dislike_{code}")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=kb_btns)

            await message.reply_photo(
                image_url,
                caption=f"Название: <b>{title}</b>\n\n<b>{description}</b>",
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Ошибка при отправке фильма: {e}")
            await message.answer("Произошла ошибка при обработке запроса. Попробуйте позже.")
    else:
        await message.answer("❌🎬 <b>Фильм не найден.</b>\nПопробуй другой код! 😊", parse_mode="HTML")

@router.callback_query(F.data.startswith('like_'))
async def like_movie(callback: CallbackQuery):
    code = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    await database.add_liked_movie(user_id, code)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💔 Убрать из избранного", callback_data=f"dislike_{code}")]])
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer("Добавлено в Кинотеку! ✨")

@router.callback_query(F.data.startswith('dislike_'))
async def dislike_movie(callback: CallbackQuery):
    code = int(callback.data.split('_')[1])
    user_id = callback.from_user.id
    await database.remove_liked_movie(user_id, code)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❤️ Добавить в избранное", callback_data=f"like_{code}")]])
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer("Удалено из Кинотеки.")
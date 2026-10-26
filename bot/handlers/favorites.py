from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, CallbackQuery
from aiogram.fsm.context import FSMContext
from bot.handlers.search import clear_state
from db.crud import database

router = Router()

@router.message(F.text.contains("🎬 Твоя Кинотека"))
async def liked_cmd(message: Message, state: FSMContext):
    user_id = message.from_user.id
    liked_codes = await database.get_liked_movies(user_id)

    if liked_codes:
        index = 0
        code = liked_codes[index]
        result = await database.get_movie_by_code(code)

        if result:
            title = result.title
            description = result.description
            image_url = result.image_url

            text = f"<b>{title}</b>\n\n{description}"
            
            nav_buttons = []
            if index > 0:
                nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"fav:{index - 1}"))
            if index < len(liked_codes) - 1:
                nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"fav:{index + 1}"))
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💔 Убрать из избранного", callback_data=f"dislikeInF_{code}")],
                nav_buttons
            ])

            try:
                if message.photo: # If it's already a photo message (e.g. from callback)
                    media = InputMediaPhoto(media=image_url, caption=text, parse_mode="HTML")
                    await message.edit_media(media=media, reply_markup=keyboard)
                else:
                    await message.answer_photo(photo=image_url, caption=text, parse_mode="HTML", reply_markup=keyboard)
            except Exception:
                await message.answer_photo(photo=image_url, caption=text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer("В твоей Кинотеке пока пусто. Сохраняй фильмы, чтобы они появились здесь! 🎬💤")

@router.callback_query(lambda c: c.data.startswith("fav:"))
async def scroll_favorites(callback: CallbackQuery):
    user_id = callback.from_user.id
    liked_codes = await database.get_liked_movies(user_id)

    index = int(callback.data.split(":")[1])
    if index < 0 or index >= len(liked_codes):
        await callback.answer("Больше фильмов нет.")
        return

    code = liked_codes[index]
    result = await database.get_movie_by_code(code)
    if not result:
        await callback.answer("Фильм не найден.")
        return

    title = result.title
    description = result.description
    image_url = result.image_url
    text = f"<b>{title}</b>\n\n{description}"

    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"fav:{index - 1}"))
    if index < len(liked_codes) - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"fav:{index + 1}"))
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💔 Убрать из избранного", callback_data=f"dislikeInF_{code}")],
        nav_buttons
    ])

    media = InputMediaPhoto(media=image_url, caption=text, parse_mode="HTML")
    await callback.message.edit_media(media, reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("dislikeInF_"))
async def dislike_liked_film(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    code = int(callback.data.split("_")[1])
    await database.remove_liked_movie(user_id, code)
    await callback.answer("Удалено из Кинотеки.")
    
    # Check if there are still liked movies
    liked_codes = await database.get_liked_movies(user_id)
    if not liked_codes:
        await callback.message.delete()
        await callback.message.answer("В твоей Кинотеке больше ничего нет. 🎬💤")
    else:
        # Show first movie again
        await liked_cmd(callback.message, state)
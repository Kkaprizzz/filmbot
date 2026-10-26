import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from bot.handlers.search import clear_state
from db.crud import database
from core.config import settings

router = Router()

class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in settings.ADMIN_IDS

class AdminStates(StatesGroup):
    add_title = State()
    add_desc = State()
    add_photo = State()
    confirm_save = State()
    manage_find = State()
    # Рассылка
    broadcast_msg = State()
    broadcast_btn_text = State()
    broadcast_btn_url = State()
    broadcast_confirm = State()

# --- КЛАВИАТУРЫ ---

async def get_admin_main_text():
    stats = await database.get_statistics()
    return (f"🛠 <b>Панель администратора</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"👤 Пользователей: <code>{stats['users_count']}</code>\n"
            f"🎬 Фильмов в базе: <code>{stats['films_count']}</code>\n\n"
            f"Выберите действие ниже:")

def get_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить фильм", callback_data="admin_add")],
        [InlineKeyboardButton(text="⚙️ Управление фильмами", callback_data="admin_manage")],
        [InlineKeyboardButton(text="🚀 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="admin_refresh")]
    ])

def get_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
    ])

# --- ОБРАБОТЧИКИ МЕНЮ ---

@router.message(F.text == "📊 Админ панель", IsAdmin())
@router.message(Command("admin"), IsAdmin())
async def admin_start(message: Message, state: FSMContext):
    await clear_state(state)
    text = await get_admin_main_text()
    await message.answer(text, reply_markup=get_admin_kb(), parse_mode="HTML")

@router.callback_query(F.data == "admin_refresh", IsAdmin())
async def admin_refresh(callback: CallbackQuery):
    text = await get_admin_main_text()
    try:
        await callback.message.edit_text(text, reply_markup=get_admin_kb(), parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            await callback.answer("Данные актуальны ✅")
        else:
            raise e

@router.callback_query(F.data == "admin_cancel", IsAdmin())
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = await get_admin_main_text()
    await callback.message.answer("🛑 Действие отменено.")
    await callback.message.answer(text, reply_markup=get_admin_kb(), parse_mode="HTML")

# --- РАССЫЛКА ---

@router.callback_query(F.data == "admin_broadcast", IsAdmin())
async def broadcast_init(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_msg)
    await callback.message.edit_text("📢 <b>Режим рассылки</b>\n\nОтправьте сообщение (текст + фото), которое увидят все пользователи. Поддерживается <b>HTML-разметка</b>.", 
                                     reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(AdminStates.broadcast_msg, IsAdmin())
async def broadcast_msg_received(message: Message, state: FSMContext):
    photo = message.photo[-1].file_id if message.photo else None
    # Используем html_text чтобы сохранить разметку
    text = message.html_text
    await state.update_data(b_text=text, b_photo=photo, b_btn_text=None, b_btn_url=None)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, добавить", callback_data="bc_add_btn")],
        [InlineKeyboardButton(text="❌ Нет, без кнопки", callback_data="bc_no_btn")]
    ])
    await message.answer("Нужна ли кнопка-ссылка к этому посту?", reply_markup=kb)

@router.callback_query(F.data == "bc_add_btn", IsAdmin())
async def bc_btn_text_step(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.broadcast_btn_text)
    await callback.message.edit_text("📝 Введите <b>Текст кнопки</b>:", reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(AdminStates.broadcast_btn_text, IsAdmin())
async def bc_btn_url_step(message: Message, state: FSMContext):
    await state.update_data(b_btn_text=message.text)
    await state.set_state(AdminStates.broadcast_btn_url)
    await message.answer("🔗 Введите <b>URL-ссылку</b> для кнопки (например, https://google.com):", reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(AdminStates.broadcast_btn_url, IsAdmin())
async def bc_preview(message: Message, state: FSMContext):
    if not message.text.startswith("http"):
        return await message.answer("❌ Ссылка должна начинаться с http:// или https://. Попробуйте еще раз:")
    
    await state.update_data(b_btn_url=message.text)
    await bc_show_preview(message, state)

@router.callback_query(F.data == "bc_no_btn", IsAdmin())
async def bc_no_btn(callback: CallbackQuery, state: FSMContext):
    await bc_show_preview(callback.message, state)

async def bc_show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    text = data['b_text']
    photo = data['b_photo']
    btn_text = data.get('b_btn_text')
    btn_url = data.get('b_btn_url')
    
    kb = None
    if btn_text and btn_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=btn_url)]])
    
    await message.answer("👀 <b>ПРЕДПРОСМОТР РАССЫЛКИ:</b>")
    if photo:
        await message.answer_photo(photo, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Запустить рассылку", callback_data="bc_start")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
    ])
    await message.answer("Запускаем?", reply_markup=confirm_kb)
    await state.set_state(AdminStates.broadcast_confirm)

@router.callback_query(F.data == "bc_start", AdminStates.broadcast_confirm)
async def broadcast_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    text = data['b_text']
    photo = data['b_photo']
    btn_text = data.get('b_btn_text')
    btn_url = data.get('b_btn_url')
    await state.clear()
    
    markup = None
    if btn_text and btn_url:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=btn_url)]])
    
    users = await database.get_all_users()
    await callback.message.edit_text(f"🚀 Рассылка запущена на <b>{len(users)}</b> пользователей...", parse_mode="HTML")
    
    count = 0
    blocked = 0
    errors = 0
    
    for user in users:
        try:
            if photo:
                await bot.send_photo(user.user_id, photo, caption=text, parse_mode="HTML", reply_markup=markup)
            else:
                await bot.send_message(user.user_id, text, parse_mode="HTML", reply_markup=markup)
            count += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                if photo: await bot.send_photo(user.user_id, photo, caption=text, parse_mode="HTML", reply_markup=markup)
                else: await bot.send_message(user.user_id, text, parse_mode="HTML", reply_markup=markup)
                count += 1
            except: errors += 1
        except Exception:
            errors += 1
        
        await asyncio.sleep(0.05)
    
    await callback.message.answer(f"🏁 <b>Рассылка завершена!</b>\n\n"
                                  f"✅ Доставлено: <code>{count}</code>\n"
                                  f"🚫 Заблокировали бота: <code>{blocked}</code>\n"
                                  f"⚠️ Ошибки: <code>{errors}</code>", parse_mode="HTML")
    
    text = await get_admin_main_text()
    await callback.message.answer(text, reply_markup=get_admin_kb(), parse_mode="HTML")

# --- ДОБАВЛЕНИЕ / РЕДАКТИРОВАНИЕ ФИЛЬМОВ ---

@router.callback_query(F.data == "admin_add", IsAdmin())
async def add_film_init(callback: CallbackQuery, state: FSMContext):
    code = await database.get_free_code()
    await state.update_data(code=code, mode="add")
    await state.set_state(AdminStates.add_title)
    await callback.message.edit_text(f"📝 Начинаем добавление.\nАвтоматически выбран код: <b>{code}</b>\n\nВведите <b>Название</b> фильма:", 
                                     reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(AdminStates.add_title, IsAdmin())
async def add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminStates.add_desc)
    await message.answer("📖 Теперь введите <b>Описание</b> фильма:", reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(AdminStates.add_desc, IsAdmin())
async def add_desc(message: Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await state.set_state(AdminStates.add_photo)
    await message.answer("🖼 Отправьте <b>Фото</b> (картинкой) или ссылку на него:", reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(AdminStates.add_photo, IsAdmin())
async def add_preview(message: Message, state: FSMContext):
    photo = message.photo[-1].file_id if message.photo else message.text
    await state.update_data(photo=photo)
    data = await state.get_data()

    await message.answer("👀 <b>ПРЕДПРОСМОТР:</b>\nТак сообщение будет выглядеть для пользователя 👇")
    
    preview_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❤️", callback_data="none")]])
    
    await message.answer_photo(
        photo=photo,
        caption=f"Название: <b>{data['title']}</b>\n\n<b>{data['desc']}</b>",
        parse_mode="HTML",
        reply_markup=preview_kb
    )

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="save_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
    ])
    await message.answer("Все верно? Сохраняем в базу?", reply_markup=confirm_kb)
    await state.set_state(AdminStates.confirm_save)

@router.callback_query(F.data == "save_confirm", AdminStates.confirm_save)
async def save_to_db(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    await database.add_movie(data['code'], data['title'], data['desc'], data['photo'])
    res_text = f"✅ Данные фильма <code>{data['code']}</code> сохранены!"

    await state.clear()
    await callback.message.answer(res_text, parse_mode="HTML")
    text = await get_admin_main_text()
    await callback.message.answer(text, reply_markup=get_admin_kb(), parse_mode="HTML")
    await callback.message.delete()

# --- УПРАВЛЕНИЕ ФИЛЬМАМИ ---

@router.callback_query(F.data == "admin_manage", IsAdmin())
async def manage_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.manage_find)
    await callback.message.edit_text("🔍 Введите <b>Код</b> фильма для редактирования или удаления:", 
                                     reply_markup=get_cancel_kb(), parse_mode="HTML")

@router.message(AdminStates.manage_find, IsAdmin())
async def manage_find(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Введите числовой код!")
    
    movie = await database.get_movie_by_code(int(message.text))
    if not movie:
        return await message.answer("❌ Фильм не найден в базе.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_{movie.code}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{movie.code}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_cancel")]
    ])

    await message.answer_photo(
        photo=movie.image_url,
        caption=f"📝 <b>Управление фильмом</b>\nКод: <code>{movie.code}</code>\nНазвание: {movie.title}",
        reply_markup=kb, parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("del_"), IsAdmin())
async def delete_movie(callback: CallbackQuery):
    code = int(callback.data.split("_")[1])
    await database.delete_movie(code)
    await callback.answer("Удалено!", show_alert=True)
    await callback.message.delete()
    text = await get_admin_main_text()
    await callback.message.answer(text, reply_markup=get_admin_kb(), parse_mode="HTML")

@router.callback_query(F.data.startswith("edit_"), IsAdmin())
async def edit_movie_init(callback: CallbackQuery, state: FSMContext):
    code = int(callback.data.split("_")[1])
    await state.update_data(code=code, mode="edit")
    await state.set_state(AdminStates.add_title)
    await callback.message.answer(f"📝 Редактируем код <b>{code}</b>\nВведите НОВОЕ название:", parse_mode="HTML")
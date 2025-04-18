import json
import os
import logging
import asyncio
import time
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

from config import TOKEN, CHANNEL_ID, ADMIN_ID
from messages import LANGUAGES, TEXTS, CATEGORIES, SERVICES, NATIONALITIES

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)

class Form(StatesGroup):
    language = State()
    category = State()
    service = State()
    nationality = State()
    custom_nationality = State()
    name = State()
    phone = State()
    comment = State()

def save_request(request_data):
    file_path = "data/requests.json"
    os.makedirs("data", exist_ok=True)
    max_requests = 1000  # Максимальное количество хранимых запросов

    try:
        requests = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    requests = json.load(f)
                    # Ограничиваем количество хранимых запросов
                    if len(requests) >= max_requests:
                        requests = requests[-max_requests:]
                except json.JSONDecodeError:
                    logging.error("Failed to load requests.json, creating new file")
                    requests = []

        requests.append(request_data)

        # Используем временный файл для безопасной записи
        temp_file = f"{file_path}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(requests, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, file_path)
    except Exception as e:
        logging.error(f"Error saving request: {e}")

async def set_commands():
    commands = [
        types.BotCommand(command="start", description="🚀 Start Bot / Запустить бота"),
        types.BotCommand(command="about", description="ℹ️ О нас / About Us")
    ]
    await bot.delete_my_commands()  # Удаляем старые команды
    await bot.set_my_commands(commands)  # Устанавливаем новые

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Создаем кнопки для языков
    lang_buttons = [[InlineKeyboardButton(text=lang_name, callback_data=f"lang_{lang_code}")]
                   for lang_code, lang_name in LANGUAGES.items()]
    # Добавляем кнопку "О нас"
    about_button = [InlineKeyboardButton(text="ℹ️ О нас / About Us", callback_data="show_about")]
    # Объединяем все кнопки
    all_buttons = lang_buttons + [about_button]
    markup = InlineKeyboardMarkup(inline_keyboard=all_buttons)
    await message.answer(TEXTS["start"][list(LANGUAGES.keys())[0]], reply_markup=markup)

@dp.callback_query(lambda c: c.data == "show_about")
async def show_about(callback_query: types.CallbackQuery):
    from messages import ABOUT_TEXT
    await callback_query.message.edit_text(ABOUT_TEXT, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start")]]
    ))

@dp.callback_query(lambda c: c.data == "back_to_start")
async def back_to_start(callback_query: types.CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=lang_name, callback_data=f"lang_{lang_code}")
    ] for lang_code, lang_name in LANGUAGES.items()] + [
        [InlineKeyboardButton(text="ℹ️ О нас / About Us", callback_data="show_about")]
    ])
    await callback_query.message.edit_text(TEXTS["start"][list(LANGUAGES.keys())[0]], reply_markup=markup)

@dp.callback_query(F.data.startswith("lang_"))
async def process_language(callback_query: types.CallbackQuery, state: FSMContext):
    lang = callback_query.data.split('_')[1]
    await state.update_data(language=lang)

    # Удаляем сообщение с инлайн клавиатурой
    await callback_query.message.delete()

    buttons = [[KeyboardButton(text=category)] for category in CATEGORIES[lang]]
    buttons.append([KeyboardButton(text=TEXTS["contact_admin"][lang])])
    buttons.append([KeyboardButton(text=TEXTS["back"][lang])])
    markup = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await callback_query.message.answer(TEXTS["choose_category"][lang], reply_markup=markup)
    await state.set_state(Form.category)
    await callback_query.answer()

@dp.message(Form.category)
async def process_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language')

    if message.text == TEXTS["contact_admin"][lang]:
        user_link = f"@{message.from_user.username}" if message.from_user.username else f"[ID: {message.from_user.id}](tg://user?id={message.from_user.id})"
        notification = f"📩 Запрос на связь\n👤 От пользователя: {user_link}"
        try:
            await bot.send_message(CHANNEL_ID, notification, parse_mode="Markdown")
            await message.answer(TEXTS["thanks"][lang], reply_markup=types.ReplyKeyboardRemove())
            # Show language selection menu again
            lang_buttons = [[InlineKeyboardButton(text=lang_name, callback_data=f"lang_{lang_code}")]
                          for lang_code, lang_name in LANGUAGES.items()]
            about_button = [InlineKeyboardButton(text="ℹ️ О нас / About Us", callback_data="show_about")]
            markup = InlineKeyboardMarkup(inline_keyboard=lang_buttons + [about_button])
            await message.answer(TEXTS["start"][list(LANGUAGES.keys())[0]], reply_markup=markup)
            await state.clear()
        except Exception as e:
            logging.error(f"Failed to send contact request: {e}")
        return

    if message.text == TEXTS["back"][lang]:
        # Сначала убираем клавиатуру с категориями
        await message.answer("👌", reply_markup=types.ReplyKeyboardRemove())
        # Показываем меню выбора языка
        lang_buttons = [[InlineKeyboardButton(text=lang_name, callback_data=f"lang_{lang_code}")]
                       for lang_code, lang_name in LANGUAGES.items()]
        about_button = [InlineKeyboardButton(text="ℹ️ О нас / About Us", callback_data="show_about")]
        markup = InlineKeyboardMarkup(inline_keyboard=lang_buttons + [about_button])
        await message.answer(TEXTS["start"][list(LANGUAGES.keys())[0]], reply_markup=markup)
        await state.clear()
        return

    if message.text not in CATEGORIES[lang]:
        await message.reply(TEXTS["unknown_command"][lang])
        return

    await state.update_data(category=message.text)
    buttons = [[KeyboardButton(text=service)] for service in SERVICES[message.text]]
    buttons.append([KeyboardButton(text=TEXTS["back"][lang])])
    markup = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await message.answer(TEXTS["choose_service"][lang], reply_markup=markup)
    await state.set_state(Form.service)

@dp.message(Form.service)
async def process_service(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language')
    category = data.get('category')

    if message.text == TEXTS["back"][lang]:
        buttons = [[KeyboardButton(text=cat)] for cat in CATEGORIES[lang]]
        buttons.append([KeyboardButton(text=TEXTS["back"][lang])])
        markup = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        await message.answer(TEXTS["choose_category"][lang], reply_markup=markup)
        await state.set_state(Form.category)
        return

    if message.text not in SERVICES[category]:
        await message.reply(TEXTS["unknown_command"][lang])
        return

    await state.update_data(service=message.text)
    buttons = [[KeyboardButton(text=nationality)] for nationality in NATIONALITIES[lang]]
    buttons.append([KeyboardButton(text=TEXTS["back"][lang])])
    markup = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await message.answer(TEXTS["choose_nationality"][lang], reply_markup=markup)
    await state.set_state(Form.nationality)

@dp.message(Form.nationality)
async def process_nationality(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language')

    if message.text == TEXTS["back"][lang]:
        category = data.get('category')
        buttons = [[KeyboardButton(text=service)] for service in SERVICES[category]]
        buttons.append([KeyboardButton(text=TEXTS["back"][lang])])
        markup = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        await message.answer(TEXTS["choose_service"][lang], reply_markup=markup)
        await state.set_state(Form.service)
        return

    if message.text in ["🏳️ Другая страна", "🏳️ Інша країна", "🏳️ Inny kraj", "🏳️ Other Country"]:
        await message.answer(TEXTS["enter_country"][lang], reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(Form.custom_nationality)
        return

    await state.update_data(nationality=message.text)
    await message.answer(TEXTS["ask_name"][lang], reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Form.name)

@dp.message(Form.custom_nationality)
async def process_custom_nationality(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language')

    await state.update_data(nationality=message.text)
    await message.answer(TEXTS["ask_name"][lang])
    await state.set_state(Form.name)

@dp.message(Form.name)
async def process_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language')

    if message.text == TEXTS["back"][lang]:
        markup = ReplyKeyboardMarkup(keyboard=[[
            KeyboardButton(text=nationality)
        ] for nationality in NATIONALITIES[lang]] + [[KeyboardButton(text=TEXTS["back"][lang])]], resize_keyboard=True)
        await message.answer(TEXTS["choose_nationality"][lang], reply_markup=markup)
        await state.set_state(Form.nationality)
        return

    await state.update_data(name=message.text)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=TEXTS["back"][lang])]], resize_keyboard=True)
    await message.answer(TEXTS["ask_phone"][lang], reply_markup=markup)
    await state.set_state(Form.phone)

# Защита от флуда
_flood_control = {}
_flood_limit = 5  # сообщений
_flood_timeout = 60  # секунд
_cleanup_interval = 300  # очистка каждые 5 минут

def cleanup_flood_control():
    current_time = time.time()
    expired = [uid for uid, data in _flood_control.items() 
              if current_time - data["first_msg"] > _flood_timeout]
    for uid in expired:
        del _flood_control[uid]

def is_flood(user_id: int) -> bool:
    current_time = time.time()
    
    # Периодическая очистка
    if random.random() < 0.1:  # 10% шанс очистки при каждой проверке
        cleanup_flood_control()
    
    if user_id not in _flood_control:
        _flood_control[user_id] = {"count": 1, "first_msg": current_time}
        return False

    data = _flood_control[user_id]
    if current_time - data["first_msg"] > _flood_timeout:
        _flood_control[user_id] = {"count": 1, "first_msg": current_time}
        return False

    data["count"] += 1
    return data["count"] > _flood_limit

@dp.message(Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    if is_flood(message.from_user.id):
        await message.answer("⚠️ Слишком много сообщений. Пожалуйста, подождите минуту.")
        return

    data = await state.get_data()
    lang = data.get('language')

    if message.text == TEXTS["back"][lang]:
        await message.answer(TEXTS["ask_name"][lang])
        await state.set_state(Form.name)
        return

    await state.update_data(phone=message.text)
    markup = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=TEXTS["skip"][lang])],
        [KeyboardButton(text=TEXTS["back"][lang])]
    ], resize_keyboard=True)
    await message.answer(TEXTS["ask_comment"][lang], reply_markup=markup)
    await state.set_state(Form.comment)

@dp.message(Form.comment)
async def process_comment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get('language')

    if message.text == TEXTS["back"][lang]:
        await message.answer(TEXTS["ask_phone"][lang])
        await state.set_state(Form.phone)
        return
        
    comment = "—" if message.text == TEXTS["skip"][lang] else message.text
    user_data = await state.get_data()
    user_data.update({
        'comment': comment,
        'telegram_id': message.from_user.id,
        'username': message.from_user.username,
        'timestamp': message.date.strftime("%d.%m.%Y %H:%M:%S")
    })

    save_request(user_data)

    # Send notification to channel if configured
    if CHANNEL_ID:
        user_link = f"@{user_data.get('username')}" if user_data.get('username') else f"[ID: {user_data['telegram_id']}](tg://user?id={user_data['telegram_id']})"
        notification = (
            f"📋 Новая заявка\n\n"
            f"📁 Категория: {user_data['category']}\n"
            f"🔍 Услуга: {user_data['service']}\n"
            f"👤 Имя: {user_data['name']}\n"
            f"📞 Телефон: {user_data['phone']}\n"
            f"💭 Комментарий: {user_data.get('comment', '—')}\n"
            f"🌍 Страна: {user_data['nationality']}\n"
            f"🔗 Telegram: {user_link}"
        )
        try:
            await bot.send_message(CHANNEL_ID, notification, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send notification to channel: {e}")

    await message.answer(TEXTS["thanks"][lang], reply_markup=types.ReplyKeyboardRemove())
    
    # Show language selection menu again
    lang_buttons = [[InlineKeyboardButton(text=lang_name, callback_data=f"lang_{lang_code}")]
                   for lang_code, lang_name in LANGUAGES.items()]
    about_button = [InlineKeyboardButton(text="ℹ️ О нас / About Us", callback_data="show_about")]
    markup = InlineKeyboardMarkup(inline_keyboard=lang_buttons + [about_button])
    await message.answer(TEXTS["start"][list(LANGUAGES.keys())[0]], reply_markup=markup)
    await state.clear()

@dp.message(Command("admin"))
async def handle_admin(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID and message.from_user.username != "EbZakhar":
        await message.answer("❌ У вас нет доступа к панели администратора.")
        return
    from admin_panel import admin_panel
    await admin_panel(message, state)

@dp.message(Command("about"))
async def cmd_about(message: types.Message):
    from messages import ABOUT_TEXT
    await message.answer(ABOUT_TEXT)

@dp.message()
async def handle_message(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    # Если это состояние ожидания ответа от админа
    if current_state == "AdminState:waiting_for_reply":
        from admin_panel import send_reply
        await send_reply(message, state)
        return

    # First remove the keyboard
    await message.answer("👌", reply_markup=types.ReplyKeyboardRemove())
    
    # Then show language selection menu
    lang_buttons = [[InlineKeyboardButton(text=lang_name, callback_data=f"lang_{lang_code}")]
                   for lang_code, lang_name in LANGUAGES.items()]
    about_button = [InlineKeyboardButton(text="ℹ️ О нас / About Us", callback_data="show_about")]
    markup = InlineKeyboardMarkup(inline_keyboard=lang_buttons + [about_button])
    await message.answer(TEXTS["start"][list(LANGUAGES.keys())[0]], reply_markup=markup)
    await state.clear()

async def main():
    try:
        from admin_panel import register_admin_handlers
        await register_admin_handlers(dp)
        await set_commands()

        logging.info("Bot started")
        await dp.start_polling(bot, allowed_updates=[
            "message",
            "callback_query",
        ])
    except Exception as e:
        logging.error(f"Critical error: {e}")
        # Перезапуск бота при критической ошибке
        await asyncio.sleep(5)
        await main()

from aiohttp import web

async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("Web server started on http://0.0.0.0:8080")

if __name__ == '__main__':
    async def start_services():
        await asyncio.gather(
            main(),
            start_web_server()
        )
    
    asyncio.run(start_services())
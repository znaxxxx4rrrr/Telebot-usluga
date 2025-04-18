import datetime
import logging
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_ID
import json
import os

router = Router()
DATA_PATH = "data/requests.json"

# Add missing import
import time

class AdminState(StatesGroup):
    waiting_for_reply = State()

_request_cache = {}
_cache_timestamp = 0
_cache_lifetime = 300  # увеличим до 5 минут для снижения нагрузки
_last_file_mtime = 0

def load_last_requests(limit=5):
    global _request_cache, _cache_timestamp, _last_file_mtime
    current_time = time.time()
    
    try:
        current_mtime = os.path.getmtime(DATA_PATH)
    except OSError:
        current_mtime = 0
    
    # Используем кэш если он не устарел и файл не изменился
    if (current_time - _cache_timestamp < _cache_lifetime and 
        _request_cache and current_mtime == _last_file_mtime):
        return _request_cache[:limit]
        
    try:
        if not os.path.exists(DATA_PATH):
            return []
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                # Валидация и сортировка данных
                valid_data = [
                    req for req in data 
                    if isinstance(req, dict) and all(k in req for k in ['timestamp', 'name', 'phone'])
                ]
                _request_cache = sorted(valid_data, key=lambda x: x.get('timestamp', ''), reverse=True)
                _cache_timestamp = current_time
                return _request_cache[:limit]
            except json.JSONDecodeError:
                logging.error("Corrupted requests.json file")
                return []
    except Exception as e:
        logging.error(f"Error loading requests: {e}")
        return []

def save_answer_log(user_id, message):
    try:
        log_path = "data/answers.json"
        os.makedirs("data", exist_ok=True)
        
        log = []
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
                with open(log_path, "r", encoding="utf-8") as f:
                    log = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            logging.error(f"Error reading answer log: {str(e)}")

        log.append({
            "to": user_id,
            "message": message,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        if len(log) > 1000:
            log = log[-1000:]

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving answer log: {e}")

async def register_admin_handlers(dp):
    dp.include_router(router)

@router.message(Command("admin", ignore_case=True))
async def admin_panel(message: types.Message, state: FSMContext):
    logging.info(f"Admin access attempt - User ID: {message.from_user.id}, Username: {message.from_user.username}")
    
    # Быстрая проверка прав администратора
    is_admin = message.from_user.id == ADMIN_ID or message.from_user.username == "EbZakhar"
    if not is_admin:
        await message.answer("❌ У вас нет доступа к панели администратора.")
        logging.info(f"Access denied. Required ID: {ADMIN_ID}")
        return

    # Сбрасываем текущее состояние
    await state.clear()

    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📄 Последние заявки", callback_data="last_requests"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
    ]])
    await message.answer("👨‍💼 Панель администратора:", reply_markup=markup)

@router.callback_query(F.data == "last_requests")
async def show_last_requests(callback: types.CallbackQuery):
    try:
        if callback.from_user.id != ADMIN_ID and callback.from_user.username != "EbZakhar":
            return await callback.answer("❌ Нет доступа", show_alert=True)

        requests = load_last_requests()
        if not requests:
            return await callback.message.edit_text("📭 Нет новых заявок.")
    except Exception as e:
        logging.error(f"Error in show_last_requests: {e}")
        await callback.answer("❌ Произошла ошибка при загрузке заявок", show_alert=True)
        return

    await callback.message.delete()
    for req in reversed(requests):
        text = (
            f"📋 <b>Новая заявка</b>\n\n"
            f"📁 Категория: {req['category']}\n"
            f"🔍 Услуга: {req['service']}\n"
            f"👤 Имя: {req['name']}\n"
            f"📞 Телефон: {req['phone']}\n"
            f"💭 Комментарий: {req.get('comment', '—')}\n"
            f"🌍 Страна: {req['nationality']}\n"
            f"🔗 Telegram: @{req.get('username', 'Без username')}"
        )

        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply_{req.get('telegram_id', '')}")
        ]])
        await callback.message.answer(text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(lambda c: c.data.startswith("reply_"))
async def prepare_reply(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID and callback.from_user.username != "EbZakhar":
        return await callback.answer("❌ Нет доступа", show_alert=True)

    user_id = callback.data.split("_")[1]
    if not user_id:
        return await callback.answer("❌ ID пользователя не найден", show_alert=True)

    await state.set_state(AdminState.waiting_for_reply)
    await state.update_data(reply_to=user_id)
    await callback.message.answer(
        f"✍️ Напишите ответ для пользователя (ID: {user_id}):"
    )

@router.message(AdminState.waiting_for_reply)
async def send_reply(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID and message.from_user.username != "EbZakhar":
        return

    data = await state.get_data()
    user_id = data.get('reply_to')
    
    if not user_id:
        await message.answer("❌ Ошибка: ID пользователя не найден")
        await state.clear()
        return

    try:
        await message.bot.send_message(
            chat_id=int(user_id),
            text=f"📬 <b>Сообщение от администратора:</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        save_answer_log(user_id, message.text)
        await message.answer("✅ Ответ успешно отправлен")
        logging.info(f"Admin reply sent to user {user_id}")
        
        # Показываем админ-панель снова
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📄 Последние заявки", callback_data="last_requests"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
        ]])
        await message.answer("👨‍💼 Панель администратора:", reply_markup=markup)
        
    except ValueError:
        await message.answer("❌ Ошибка: Неверный формат ID пользователя")
        logging.error(f"Invalid user ID format: {user_id}")
    except Exception as e:
        error_msg = f"❌ Ошибка при отправке: {str(e)}"
        await message.answer(error_msg)
        logging.error(f"Failed to send admin reply to {user_id}: {str(e)}")
    finally:
        await state.clear()

@router.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID and callback.from_user.username != "EbZakhar":
        return await callback.answer("❌ Нет доступа", show_alert=True)

    if not os.path.exists(DATA_PATH):
        return await callback.message.edit_text("📊 Статистика пуста")

    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = len(data)
        categories = {}
        services = {}

        for req in data:
            cat = req["category"]
            serv = req["service"]
            categories[cat] = categories.get(cat, 0) + 1
            services[serv] = services.get(serv, 0) + 1

        text = f"📊 <b>Общая статистика</b>\n\n"
        text += f"📝 Всего заявок: {count}\n\n"
        text += "<b>По категориям:</b>\n"
        for cat, count in categories.items():
            text += f"- {cat}: {count}\n"

        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка при загрузке статистики: {str(e)}")
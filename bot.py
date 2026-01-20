import asyncio
import json
import random
import logging
import os
import time
import pickle
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
    FSInputFile
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import aiohttp
from aiohttp import web
import base64
from typing import Dict, List, Optional

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN', '8400292600:AAEDv_L2A-xTFC2aiUn-2fOR4HNV4_iDMXo')
ADMIN_IDS = [7539197809]
LOG_CHANNEL = os.getenv('LOG_CHANNEL', '-1003620475629')
BOT_NAME = "Давинчикк 🎭"

# GitHub для хранения данных
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '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')
GITHUB_USERNAME = os.getenv('GITHUB_USERNAME', 'mirmahmedovf52-ui')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'davincikk-6ot')
DATA_FILE = "bot_data.json"

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
active_searches: Dict[int, datetime] = {}
active_chats: Dict[int, int] = {}
online_users: Dict[int, datetime] = {}
notifications_sent = {}  # Для отслеживания отправленных уведомлений

# === КЛАВИАТУРЫ ===
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Главная клавиатура"""
    buttons = [
        [types.KeyboardButton(text="🔍 Начать поиск"), types.KeyboardButton(text="⏹️ Остановить")],
        [types.KeyboardButton(text="👤 Мой профиль"), types.KeyboardButton(text="📊 Статистика")],
        [types.KeyboardButton(text="👥 Мои друзья"), types.KeyboardButton(text="⚙️ Настройки")],
        [types.KeyboardButton(text="ℹ️ Помощь"), types.KeyboardButton(text="🎁 Бонусы")]
    ]
    
    if user_id in ADMIN_IDS:
        buttons.insert(2, [types.KeyboardButton(text="🛠️ Админ-панель")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура админа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="📁 Файл всем", callback_data="admin_file_all")
        ],
        [
            InlineKeyboardButton(text="⚠️ Жалобы", callback_data="admin_reports"),
            InlineKeyboardButton(text="🔨 Бан/Разбан", callback_data="admin_ban")
        ],
        [
            InlineKeyboardButton(text="💾 Экспорт данных", callback_data="admin_export"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_search_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура поиска"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 Быстрый поиск", callback_data="search_fast"),
            InlineKeyboardButton(text="🔍 По фильтру", callback_data="search_filter")
        ],
        [
            InlineKeyboardButton(text="👥 С друзьями", callback_data="search_friends"),
            InlineKeyboardButton(text="💬 Только текст", callback_data="search_text")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="search_cancel")]
    ])

def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура профиля"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="♂️ Пол", callback_data="edit_gender"),
            InlineKeyboardButton(text="🔢 Возраст", callback_data="edit_age")
        ],
        [
            InlineKeyboardButton(text="🎯 Интересы", callback_data="edit_interests"),
            InlineKeyboardButton(text="📝 О себе", callback_data="edit_bio")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# === РАБОТА С ДАННЫМИ В GITHUB ===
async def load_data() -> dict:
    """Загрузить данные из GitHub"""
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/main/{DATA_FILE}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logging.info(f"✅ Данные загружены. Пользователей: {len(data.get('users', {}))}")
                    return data
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки: {e}")
    
    return {
        "users": {},
        "friends": {},
        "stats": {
            "total_users": 0,
            "total_chats": 0,
            "total_messages": 0,
            "peak_online": 0,
            "peak_online_time": None
        },
        "settings": {
            "bot_active": True,
            "auto_notifications": True,
            "notification_thresholds": [10, 50, 100, 200, 500, 1000]
        }
    }

async def save_data(data: dict) -> bool:
    """Сохранить данные в GitHub"""
    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{DATA_FILE}"
        
        # Получаем SHA текущего файла
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                sha = None
                if resp.status == 200:
                    file_info = await resp.json()
                    sha = file_info.get('sha')
            
            # Подготавливаем данные
            data["last_updated"] = datetime.now().isoformat()
            content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
            encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": f"Auto-save {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "content": encoded,
                "sha": sha,
                "branch": "main"
            }
            
            # Отправляем обновление
            async with session.put(url, headers=headers, json=payload) as resp:
                if resp.status in [200, 201]:
                    logging.info("✅ Данные сохранены в GitHub")
                    return True
                else:
                    error = await resp.text()
                    logging.error(f"❌ Ошибка сохранения: {resp.status} - {error}")
                    return False
    except Exception as e:
        logging.error(f"❌ Ошибка GitHub API: {e}")
        return False

# === СИСТЕМА ОНЛАЙН-СТАТИСТИКИ ===
def update_online(user_id: int):
    """Обновить статус онлайн пользователя"""
    online_users[user_id] = datetime.now()

def get_online_count() -> int:
    """Получить количество онлайн пользователей (активны последние 5 минут)"""
    now = datetime.now()
    return sum(1 for last_seen in online_users.values() 
               if (now - last_seen).total_seconds() < 300)

async def check_online_notifications():
    """Проверка и отправка уведомлений о высоком онлайн"""
    data = await load_data()
    thresholds = data.get('settings', {}).get('notification_thresholds', [])
    auto_notify = data.get('settings', {}).get('auto_notifications', True)
    
    if not auto_notify:
        return
    
    online_now = get_online_count()
    
    for threshold in thresholds:
        if online_now >= threshold and notifications_sent.get(threshold, 0) < 3:
            # Отправляем уведомление
            notification_text = f"""
🎉 <b>ВАЖНОЕ УВЕДОМЛЕНИЕ!</b>

Сейчас в <b>{BOT_NAME}</b> онлайн: <b>{online_now}+ пользователей</b>! 🚀

Это рекордный онлайн за последнее время!
Присоединяйся к общению прямо сейчас:

• Быстро находи собеседников
• Общайся с активными пользователями
• Добавляй новых друзей

<b>Не упусти возможность пообщаться с живыми людьми прямо сейчас!</b>

👉 Нажми /start чтобы присоединиться!
            """
            
            # Отправляем всем пользователям
            users = data.get('users', {})
            success_count = 0
            
            for user_id_str in users:
                try:
                    await bot.send_message(
                        int(user_id_str), 
                        notification_text,
                        disable_notification=False
                    )
                    success_count += 1
                except:
                    pass
            
            # Логируем
            await log_to_channel(
                f"📢 АВТО-УВЕДОМЛЕНИЕ ОНЛАЙН\n"
                f"Порог: {threshold}+ пользователей\n"
                f"Текущий онлайн: {online_now}\n"
                f"Отправлено: {success_count}/{len(users)}"
            )
            
            notifications_sent[threshold] = notifications_sent.get(threshold, 0) + 1
            break

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
async def health_check(request):
    return web.Response(text=f"{BOT_NAME} is running! ✅ Online: {get_online_count()} users")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_get('/stats', lambda r: web.Response(text=f"Online: {get_online_count()}"))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("✅ Веб-сервер запущен на порту 8080")

async def keep_alive():
    """Система keep-alive для Render"""
    while True:
        await asyncio.sleep(300)  # 5 минут
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8080/health') as resp:
                    logging.info(f"🔄 Keep-alive ping: {resp.status}")
                    
                    # Проверяем онлайн и отправляем уведомления
                    await check_online_notifications()
        except Exception as e:
            logging.error(f"❌ Keep-alive ошибка: {e}")

# === ЛОГИРОВАНИЕ В КАНАЛ ===
async def log_to_channel(text: str, media_file=None, media_type=None):
    """Отправить лог в канал с медиа"""
    try:
        if media_file and media_type:
            # Скачиваем и отправляем файл
            if media_type == 'photo':
                await bot.send_photo(LOG_CHANNEL, types.FSInputFile(media_file), caption=text[:1000])
            elif media_type == 'video':
                await bot.send_video(LOG_CHANNEL, types.FSInputFile(media_file), caption=text[:1000])
            elif media_type == 'voice':
                await bot.send_voice(LOG_CHANNEL, types.FSInputFile(media_file), caption=text[:1000])
            elif media_type == 'document':
                await bot.send_document(LOG_CHANNEL, types.FSInputFile(media_file), caption=text[:1000])
            else:
                await bot.send_message(LOG_CHANNEL, f"{text}\n[Файл: {media_type}]")
            
            # Удаляем временный файл
            try:
                os.remove(media_file)
            except:
                pass
        else:
            await bot.send_message(LOG_CHANNEL, text[:4000])
    except Exception as e:
        logging.error(f"❌ Ошибка логирования: {e}")

# === ОСНОВНЫЕ КОМАНДЫ ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Аноним"
    
    update_online(user_id)
    
    # Загружаем данные
    data = await load_data()
    
    # Регистрация/обновление пользователя
    user_id_str = str(user_id)
    if user_id_str not in data["users"]:
        data["users"][user_id_str] = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "join_date": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "profile": {
                "gender": "не указан",
                "age": 0,
                "interests": [],
                "bio": "",
                "preferred_gender": "любой",
                "preferred_age_min": 18,
                "preferred_age_max": 45
            },
            "stats": {
                "chats": 0,
                "messages": 0,
                "friends": 0,
                "rating": 5.0,
                "total_time": 0
            },
            "is_banned": False,
            "warnings": 0,
            "is_admin": user_id in ADMIN_IDS
        }
        data["stats"]["total_users"] = len(data["users"])
        
        await save_data(data)
        await log_to_channel(f"🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ\nID: {user_id}\nИмя: {first_name}\n@{username}")
    else:
        # Обновляем время последней активности
        data["users"][user_id_str]["last_seen"] = datetime.now().isoformat()
        data["users"][user_id_str]["username"] = username
        await save_data(data)
    
    welcome_text = f"""
🎭 <b>Добро пожаловать в {BOT_NAME}!</b>

🛡️ <b>Анонимный и безопасный чат-рулетка:</b>
• Ваши данные защищены
• Сообщения шифруются
• История не сохраняется
• Можно пожаловаться на нарушителей

⚡ <b>Как начать:</b>
1. Нажми "🔍 Начать поиск"
2. Найди собеседника за 10 секунд
3. Общайся текстом, фото, видео, голосовыми
4. Добавляй понравившихся в друзья

📊 <b>Сейчас онлайн:</b> {get_online_count()} пользователей
🎯 <b>Всего пользователей:</b> {data["stats"]["total_users"]}

<b>Используй кнопки ниже:</b>
"""
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id))

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await end_chat(user_id, partner_id, "по команде /stop")
        await message.answer("✅ Диалог завершен.", reply_markup=get_main_keyboard(user_id))
    elif user_id in active_searches:
        del active_searches[user_id]
        await message.answer("✅ Поиск отменен.", reply_markup=get_main_keyboard(user_id))
    else:
        await message.answer("Вы не в диалоге и не в поиске.", reply_markup=get_main_keyboard(user_id))

@dp.message(F.text == "🔍 Начать поиск")
async def start_search_handler(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        await message.answer("Вы уже в диалоге! Используйте /stop чтобы завершить.")
        return
    
    if user_id in active_searches:
        await message.answer("Вы уже в поиске!")
        return
    
    await message.answer(
        "🔍 <b>Выберите тип поиска:</b>\n\n"
        "• <b>Быстрый поиск</b> - любой собеседник\n"
        "• <b>По фильтру</b> - по полу/возрасту\n"
        "• <b>С друзьями</b> - только из списка друзей\n"
        "• <b>Только текст</b> - без медиа",
        reply_markup=get_search_keyboard()
    )

@dp.message(F.text == "🛠️ Админ-панель")
async def admin_panel_handler(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен!")
        return
    
    data = await load_data()
    online_now = get_online_count()
    
    admin_text = f"""
🛠️ <b>АДМИН-ПАНЕЛЬ {BOT_NAME}</b>

📊 <b>Статистика:</b>
• Всего пользователей: {data["stats"]["total_users"]}
• Онлайн сейчас: {online_now}
• В поиске: {len(active_searches)}
• В диалогах: {len(active_chats) // 2}
• Всего сообщений: {data["stats"]["total_messages"]}

⚙️ <b>Управление:</b>
• Рассылка всем пользователям
• Отправка файлов всем
• Управление пользователями
• Настройки бота
"""
    
    await message.answer(admin_text, reply_markup=get_admin_keyboard())

@dp.message(F.text == "📊 Статистика")
async def stats_handler(message: types.Message):
    data = await load_data()
    online_now = get_online_count()
    
    stats_text = f"""
📊 <b>СТАТИСТИКА {BOT_NAME}</b>

👥 <b>Пользователи:</b>
• Всего: {data["stats"]["total_users"]}
• Онлайн: {online_now}
• В поиске: {len(active_searches)}
• В диалогах: {len(active_chats) // 2}

💬 <b>Активность:</b>
• Всего диалогов: {data["stats"]["total_chats"]}
• Всего сообщений: {data["stats"]["total_messages"]}
• Пиковый онлайн: {data["stats"].get('peak_online', 0)}

⏱️ <b>Время:</b>
• Обновлено: {datetime.now().strftime('%H:%M:%S')}
"""
    
    await message.answer(stats_text)

# === АДМИН-КОМАНДЫ ===
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    """Рассылка сообщения всем пользователям"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен!")
        return
    
    if not command.args:
        await message.answer("Использование: /broadcast [текст сообщения]")
        return
    
    broadcast_text = command.args
    data = await load_data()
    users = data.get("users", {})
    
    await message.answer(f"📢 Начинаю рассылку для {len(users)} пользователей...")
    
    success = 0
    failed = 0
    
    for user_id_str in users:
        try:
            await bot.send_message(
                int(user_id_str),
                f"📢 <b>ОБЪЯВЛЕНИЕ ОТ АДМИНИСТРАЦИИ:</b>\n\n{broadcast_text}\n\n— {BOT_NAME}"
            )
            success += 1
            await asyncio.sleep(0.05)  # Задержка чтобы не получить лимит
        except Exception as e:
            failed += 1
    
    await message.answer(f"✅ Рассылка завершена!\nУспешно: {success}\nНе удалось: {failed}")
    await log_to_channel(f"📢 АДМИН РАССЫЛКА\nОт: {user_id}\nТекст: {broadcast_text[:100]}\nУспешно: {success}/{len(users)}")

@dp.message(Command("sendfile"))
async def cmd_sendfile(message: types.Message):
    """Отправка файла всем пользователям (админ)"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    if not message.document and not message.photo and not message.video:
        await message.answer("Отправьте файл/фото/видео с подписью: /sendfile [описание]")
        return
    
    data = await load_data()
    users = data.get("users", {})
    caption = message.caption or "Файл от администрации"
    
    await message.answer(f"📁 Отправляю файл {len(users)} пользователям...")
    
    success = 0
    failed = 0
    
    for user_id_str in users:
        try:
            if message.document:
                await bot.send_document(
                    int(user_id_str),
                    message.document.file_id,
                    caption=f"📁 {caption}\n— {BOT_NAME}"
                )
            elif message.photo:
                await bot.send_photo(
                    int(user_id_str),
                    message.photo[-1].file_id,
                    caption=f"🖼️ {caption}\n— {BOT_NAME}"
                )
            elif message.video:
                await bot.send_video(
                    int(user_id_str),
                    message.video.file_id,
                    caption=f"🎥 {caption}\n— {BOT_NAME}"
                )
            
            success += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    
    await message.answer(f"✅ Файл отправлен!\nУспешно: {success}\nНе удалось: {failed}")
    await log_to_channel(f"📁 АДМИН ФАЙЛ ВСЕМ\nОт: {user_id}\nФайл отправлен: {success}/{len(users)}")

# === ОБРАБОТЧИКИ КНОПОК ===
@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "📢 <b>Рассылка всем пользователям:</b>\n\n"
        "Используйте команду:\n"
        "<code>/broadcast ваш текст сообщения</code>\n\n"
        "Или отправьте сообщение с текстом для рассылки."
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_file_all")
async def admin_file_all_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "📁 <b>Отправка файла всем пользователям:</b>\n\n"
        "Отправьте файл/фото/видео с подписью:\n"
        "<code>/sendfile [описание файла]</code>\n\n"
        "Файл будет отправлен всем пользователям бота."
    )
    await callback.answer()

@dp.callback_query(F.data == "search_fast")
async def search_fast_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id in active_searches:
        await callback.answer("Вы уже в поиске!", show_alert=True)
        return
    
    active_searches[user_id] = datetime.now()
    
    await callback.message.edit_text(
        "🔍 <b>Ищем случайного собеседника...</b>\n\n"
        "Ожидание: до 30 секунд\n"
        "Используйте кнопку '⏹️ Остановить' для отмены."
    )
    
    # Поиск пары
    found = False
    for other_id, search_time in list(active_searches.items()):
        if other_id != user_id and (datetime.now() - search_time).seconds < 60:
            await start_chat(user_id, other_id)
            found = True
            break
    
    if not found:
        await asyncio.sleep(30)
        if user_id in active_searches:
            for other_id, search_time in list(active_searches.items()):
                if other_id != user_id:
                    await start_chat(user_id, other_id)
                    found = True
                    break
            
            if not found:
                await callback.message.edit_text(
                    "😔 <b>Собеседник не найден</b>\n\n"
                    "Попробуйте позже или другой тип поиска."
                )
                if user_id in active_searches:
                    del active_searches[user_id]
    
    await callback.answer()

# === ФУНКЦИИ ЧАТА ===
async def start_chat(user1_id: int, user2_id: int):
    """Начать диалог между двумя пользователями"""
    # Убираем из поиска
    for uid in [user1_id, user2_id]:
        if uid in active_searches:
            del active_searches[uid]
    
    # Регистрируем активный чат
    active_chats[user1_id] = user2_id
    active_chats[user2_id] = user1_id
    
    # Обновляем статистику
    data = await load_data()
    for uid in [user1_id, user2_id]:
        uid_str = str(uid)
        if uid_str in data["users"]:
            data["users"][uid_str]["stats"]["chats"] += 1
    
    data["stats"]["total_chats"] += 1
    await save_data(data)
    
    # Сообщения пользователям
    chat_text = """
✅ <b>Собеседник найден! Начинайте общение.</b>

🎭 <b>Можно отправлять:</b>
• Текстовые сообщения
• Фото и видео
• Голосовые сообщения
• Стикеры и GIF

🛡️ <b>Правила:</b>
• Будьте вежливы
• Не спамьте
• Не отправляйте запрещенный контент

<b>Чтобы завершить диалог - нажмите '⏹️ Остановить'</b>
"""
    
    try:
        await bot.send_message(user1_id, chat_text, reply_markup=get_main_keyboard(user1_id))
        await bot.send_message(user2_id, chat_text, reply_markup=get_main_keyboard(user2_id))
        
        await log_to_channel(f"🔗 НАЧАЛСЯ ДИАЛОГ\n{user1_id} ↔ {user2_id}")
    except Exception as e:
        logging.error(f"Ошибка начала чата: {e}")

async def end_chat(user1_id: int, user2_id: int, reason: str = "неизвестно"):
    """Завершить диалог"""
    # Удаляем из активных чатов
    for uid in [user1_id, user2_id]:
        if uid in active_chats:
            del active_chats[uid]
    
    # Сообщения о завершении
    end_text = "❌ <b>Диалог завершен.</b>\n\nИспользуйте '🔍 Начать поиск' для нового диалога."
    
    try:
        await bot.send_message(user1_id, end_text, reply_markup=get_main_keyboard(user1_id))
        await bot.send_message(user2_id, end_text, reply_markup=get_main_keyboard(user2_id))
        
        await log_to_channel(f"🔴 ДИАЛОГ ЗАВЕРШЕН\n{user1_id} ↔ {user2_id}\nПричина: {reason}")
    except Exception as e:
        logging.error(f"Ошибка завершения чата: {e}")

# === ОБРАБОТКА СООБЩЕНИЙ ===
@dp.message(F.chat.type == "private")
async def handle_private_message(message: types.Message):
    user_id = message.from_user.id
    update_online(user_id)
    
    # Если пользователь в чате - пересылаем сообщение
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # Обновляем статистику
        data = await load_data()
        user_id_str = str(user_id)
        if user_id_str in data["users"]:
            data["users"][user_id_str]["stats"]["messages"] += 1
            data["stats"]["total_messages"] += 1
            await save_data(data)
        
        # Сохраняем медиа-файл и отправляем в канал
        media_file = None
        media_type = None
        
        try:
            # Для фото
            if message.photo:
                file_id = message.photo[-1].file_id
                file = await bot.get_file(file_id)
                media_file = f"temp_photo_{file_id}.jpg"
                await bot.download_file(file.file_path, media_file)
                media_type = 'photo'
            
            # Для видео
            elif message.video:
                file_id = message.video.file_id
                file = await bot.get_file(file_id)
                media_file = f"temp_video_{file_id}.mp4"
                await bot.download_file(file.file_path, media_file)
                media_type = 'video'
            
            # Для голосовых
            elif message.voice:
                file_id = message.voice.file_id
                file = await bot.get_file(file_id)
                media_file = f"temp_voice_{file_id}.ogg"
                await bot.download_file(file.file_path, media_file)
                media_type = 'voice'
            
            # Для документов
            elif message.document:
                file_id = message.document.file_id
                file = await bot.get_file(file_id)
                media_file = f"temp_doc_{file_id}"
                await bot.download_file(file.file_path, media_file)
                media_type = 'document'
            
            # Логируем в канал
            msg_preview = message.text or message.caption or f"[{media_type or 'сообщение'}]"
            await log_to_channel(
                f"📨 СООБЩЕНИЕ\nОт: {user_id}\nКому: {partner_id}\nТип: {media_type or 'текст'}\n{msg_preview[:100]}",
                media_file,
                media_type
            )
            
        except Exception as e:
            logging.error(f"Ошибка обработки медиа: {e}")
            msg_preview = message.text or message.caption or "[сообщение]"
            await log_to_channel(f"📨 СООБЩЕНИЕ\n{user_id} → {partner_id}\n{msg_preview[:100]}")
        
        # Пересылаем сообщение партнеру
        try:
            if message.text:
                await bot.send_message(partner_id, f"💬 <b>Собеседник:</b>\n{message.text}")
            elif message.photo:
                await bot.send_photo(
                    partner_id, 
                    message.photo[-1].file_id,
                    caption=f"💬 <b>Собеседник:</b>\n{message.caption}" if message.caption else None
                )
            elif message.video:
                await bot.send_video(
                    partner_id,
                    message.video.file_id,
                    caption=f"💬 <b>Собеседник:</b>\n{message.caption}" if message.caption else None
                )
            elif message.voice:
                await bot.send_voice(partner_id, message.voice.file_id)
            elif message.document:
                await bot.send_document(
                    partner_id,
                    message.document.file_id,
                    caption=f"💬 <b>Собеседник:</b>\n{message.caption}" if message.caption else None
                )
            elif message.sticker:
                await bot.send_sticker(partner_id, message.sticker.file_id)
        except Exception as e:
            await message.answer("❌ Не удалось отправить сообщение. Возможно, собеседник отключился.")
            if user_id in active_chats:
                partner = active_chats[user_id]
                await end_chat(user_id, partner, "ошибка отправки")

# === ЗАПУСК БОТА ===
async def on_startup():
    """Действия при запуске бота"""
    logging.info("=" * 50)
    logging.info(f"🚀 Бот {BOT_NAME} запускается...")
    logging.info(f"👑 Админ ID: {ADMIN_IDS}")
    logging.info(f"📨 Канал логов: {LOG_CHANNEL}")
    logging.info("=" * 50)
    
    # Запускаем веб-сервер
    await start_web_server()
    
    # Запускаем keep-alive систему
    asyncio.create_task(keep_alive())
    
    # Отправляем сообщение о запуске
    try:
        await bot.send_message(
            LOG_CHANNEL,
            f"🚀 <b>{BOT_NAME} запущен на Render!</b>\n"
            f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Веб-сервер: порт 8080\n"
            f"Keep-alive: активирован"
        )
    except:
        pass

async def main():
    # Действия при запуске
    await on_startup()
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

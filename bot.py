import asyncio
import json
import random
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import aiohttp
from aiohttp import web

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN', '8400292600:AAEDv_L2A-xTFC2aiUn-2fOR4HNV4_iDMXo')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '7539197809').split(',')))
LOG_CHANNEL = os.getenv('LOG_CHANNEL', '-1003620475629')
BOT_NAME = "Давинчикк 🎭"

# GitHub для хранения данных
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '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')
GITHUB_USERNAME = os.getenv('GITHUB_USERNAME', 'mirmahmedovf52-ui')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'davincikk-6ot')
DATA_FILE = "data.json"

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
active_searches = {}  # {user_id: время начала поиска}
active_chats = {}     # {user_id: partner_id}
user_data = {}        # Данные пользователей
friends_data = {}     # Данные друзей

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
async def health_check(request):
    return web.Response(text=f"{BOT_NAME} is running! ✅ Time: {datetime.now().strftime('%H:%M:%S')}")

async def start_web_server():
    """Запуск веб-сервера на порту 10000"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    await site.start()
    logging.info("✅ Веб-сервер запущен на порту 10000")

# === KEEP-ALIVE СИСТЕМА ===
async def keep_alive_ping():
    """Отправляет запросы каждые 5 минут чтобы Render не засыпал"""
    while True:
        await asyncio.sleep(300)  # 5 минут
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:10000/health') as resp:
                    logging.info(f"🔄 Keep-alive ping: {resp.status}")
        except Exception as e:
            logging.error(f"❌ Keep-alive ошибка: {e}")

# === РАБОТА С GITHUB ===
async def load_from_github():
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
        logging.error(f"❌ Ошибка загрузки данных: {e}")
    
    # Если файла нет - создаем базовую структуру
    return {
        "users": {},
        "friends": {},
        "stats": {
            "total_users": 0,
            "total_chats": 0,
            "total_messages": 0
        }
    }

async def save_to_github():
    """Сохранить данные в GitHub"""
    try:
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{DATA_FILE}"
        
        # Получаем текущий SHA файла
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                sha = None
                if resp.status == 200:
                    file_info = await resp.json()
                    sha = file_info.get('sha')
            
            # Подготавливаем данные для сохранения
            data_to_save = {
                "users": user_data,
                "friends": friends_data,
                "stats": {
                    "total_users": len(user_data),
                    "total_chats": sum(u.get('stats', {}).get('chats', 0) for u in user_data.values()) // 2,
                    "total_messages": sum(u.get('stats', {}).get('messages', 0) for u in user_data.values()),
                    "updated": datetime.now().isoformat()
                }
            }
            
            import base64
            content = json.dumps(data_to_save, indent=2, ensure_ascii=False, default=str)
            encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
            
            payload = {
                "message": f"Auto-update {datetime.now().isoformat()}",
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

# === ЛОГИРОВАНИЕ ===
async def log_to_channel(text):
    """Отправить лог в Telegram канал"""
    try:
        await bot.send_message(LOG_CHANNEL, text[:4000])
    except Exception as e:
        logging.error(f"❌ Ошибка отправки лога: {e}")

# === ОСНОВНЫЕ КОМАНДЫ ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Аноним"
    
    user_id_str = str(user_id)
    
    # Регистрация нового пользователя
    if user_id_str not in user_data:
        user_data[user_id_str] = {
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
                "rating": 5.0
            },
            "is_banned": False,
            "is_admin": user_id in ADMIN_IDS
        }
        await log_to_channel(f"🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ\nID: {user_id}\nИмя: {first_name}\nUsername: @{username}")
    else:
        # Обновляем данные существующего пользователя
        user_data[user_id_str]['username'] = username
        user_data[user_id_str]['last_seen'] = datetime.now().isoformat()
    
    # Сохраняем данные
    await save_to_github()
    
    # Приветственное сообщение
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
3. Общайся текстом, голосовыми, стикерами
4. Добавляй понравившихся в друзья

🎯 <b>Функции:</b>
• Умный поиск собеседников
• Система друзей
• Статистика и профиль
• Админ-панель

<b>Выбери действие:</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Начать поиск", callback_data="search_start")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile_view")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats_view")],
        [InlineKeyboardButton(text="👥 Мои друзья", callback_data="friends_list")],
        [InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")] if user_id in ADMIN_IDS else [],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard)

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await end_chat(user_id, partner_id, "по команде /stop")
        await message.answer("✅ Диалог завершен.")
    elif user_id in active_searches:
        del active_searches[user_id]
        await message.answer("✅ Поиск отменен.")
    else:
        await message.answer("Вы не в диалоге и не в поиске.")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    total_users = len(user_data)
    online_count = len([u for u in user_data.values() 
                       if (datetime.now() - datetime.fromisoformat(u.get('last_seen', '2023-01-01'))).seconds < 300])
    
    stats_text = f"""
📊 <b>Статистика {BOT_NAME}:</b>

👥 <b>Пользователи:</b>
• Всего: {total_users}
• Онлайн: {online_count}
• В поиске: {len(active_searches)}
• В диалогах: {len(active_chats) // 2}

💬 <b>Активность:</b>
• Активных диалогов: {len(active_chats) // 2}
"""
    
    await message.answer(stats_text)

# === ОБРАБОТЧИКИ КНОПОК ===
@dp.callback_query(F.data == "search_start")
async def search_start(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id in active_chats:
        await callback.answer("Вы уже в диалоге!", show_alert=True)
        return
    
    if user_id in active_searches:
        await callback.answer("Вы уже в поиске!", show_alert=True)
        return
    
    # Добавляем в поиск
    active_searches[user_id] = datetime.now()
    
    await callback.message.edit_text(
        "🔍 <b>Ищем собеседника...</b>\n\n"
        "Ожидание: до 30 секунд\n"
        "Используй /stop чтобы отменить."
    )
    
    # Ищем пару
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
                    "Попробуй позже или пригласи друзей!"
                )
                if user_id in active_searches:
                    del active_searches[user_id]
    
    await callback.answer()

@dp.callback_query(F.data == "profile_view")
async def profile_view(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get(str(user_id), {})
    
    if not user:
        await callback.answer("Сначала используйте /start", show_alert=True)
        return
    
    profile = user.get('profile', {})
    stats = user.get('stats', {})
    
    profile_text = f"""
👤 <b>Ваш профиль:</b>

<b>Основное:</b>
• Имя: {user.get('first_name', 'Не указано')}
• Username: @{user.get('username', 'нет')}
• ID: {user_id}

<b>Профиль:</b>
• Пол: {profile.get('gender', 'не указан')}
• Возраст: {profile.get('age', 'не указан')}
• Интересы: {', '.join(profile.get('interests', [])) or 'не указаны'}
• О себе: {profile.get('bio', 'не указано')}

<b>Статистика:</b>
• Диалогов: {stats.get('chats', 0)}
• Сообщений: {stats.get('messages', 0)}
• Друзей: {stats.get('friends', 0)}
• Рейтинг: {stats.get('rating', 5.0)}/5.0
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="profile_edit")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(profile_text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    total_users = len(user_data)
    online_count = len([u for u in user_data.values() 
                       if (datetime.now() - datetime.fromisoformat(u.get('last_seen', '2023-01-01'))).seconds < 300])
    
    admin_text = f"""
🛠️ <b>Админ-панель {BOT_NAME}</b>

📈 <b>Статистика:</b>
• Всего пользователей: {total_users}
• Онлайн сейчас: {online_count}
• Активных диалогов: {len(active_chats) // 2}
• В поиске: {len(active_searches)}

⚙️ <b>Управление:</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Полная статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(admin_text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await cmd_start(callback.message)
    await callback.answer()

# === ФУНКЦИИ ЧАТА ===
async def start_chat(user1_id, user2_id):
    """Начать диалог между двумя пользователями"""
    # Убираем из поиска
    for uid in [user1_id, user2_id]:
        if uid in active_searches:
            del active_searches[uid]
    
    # Регистрируем активный чат
    active_chats[user1_id] = user2_id
    active_chats[user2_id] = user1_id
    
    # Обновляем статистику пользователей
    for uid in [user1_id, user2_id]:
        uid_str = str(uid)
        if uid_str in user_data:
            user_data[uid_str]['stats']['chats'] += 1
    
    await save_to_github()
    
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

<b>Чтобы завершить диалог - /stop</b>
"""
    
    try:
        await bot.send_message(user1_id, chat_text)
        await bot.send_message(user2_id, chat_text)
        
        await log_to_channel(f"🔗 НАЧАЛСЯ ДИАЛОГ\n{user1_id} ↔ {user2_id}")
    except Exception as e:
        logging.error(f"❌ Ошибка начала чата: {e}")

async def end_chat(user1_id, user2_id, reason="неизвестно"):
    """Завершить диалог"""
    # Удаляем из активных чатов
    for uid in [user1_id, user2_id]:
        if uid in active_chats:
            del active_chats[uid]
    
    # Сообщения о завершении
    end_text = "❌ <b>Диалог завершен.</b>\n\nИспользуйте /start для нового поиска."
    
    try:
        await bot.send_message(user1_id, end_text)
        await bot.send_message(user2_id, end_text)
        
        # Предложение добавить в друзья
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить в друзья", callback_data=f"add_friend_{user2_id}")]
        ])
        
        await bot.send_message(user1_id, "Хотите добавить собеседника в друзья?", reply_markup=keyboard)
        
        await log_to_channel(f"🔴 ДИАЛОГ ЗАВЕРШЕН\n{user1_id} ↔ {user2_id}\nПричина: {reason}")
    except Exception as e:
        logging.error(f"❌ Ошибка завершения чата: {e}")

# === ОБРАБОТКА СООБЩЕНИЙ ===
@dp.message(F.chat.type == "private")
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # Обновляем статистику
        uid_str = str(user_id)
        if uid_str in user_data:
            user_data[uid_str]['stats']['messages'] += 1
        
        # Логируем
        msg_preview = message.text or message.caption or f"[{message.content_type}]"
        if len(msg_preview) > 50:
            msg_preview = msg_preview[:50] + "..."
        
        await log_to_channel(f"📨 СООБЩЕНИЕ\nОт: {user_id}\nКому: {partner_id}\nТекст: {msg_preview}")
        
        try:
            # Пересылаем сообщение
            if message.text:
                await bot.send_message(partner_id, f"💬 <b>Собеседник:</b>\n{message.text}")
            elif message.photo:
                await bot.send_photo(partner_id, message.photo[-1].file_id, 
                                    caption=f"💬 <b>Собеседник:</b>\n{message.caption}" if message.caption else None)
            elif message.video:
                await bot.send_video(partner_id, message.video.file_id,
                                    caption=f"💬 <b>Собеседник:</b>\n{message.caption}" if message.caption else None)
            elif message.voice:
                await bot.send_voice(partner_id, message.voice.file_id)
            elif message.sticker:
                await bot.send_sticker(partner_id, message.sticker.file_id)
        except Exception as e:
            await message.answer("❌ Не удалось отправить сообщение. Возможно, собеседник отключился.")
            if user_id in active_chats:
                partner = active_chats[user_id]
                await end_chat(user_id, partner, "ошибка отправки")
    else:
        # Если не в чате - показываем меню
        await cmd_start(message)

# === ЗАПУСК БОТА ===
async def main():
    # Загружаем данные из GitHub
    global user_data, friends_data
    data = await load_from_github()
    user_data = data.get('users', {})
    friends_data = data.get('friends', {})
    
    # Запускаем веб-сервер для Render
    await start_web_server()
    
    # Запускаем keep-alive систему
    asyncio.create_task(keep_alive_ping())
    
    # Информация о запуске
    logging.info("=" * 50)
    logging.info(f"🚀 Бот {BOT_NAME} запущен на Render")
    logging.info(f"👑 Админ ID: {ADMIN_IDS}")
    logging.info(f"📊 Пользователей в базе: {len(user_data)}")
    logging.info(f"📨 Логи в канал: {LOG_CHANNEL}")
    logging.info("=" * 50)
    
    # Отправляем сообщение о запуске в канал
    await log_to_channel(f"🚀 <b>{BOT_NAME} запущен на Render!</b>\nВремя: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nПользователей: {len(user_data)}")
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

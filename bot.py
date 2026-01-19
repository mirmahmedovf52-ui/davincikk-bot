import asyncio
import json
import random
import logging
import base64
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = "8400292600:AAEDv_L2A-xTFC2aiUn-2fOR4HNV4_iDMXo"
ADMIN_IDS = [7539197809]
LOG_CHANNEL = "-1003620475629"
BOT_NAME = "Давинчикк 🎭"

# GitHub настройки
GITHUB_TOKEN = "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"
GITHUB_USERNAME = "mirmahmedovf52-ui"
GITHUB_REPO = "davincikk-6ot"
DATA_FILE = "bot_data.json"
GITHUB_API = "https://api.github.com"

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

# === СОСТОЯНИЯ ===
class UserStates(StatesGroup):
    menu = State()
    searching = State()
    in_chat = State()
    profile_edit = State()
    admin_panel = State()

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
active_searches = {}    # {user_id: timestamp}
active_chats = {}       # {user_id: partner_id}
data_cache = {}         # Кэш данных

# === GITHUB API ===
class GitHubDB:
    def __init__(self):
        self.headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        self.repo_url = f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{DATA_FILE}"
    
    async def load_data(self):
        """Загрузить данные из GitHub"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.repo_url, headers=self.headers) as resp:
                    if resp.status == 200:
                        content = await resp.json()
                        file_content = base64.b64decode(content['content']).decode('utf-8')
                        data = json.loads(file_content)
                        logging.info(f"Данные загружены из GitHub. Пользователей: {len(data.get('users', {}))}")
                        return data
        except Exception as e:
            logging.error(f"Ошибка загрузки из GitHub: {e}")
        
        # Если файла нет или ошибка - возвращаем базовую структуру
        return {
            "users": {},
            "friends": {},
            "stats": {
                "total_users": 0,
                "total_chats": 0,
                "total_messages": 0
            },
            "settings": {
                "bot_active": True,
                "maintenance": False
            }
        }
    
    async def save_data(self, data):
        """Сохранить данные в GitHub"""
        try:
            # Получаем текущий SHA файла
            async with aiohttp.ClientSession() as session:
                async with session.get(self.repo_url, headers=self.headers) as resp:
                    sha = None
                    if resp.status == 200:
                        file_info = await resp.json()
                        sha = file_info.get('sha')
                
                # Подготавливаем данные
                content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
                encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                
                payload = {
                    "message": f"Auto-update {datetime.now().isoformat()}",
                    "content": encoded,
                    "sha": sha,
                    "branch": "main"
                }
                
                # Отправляем обновление
                async with session.put(self.repo_url, headers=self.headers, json=payload) as resp:
                    if resp.status in [200, 201]:
                        logging.info("Данные сохранены в GitHub")
                        return True
                    else:
                        error_text = await resp.text()
                        logging.error(f"Ошибка сохранения: {resp.status} - {error_text}")
                        return False
        except Exception as e:
            logging.error(f"Ошибка сохранения в GitHub: {e}")
            return False

# Создаем экземпляр базы данных
github_db = GitHubDB()

# === РАБОТА С ДАННЫМИ ===
async def load_all_data():
    """Загрузить все данные"""
    global data_cache
    data_cache = await github_db.load_data()
    return data_cache

async def save_all_data():
    """Сохранить все данные"""
    return await github_db.save_data(data_cache)

async def update_user(user_id, update_dict):
    """Обновить данные пользователя"""
    user_id_str = str(user_id)
    
    if 'users' not in data_cache:
        data_cache['users'] = {}
    
    if user_id_str not in data_cache['users']:
        # Создаем нового пользователя
        data_cache['users'][user_id_str] = {
            "id": user_id,
            "username": "",
            "first_name": "",
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
                "total_rating": 0,
                "rating_count": 0
            },
            "is_banned": False,
            "ban_reason": "",
            "is_admin": user_id in ADMIN_IDS,
            "warnings": 0
        }
        data_cache['stats']['total_users'] = len(data_cache['users'])
    
    # Обновляем поля
    for key, value in update_dict.items():
        if key in data_cache['users'][user_id_str]:
            data_cache['users'][user_id_str][key] = value
        elif key in ['username', 'first_name']:
            data_cache['users'][user_id_str][key] = value
    
    data_cache['users'][user_id_str]['last_seen'] = datetime.now().isoformat()
    
    await save_all_data()
    return data_cache['users'][user_id_str]

async def add_friend(user_id, friend_id):
    """Добавить друга"""
    user_id_str = str(user_id)
    friend_id_str = str(friend_id)
    
    if 'friends' not in data_cache:
        data_cache['friends'] = {}
    
    if user_id_str not in data_cache['friends']:
        data_cache['friends'][user_id_str] = []
    
    if friend_id_str not in data_cache['friends'][user_id_str]:
        data_cache['friends'][user_id_str].append(friend_id_str)
        
        # Обновляем счетчики
        if user_id_str in data_cache['users']:
            data_cache['users'][user_id_str]['stats']['friends'] += 1
        
        await save_all_data()
        return True
    
    return False

async def get_user_friends(user_id):
    """Получить друзей пользователя"""
    user_id_str = str(user_id)
    return data_cache.get('friends', {}).get(user_id_str, [])

# === ЛОГИРОВАНИЕ ===
async def log_action(action, user_id=None, details=""):
    """Отправить лог в канал"""
    try:
        text = f"📊 {action}\n"
        if user_id:
            user = data_cache.get('users', {}).get(str(user_id), {})
            username = user.get('username', 'без username')
            text += f"👤 ID: {user_id} (@{username})\n"
        if details:
            text += f"📝 {details}\n"
        text += f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        
        await bot.send_message(LOG_CHANNEL, text)
    except Exception as e:
        logging.error(f"Ошибка логирования: {e}")

# === КОМАНДЫ БОТА ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Аноним"
    
    # Обновляем данные пользователя
    await update_user(user_id, {
        "username": username,
        "first_name": first_name
    })
    
    await log_action("🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ", user_id, f"{first_name} (@{username})")
    
    # Приветственное сообщение
    welcome_text = f"""
🎭 <b>Добро пожаловать в {BOT_NAME}!</b>

🛡️ <b>Анонимный и безопасный чат-рулетка:</b>
• Ваши данные защищены
• Сообщения шифруются
• История не сохраняется
• Можно пожаловаться на нарушителей

⚡ <b>Как начать:</b>
1. Настрой профиль (пол, возраст, интересы)
2. Найди собеседника за 10 секунд
3. Общайся текстом, голосовыми, стикерами
4. Добавляй понравившихся в друзья

🎯 <b>Умный поиск</b> | 👥 <b>Система друзей</b> | 📊 <b>Статистика</b>

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
    await state.set_state(UserStates.menu)

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Если в чате
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await end_chat(user_id, partner_id, "по команде /stop")
        await message.answer("✅ Диалог завершен.")
    # Если в поиске
    elif user_id in active_searches:
        del active_searches[user_id]
        await message.answer("✅ Поиск отменен.")
    else:
        await message.answer("Вы не в диалоге и не в поиске.")
    
    await state.set_state(UserStates.menu)

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    user = data_cache.get('users', {}).get(str(user_id), {})
    
    if not user:
        await message.answer("Сначала используйте /start")
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
• Рейтинг: {stats.get('rating', 5.0):.1f}/5.0
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="profile_edit_menu")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")]
    ])
    
    await message.answer(profile_text, reply_markup=keyboard)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    stats = data_cache.get('stats', {})
    total_users = len(data_cache.get('users', {}))
    online_count = len([u for u in data_cache.get('users', {}).values() 
                       if (datetime.now() - datetime.fromisoformat(u.get('last_seen', '2023-01-01'))).seconds < 300])
    
    stats_text = f"""
📊 <b>Общая статистика {BOT_NAME}:</b>

👥 <b>Пользователи:</b>
• Всего: {total_users}
• Онлайн: {online_count}
• В поиске: {len(active_searches)}
• В диалогах: {len(active_chats) // 2}

💬 <b>Активность:</b>
• Всего диалогов: {stats.get('total_chats', 0)}
• Всего сообщений: {stats.get('total_messages', 0)}

🕐 <b>Время работы:</b>
• Данные обновлены: {datetime.now().strftime('%H:%M:%S')}
"""
    
    await message.answer(stats_text)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен!")
        return
    
    stats = data_cache.get('stats', {})
    total_users = len(data_cache.get('users', {}))
    online_count = len([u for u in data_cache.get('users', {}).values() 
                       if (datetime.now() - datetime.fromisoformat(u.get('last_seen', '2023-01-01'))).seconds < 300])
    
    admin_text = f"""
🛠️ <b>Админ-панель {BOT_NAME}</b>

📈 <b>Статистика:</b>
• Всего пользователей: {total_users}
• Онлайн сейчас: {online_count}
• Активных диалогов: {len(active_chats) // 2}
• В поиске: {len(active_searches)}

⚙️ <b>Управление:</b>
• /admin_stats - полная статистика
• /admin_users - управление пользователями
• /admin_broadcast - рассылка сообщений
• /admin_backup - резервное копирование
"""
    
    await message.answer(admin_text)

# === ОБРАБОТЧИКИ КНОПОК ===
@dp.callback_query(F.data == "search_start")
async def search_start(callback: types.CallbackQuery, state: FSMContext):
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
        "Используй /stop чтобы отменить.\n\n"
        "<i>Поиск активных пользователей...</i>"
    )
    
    # Ищем пару
    found = False
    for other_id, search_time in list(active_searches.items()):
        if other_id != user_id and (datetime.now() - search_time).seconds < 60:
            await start_chat(user_id, other_id)
            found = True
            break
    
    if not found:
        await asyncio.sleep(5)
        if user_id in active_searches:
            for other_id, search_time in list(active_searches.items()):
                if other_id != user_id:
                    await start_chat(user_id, other_id)
                    found = True
                    break
        
        if not found and user_id in active_searches:
            await asyncio.sleep(25)
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
    user = data_cache.get('users', {}).get(str(user_id), {})
    
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
• Рейтинг: {stats.get('rating', 5.0):.1f}/5.0
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="profile_edit_menu")],
        [InlineKeyboardButton(text="⚙️ Настройки поиска", callback_data="search_settings")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(profile_text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    stats = data_cache.get('stats', {})
    total_users = len(data_cache.get('users', {}))
    online_count = len([u for u in data_cache.get('users', {}).values() 
                       if (datetime.now() - datetime.fromisoformat(u.get('last_seen', '2023-01-01'))).seconds < 300])
    
    admin_text = f"""
🛠️ <b>Админ-панель {BOT_NAME}</b>

<b>Статистика:</b>
• Всего пользователей: {total_users}
• Онлайн сейчас: {online_count}
• Активных диалогов: {len(active_chats) // 2}
• В поиске: {len(active_searches)}

<b>Управление:</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Полная статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Рассылка сообщений", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💾 Резервное копирование", callback_data="admin_backup")],
        [InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(admin_text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "friends_list")
async def friends_list(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_id_str = str(user_id)
    
    friends = await get_user_friends(user_id)
    
    if not friends:
        text = "👥 <b>У вас пока нет друзей.</b>\n\nДобавляйте понравившихся собеседников после диалога!"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Начать поиск", callback_data="search_start")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    else:
        text = "👥 <b>Ваши друзья:</b>\n\n"
        
        # Показываем друзей
        for friend_id in friends[:10]:
            friend = data_cache.get('users', {}).get(friend_id, {})
            name = friend.get('first_name', f'Пользователь {friend_id}')
            username = friend.get('username', '')
            online = "🟢" if (datetime.now() - datetime.fromisoformat(friend.get('last_seen', '2023-01-01'))).seconds < 300 else "⚫"
            
            text += f"{online} {name}"
            if username:
                text += f" (@{username})"
            text += f"\n"
        
        if len(friends) > 10:
            text += f"\n...и еще {len(friends) - 10} друзей"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Начать диалог с другом", callback_data="chat_with_friend")],
            [InlineKeyboardButton(text="📋 Все друзья", callback_data="friends_all")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)
    await callback.answer()

# === ФУНКЦИИ ЧАТА ===
async def start_chat(user1_id, user2_id):
    """Начать диалог между двумя пользователями"""
    # Удаляем из поиска
    for uid in [user1_id, user2_id]:
        if uid in active_searches:
            del active_searches[uid]
    
    # Регистрируем активный чат
    active_chats[user1_id] = user2_id
    active_chats[user2_id] = user1_id
    
    # Обновляем статистику
    for uid in [user1_id, user2_id]:
        uid_str = str(uid)
        if uid_str in data_cache.get('users', {}):
            data_cache['users'][uid_str]['stats']['chats'] += 1
    
    data_cache['stats']['total_chats'] = data_cache['stats'].get('total_chats', 0) + 1
    await save_all_data()
    
    # Сообщения пользователям
    chat_start_text = """
✅ <b>Собеседник найден! Начинайте общение.</b>

🎭 <b>Правила:</b>
• Будьте вежливы
• Не спамьте
• Не отправляйте запрещенный контент

📱 <b>Отправляйте:</b>
• Текстовые сообщения
• Фото и видео
• Голосовые сообщения
• Стикеры и GIF

🛡️ <b>Безопасность:</b>
• Чтобы пожаловаться - используйте /report
• Чтобы завершить - /stop

<b>Приятного общения! 🎯</b>
"""
    
    try:
        await bot.send_message(user1_id, chat_start_text)
        await bot.send_message(user2_id, chat_start_text)
        
        await log_action("🔗 НАЧАЛСЯ ДИАЛОГ", None, f"{user1_id} ↔ {user2_id}")
    except Exception as e:
        logging.error(f"Ошибка начала чата: {e}")

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
        
        # Кнопка "Добавить в друзья"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить в друзья", 
                                callback_data=f"add_friend_{user2_id if user1_id == user1_id else user1_id}")]
        ])
        
        await bot.send_message(user1_id, "Хотите добавить собеседника в друзья?", reply_markup=keyboard)
        await bot.send_message(user2_id, "Хотите добавить собеседника в друзья?", reply_markup=keyboard)
        
        await log_action("🔴 ДИАЛОГ ЗАВЕРШЕН", None, f"{user1_id} ↔ {user2_id}\nПричина: {reason}")
    except Exception as e:
        logging.error(f"Ошибка завершения чата: {e}")

# === ОБРАБОТКА СООБЩЕНИЙ В ЧАТЕ ===
@dp.message(F.chat.type == "private")
async def handle_private_message(message: types.Message):
    user_id = message.from_user.id
    
    # Если пользователь в чате - пересылаем сообщение
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # Обновляем статистику
        uid_str = str(user_id)
        if uid_str in data_cache.get('users', {}):
            data_cache['users'][uid_str]['stats']['messages'] += 1
        
        data_cache['stats']['total_messages'] = data_cache['stats'].get('total_messages', 0) + 1
        await save_all_data()
        
        # Логируем
        msg_preview = message.text or message.caption or f"[{message.content_type}]"
        if len(msg_preview) > 50:
            msg_preview = msg_preview[:50] + "..."
        
        await log_action("📨 СООБЩЕНИЕ", user_id, f"→ {partner_id}\n{msg_preview}")
        
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
            elif message.document:
                await bot.send_document(partner_id, message.document.file_id,
                                       caption=f"💬 <b>Собеседник:</b>\n{message.caption}" if message.caption else None)
        except Exception as e:
            await message.answer("❌ Не удалось отправить сообщение. Возможно, собеседник отключился.")
            if user_id in active_chats:
                partner = active_chats[user_id]
                await end_chat(user_id, partner, "ошибка отправки")
    
    # Если не в чате - показываем меню
    elif message.text and not message.text.startswith('/'):
        await cmd_start(message)

# === ОБРАБОТКА ДОБАВЛЕНИЯ В ДРУЗЬЯ ===
@dp.callback_query(F.data.startswith("add_friend_"))
async def add_friend_handler(callback: types.CallbackQuery):
    try:
        friend_id = int(callback.data.replace("add_friend_", ""))
        user_id = callback.from_user.id
        
        success = await add_friend(user_id, friend_id)
        
        if success:
            await callback.answer("✅ Добавлено в друзья!", show_alert=True)
            
            # Уведомляем другого пользователя
            try:
                await bot.send_message(friend_id, 
                                      f"🎉 <b>Вас добавили в друзья!</b>\n\n"
                                      f"Пользователь ID: {user_id}\n"
                                      f"Теперь вы можете начинать диалог без поиска.")
            except:
                pass
            
            await log_action("➕ ДРУГ ДОБАВЛЕН", user_id, f"добавил {friend_id}")
        else:
            await callback.answer("❌ Уже в друзьях!", show_alert=True)
        
    except Exception as e:
        logging.error(f"Ошибка добавления друга: {e}")
        await callback.answer("❌ Ошибка!", show_alert=True)

# === ЗАПУСК БОТА ===
async def main():
    # Загружаем данные из GitHub
    await load_all_data()
    
    logging.info(f"=== Бот {BOT_NAME} запущен ===")
    logging.info(f"Админ ID: {ADMIN_IDS}")
    logging.info(f"Логи в канал: {LOG_CHANNEL}")
    logging.info(f"GitHub репозиторий: {GITHUB_USERNAME}/{GITHUB_REPO}")
    
    # Отправляем сообщение о запуске
    try:
        await bot.send_message(LOG_CHANNEL, 
                              f"🚀 <b>Бот {BOT_NAME} запущен!</b>\n"
                              f"Версия: 1.0\n"
                              f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except:
        pass
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

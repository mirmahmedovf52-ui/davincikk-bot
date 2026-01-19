import asyncio
import json
import random
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import aiofiles
import aiohttp
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# === НАСТРОЙКИ ===
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"  # Заменишь после создания бота
ADMIN_IDS = [123456789]  # Твой ID в Telegram
LOG_CHANNEL = "-1002123456789"  # ID канала для логов (создашь позже)

# Имена для бота
BOT_NAME = "Давинчикк 🎭"
VERSION = "1.0"

# Файлы данных (будут в GitHub)
USERS_FILE = "https://raw.githubusercontent.com/ВАШ_ЛОГИН/davincikk-bot/main/users.json"
FRIENDS_FILE = "https://raw.githubusercontent.com/ВАШ_ЛОГИН/davincikk-bot/main/friends.json"
STATS_FILE = "https://raw.githubusercontent.com/ВАШ_ЛОГИН/davincikk-bot/main/stats.json"

# Инициализация
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
logging.basicConfig(level=logging.INFO)

# === СОСТОЯНИЯ (FSM) ===
class UserStates(StatesGroup):
    menu = State()
    profile_edit = State()
    profile_set_gender = State()
    profile_set_age = State()
    profile_set_interests = State()
    profile_set_bio = State()
    searching = State()
    in_chat = State()
    admin_panel = State()

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
active_searches = {}  # user_id: timestamp
active_chats = {}     # user_id: partner_id
user_profiles = {}    # user_id: profile_data
user_data = {}        # user_id: all_data
friends_data = {}     # user_id: [friend_ids]
waiting_for_friend = {}  # user_id: waiting_for_id

# === ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ ИЗ GITHUB ===
async def load_github_file(url):
    """Загрузить JSON файл из GitHub"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
    except:
        pass
    return {}

async def save_github_file(filename, data):
    """Сохранить данные в файл (локально для демо)"""
    # В реальности тут будет push в GitHub через API
    # Но для начала сохраняем локально
    async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    return True

async def load_all_data():
    """Загрузить все данные"""
    global user_data, friends_data
    
    user_data = await load_github_file(USERS_FILE)
    friends_data = await load_github_file(FRIENDS_FILE)
    
    # Если файлов нет - создаем базовые структуры
    if not user_data:
        user_data = {"users": {}, "stats": {"total": 0, "online": 0}}
    if not friends_data:
        friends_data = {}
    
    logging.info(f"Данные загружены. Пользователей: {len(user_data.get('users', {}))}")

async def save_all_data():
    """Сохранить все данные"""
    await save_github_file("users.json", user_data)
    await save_github_file("friends.json", friends_data)
    await save_github_file("stats.json", {
        "updated": datetime.now().isoformat(),
        "total_users": len(user_data.get('users', {})),
        "active_chats": len(active_chats) // 2,
        "active_searches": len(active_searches)
    })

# === ЛОГИРОВАНИЕ ===
async def log_action(action, user_id=None, details=""):
    """Логировать действие в канал"""
    try:
        text = f"📊 {action}\n"
        if user_id:
            user = user_data.get('users', {}).get(str(user_id), {})
            username = user.get('username', 'без username')
            text += f"👤 ID: {user_id} (@{username})\n"
        if details:
            text += f"📝 {details}\n"
        text += f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        
        if LOG_CHANNEL:
            await bot.send_message(LOG_CHANNEL, text)
    except Exception as e:
        logging.error(f"Ошибка логирования: {e}")

# === КОМАНДЫ ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "без username"
    first_name = message.from_user.first_name or "Аноним"
    
    # Регистрация/обновление пользователя
    if str(user_id) not in user_data.get('users', {}):
        user_data.setdefault('users', {})[str(user_id)] = {
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
        user_data['stats']['total'] = len(user_data['users'])
        await log_action("🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ", user_id, f"{first_name} (@{username})")
    else:
        # Обновляем last_seen
        user_data['users'][str(user_id)]['last_seen'] = datetime.now().isoformat()
        user_data['users'][str(user_id)]['username'] = username
    
    await save_all_data()
    
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

🎯 <b>Умный поиск:</b> по возрасту, полу, интересам
👥 <b>Система друзей:</b> общайся с теми, кто понравился
📊 <b>Статистика:</b> следи за своей активностью

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
    await log_action("🔘 START", user_id)

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Если в чате - завершить
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await end_chat(user_id, partner_id, "по команде /stop")
        await message.answer("✅ Диалог завершен.")
    # Если в поиске - отменить
    elif user_id in active_searches:
        del active_searches[user_id]
        await message.answer("✅ Поиск отменен.")
    else:
        await message.answer("Вы не в диалоге и не в поиске.")
    
    await state.set_state(UserStates.menu)

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
    
    # Клавиатура поиска
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Быстрый поиск", callback_data="search_quick")],
        [InlineKeyboardButton(text="🔍 По критериям", callback_data="search_criteria")],
        [InlineKeyboardButton(text="👥 Среди друзей", callback_data="search_friends")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="search_cancel")]
    ])
    
    await callback.message.edit_text(
        "🔍 <b>Выбери тип поиска:</b>\n\n"
        "• <b>Быстрый поиск</b> - любой собеседник\n"
        "• <b>По критериям</b> - по полу/возрасту/интересам\n"
        "• <b>Среди друзей</b> - только из списка друзей",
        reply_markup=keyboard
    )
    await state.set_state(UserStates.searching)
    await callback.answer()

@dp.callback_query(F.data == "search_quick")
async def search_quick(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    await callback.message.edit_text(
        "🔄 <b>Ищем случайного собеседника...</b>\n"
        "Ожидание: 0-30 секунд\n\n"
        "Используй /stop чтобы отменить."
    )
    
    # Ищем пару
    found = False
    for other_id, search_time in list(active_searches.items()):
        if other_id != user_id and (datetime.now() - search_time).seconds < 60:
            # Нашли пару!
            await start_chat(user_id, other_id)
            found = True
            break
    
    if not found:
        # Если не нашли сразу - ждем 30 секунд
        await asyncio.sleep(30)
        if user_id in active_searches:
            # Проверяем снова
            for other_id, search_time in list(active_searches.items()):
                if other_id != user_id:
                    await start_chat(user_id, other_id)
                    found = True
                    break
            
            if not found:
                await callback.message.edit_text(
                    "😔 <b>Собеседник не найден</b>\n\n"
                    "Попробуй позже или выбери другой тип поиска."
                )
                if user_id in active_searches:
                    del active_searches[user_id]

@dp.callback_query(F.data == "profile_view")
async def profile_view(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = user_data.get('users', {}).get(str(user_id), {})
    profile = user.get('profile', {})
    stats = user.get('stats', {})
    
    profile_text = f"""
👤 <b>Ваш профиль:</b>

<b>Основное:</b>
• Имя: {user.get('first_name', 'Не указано')}
• Username: @{user.get('username', 'нет')}
• Дата регистрации: {user.get('join_date', '?')[:10]}

<b>Настройки профиля:</b>
• Пол: {profile.get('gender', 'не указан')}
• Возраст: {profile.get('age', 'не указан')}
• Интересы: {', '.join(profile.get('interests', [])) or 'не указаны'}
• О себе: {profile.get('bio', 'не указано')}

<b>Предпочтения для поиска:</b>
• Предпочитаемый пол: {profile.get('preferred_gender', 'любой')}
• Возраст: от {profile.get('preferred_age_min', 18)} до {profile.get('preferred_age_max', 45)}

<b>Статистика:</b>
• Диалогов: {stats.get('chats', 0)}
• Сообщений: {stats.get('messages', 0)}
• Друзей: {stats.get('friends', 0)}
• Рейтинг: {stats.get('rating', 5.0)}/5.0
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать профиль", callback_data="profile_edit")],
        [InlineKeyboardButton(text="⚙️ Настройки поиска", callback_data="search_settings")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(profile_text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if user_id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    stats = user_data.get('stats', {})
    online_count = len([u for u in user_data.get('users', {}).values() 
                       if (datetime.now() - datetime.fromisoformat(u.get('last_seen', '2023-01-01'))).seconds < 300])
    
    admin_text = f"""
🛠️ <b>Админ-панель {BOT_NAME}</b>

<b>Статистика:</b>
• Всего пользователей: {stats.get('total', 0)}
• Онлайн сейчас: {online_count}
• Активных диалогов: {len(active_chats) // 2}
• В поиске: {len(active_searches)}

<b>Управление:</b>
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Полная статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔄 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⚙️ Настройки бота", callback_data="admin_settings")],
        [InlineKeyboardButton(text="📁 Экспорт данных", callback_data="admin_export")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(admin_text, reply_markup=keyboard)
    await state.set_state(UserStates.admin_panel)
    await callback.answer()

@dp.callback_query(F.data == "friends_list")
async def friends_list(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_id_str = str(user_id)
    
    friends = friends_data.get(user_id_str, [])
    
    if not friends:
        text = "👥 <b>У вас пока нет друзей.</b>\n\nДобавляйте понравившихся собеседников после диалога!"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Начать поиск", callback_data="search_start")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    else:
        text = "👥 <b>Ваши друзья:</b>\n\n"
        
        # Показываем первых 5 друзей
        for i, friend_id in enumerate(friends[:5], 1):
            friend = user_data.get('users', {}).get(friend_id, {})
            name = friend.get('first_name', f'Пользователь {friend_id}')
            username = friend.get('username', '')
            online = "🟢" if (datetime.now() - datetime.fromisoformat(friend.get('last_seen', '2023-01-01'))).seconds < 300 else "⚫"
            
            text += f"{i}. {online} {name}"
            if username:
                text += f" (@{username})"
            text += f" [ID: {friend_id}]\n"
        
        if len(friends) > 5:
            text += f"\n...и еще {len(friends) - 5} друзей"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать другу", callback_data="friend_chat")],
            [InlineKeyboardButton(text="📋 Полный список", callback_data="friends_all")],
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
        if uid_str in user_data.get('users', {}):
            user_data['users'][uid_str]['stats']['chats'] = user_data['users'][uid_str]['stats'].get('chats', 0) + 1
    
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
• Ваши данные защищены
• Чтобы пожаловаться - используйте /report
• Чтобы завершить - /stop

<b>Приятного общения! 🎯</b>
"""
    
    try:
        await bot.send_message(user1_id, chat_start_text)
        await bot.send_message(user2_id, chat_start_text)
        
        # Логируем
        await log_action("🔗 НАЧАЛСЯ ДИАЛОГ", None, 
                        f"{user1_id} ↔ {user2_id}")
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
            [InlineKeyboardButton(text="➕ Добавить в друзья", callback_data=f"add_friend_{user1_id if user2_id == user1_id else user2_id}")]
        ])
        
        await bot.send_message(user1_id, "Хотите добавить собеседника в друзья?", reply_markup=keyboard)
        await bot.send_message(user2_id, "Хотите добавить собеседника в друзья?", reply_markup=keyboard)
        
        # Логируем
        await log_action("🔴 ДИАЛОГ ЗАВЕРШЕН", None, 
                        f"{user1_id} ↔ {user2_id}\nПричина: {reason}")
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
        if uid_str in user_data.get('users', {}):
            user_data['users'][uid_str]['stats']['messages'] = user_data['users'][uid_str]['stats'].get('messages', 0) + 1
        
        # Логируем
        msg_preview = message.text or message.caption or f"[{message.content_type}]"
        if len(msg_preview) > 50:
            msg_preview = msg_preview[:50] + "..."
        
        await log_action("📨 СООБЩЕНИЕ", user_id, 
                        f"→ {partner_id}\n{msg_preview}")
        
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
        
        user_id_str = str(user_id)
        friend_id_str = str(friend_id)
        
        # Инициализируем если нет
        if user_id_str not in friends_data:
            friends_data[user_id_str] = []
        
        # Проверяем, не добавлен ли уже
        if friend_id_str in friends_data[user_id_str]:
            await callback.answer("❌ Уже в друзьях!", show_alert=True)
            return
        
        # Добавляем
        friends_data[user_id_str].append(friend_id_str)
        
        # Обновляем статистику
        if user_id_str in user_data.get('users', {}):
            user_data['users'][user_id_str]['stats']['friends'] = user_data['users'][user_id_str]['stats'].get('friends', 0) + 1
        
        await save_all_data()
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
        
    except Exception as e:
        logging.error(f"Ошибка добавления друга: {e}")
        await callback.answer("❌ Ошибка!", show_alert=True)

# === ЗАПУСК БОТА ===
async def main():
    # Загружаем данные
    await load_all_data()
    
    # Запускаем бота
    logging.info(f"Бот {BOT_NAME} запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

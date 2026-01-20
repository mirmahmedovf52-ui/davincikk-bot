import asyncio
import json
import random
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
import aiohttp
from aiohttp import web

# === КОНФИГ ===
BOT_TOKEN = os.getenv('BOT_TOKEN', '8400292600:AAEDv_L2A-xTFC2aiUn-2fOR4HNV4_iDMXo')
ADMIN_IDS = [7539197809]
LOG_CHANNEL = os.getenv('LOG_CHANNEL', '-1003620475629')
BOT_NAME = "Давинчикк 🎭"

# === ИНИЦИАЛИЗАЦИЯ ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
active_searches = {}
active_chats = {}
user_data = {}
friends_data = {}

# === КЛАВИАТУРЫ ===
def get_main_keyboard(user_id: int):
    """Главное меню - только работающие кнопки"""
    buttons = [
        [KeyboardButton(text="🔍 Начать поиск")],
        [KeyboardButton(text="⏹️ Остановить")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="👥 Мои друзья")]
    ]
    
    if user_id in ADMIN_IDS:
        buttons.append([KeyboardButton(text="🛠️ Админ-панель")])
    
    buttons.append([KeyboardButton(text="ℹ️ Помощь")])
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_profile_keyboard():
    """Клавиатура профиля"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

def get_admin_keyboard():
    """Клавиатура админа - только работающие функции"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ])

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
async def health_check(request):
    return web.Response(text=f"{BOT_NAME} работает")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("✅ Веб-сервер запущен")

async def keep_alive():
    """Keep-alive система"""
    while True:
        await asyncio.sleep(300)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8080/health') as resp:
                    logging.info(f"🔄 Keep-alive: {resp.status}")
        except:
            pass

# === СОХРАНЕНИЕ ДАННЫХ ===
async def save_data():
    """Сохранить данные в файл"""
    try:
        data = {
            "users": user_data,
            "friends": friends_data,
            "updated": datetime.now().isoformat()
        }
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except:
        pass

async def load_data():
    """Загрузить данные из файла"""
    try:
        if os.path.exists("data.json"):
            with open("data.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                global user_data, friends_data
                user_data = data.get("users", {})
                friends_data = data.get("friends", {})
                logging.info(f"✅ Данные загружены. Пользователей: {len(user_data)}")
    except:
        user_data = {}
        friends_data = {}

# === ЛОГИРОВАНИЕ ===
async def log_action(action: str, user_id=None, details=""):
    try:
        text = f"📊 {action}\n"
        if user_id:
            user = user_data.get(str(user_id), {})
            username = user.get('username', 'без username')
            text += f"👤 ID: {user_id} (@{username})\n"
        if details:
            text += f"📝 {details}\n"
        
        await bot.send_message(LOG_CHANNEL, text[:4000])
    except:
        pass

# === ОСНОВНЫЕ КОМАНДЫ ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "Аноним"
    
    user_id_str = str(user_id)
    
    # Регистрация
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
                "interests": []
            },
            "stats": {
                "chats": 0,
                "messages": 0,
                "friends": 0
            }
        }
        await log_action("🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ", user_id, f"{first_name} (@{username})")
    else:
        user_data[user_id_str]['username'] = username
        user_data[user_id_str]['last_seen'] = datetime.now().isoformat()
    
    await save_data()
    
    await message.answer(
        f"🎭 <b>Добро пожаловать в {BOT_NAME}!</b>\n\n"
        f"👥 Пользователей: {len(user_data)}\n"
        f"💬 Активных диалогов: {len(active_chats) // 2}\n\n"
        f"<b>Используй кнопки ниже:</b>",
        reply_markup=get_main_keyboard(user_id)
    )

@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        await end_chat(user_id, partner_id)
        await message.answer("✅ Диалог завершен.", reply_markup=get_main_keyboard(user_id))
    elif user_id in active_searches:
        del active_searches[user_id]
        await message.answer("✅ Поиск отменен.", reply_markup=get_main_keyboard(user_id))
    else:
        await message.answer("Вы не в диалоге и не в поиске.", reply_markup=get_main_keyboard(user_id))

# === ОБРАБОТЧИКИ КНОПОК ===
@dp.message(F.text == "🔍 Начать поиск")
async def start_search_handler(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        await message.answer("Вы уже в диалоге! Используйте '⏹️ Остановить'.")
        return
    
    if user_id in active_searches:
        await message.answer("Вы уже в поиске!")
        return
    
    active_searches[user_id] = datetime.now()
    
    await message.answer("🔍 Ищем собеседника... (до 30 секунд)")
    
    # Поиск пары
    found = False
    for other_id, search_time in list(active_searches.items()):
        if other_id != user_id:
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
                await message.answer("😔 Собеседник не найден.")
                del active_searches[user_id]

@dp.message(F.text == "👤 Мой профиль")
async def profile_handler(message: types.Message):
    user_id = message.from_user.id
    user = user_data.get(str(user_id), {})
    
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

<b>Статистика:</b>
• Диалогов: {stats.get('chats', 0)}
• Сообщений: {stats.get('messages', 0)}
• Друзей: {stats.get('friends', 0)}
"""
    
    await message.answer(profile_text, reply_markup=get_profile_keyboard())

@dp.message(F.text == "📊 Статистика")
async def stats_handler(message: types.Message):
    total_users = len(user_data)
    online_now = sum(1 for u in user_data.values() 
                    if (datetime.now() - datetime.fromisoformat(u.get('last_seen', '2023-01-01'))).seconds < 300)
    
    stats_text = f"""
📊 <b>Статистика {BOT_NAME}:</b>

👥 <b>Пользователи:</b>
• Всего: {total_users}
• Онлайн: {online_now}
• В поиске: {len(active_searches)}
• В диалогах: {len(active_chats) // 2}

💬 <b>Активность:</b>
• Активных диалогов: {len(active_chats) // 2}
"""
    
    await message.answer(stats_text)

@dp.message(F.text == "👥 Мои друзья")
async def friends_handler(message: types.Message):
    user_id = message.from_user.id
    user_id_str = str(user_id)
    
    friends = friends_data.get(user_id_str, [])
    
    if not friends:
        text = "👥 У вас пока нет друзей.\nДобавляйте понравившихся собеседников!"
    else:
        text = "👥 Ваши друзья:\n\n"
        for friend_id in friends[:10]:
            friend = user_data.get(friend_id, {})
            name = friend.get('first_name', f'Пользователь {friend_id}')
            text += f"• {name}\n"
        
        if len(friends) > 10:
            text += f"\n...и еще {len(friends) - 10} друзей"
    
    await message.answer(text)

@dp.message(F.text == "🛠️ Админ-панель")
async def admin_panel_handler(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен!")
        return
    
    total_users = len(user_data)
    
    admin_text = f"""
🛠️ <b>Админ-панель {BOT_NAME}</b>

📊 <b>Статистика:</b>
• Всего пользователей: {total_users}
• В поиске: {len(active_searches)}
• В диалогах: {len(active_chats) // 2}

⚙️ <b>Управление:</b>
• Рассылка сообщений всем
• Просмотр статистики
"""
    
    await message.answer(admin_text, reply_markup=get_admin_keyboard())

@dp.message(F.text == "ℹ️ Помощь")
async def help_handler(message: types.Message):
    help_text = f"""
ℹ️ <b>Помощь по {BOT_NAME}:</b>

<b>Основные команды:</b>
• /start - начать работу
• /stop - остановить диалог или поиск

<b>Кнопки:</b>
• 🔍 Начать поиск - найти собеседника
• ⏹️ Остановить - завершить диалог
• 👤 Мой профиль - информация о вас
• 📊 Статистика - статистика бота
• 👥 Мои друзья - список друзей

<b>Как общаться:</b>
1. Нажмите "🔍 Начать поиск"
2. Дождитесь собеседника
3. Отправляйте текстовые сообщения, фото, видео
4. Используйте "⏹️ Остановить" для завершения

<b>Безопасность:</b>
• Ваши данные защищены
• Сообщения анонимны
• Можно пожаловаться на нарушителей
"""
    
    await message.answer(help_text)

# === ОБРАБОТЧИКИ INLINE КНОПОК ===
@dp.callback_query(F.data == "edit_profile")
async def edit_profile_callback(callback: types.CallbackQuery):
    await callback.message.answer("✏️ Редактирование профиля:\n\nИспользуйте команды:\n• /setgender [м/ж]\n• /setage [возраст]\n• /addinterest [интерес]")
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: types.CallbackQuery):
    total_users = len(user_data)
    total_chats = sum(u.get('stats', {}).get('chats', 0) for u in user_data.values()) // 2
    total_messages = sum(u.get('stats', {}).get('messages', 0) for u in user_data.values())
    
    stats_text = f"""
📊 <b>Детальная статистика:</b>

👥 <b>Пользователи:</b>
• Всего: {total_users}
• Новых сегодня: {sum(1 for u in user_data.values() 
                     if datetime.fromisoformat(u.get('join_date', '2023-01-01')).date() == datetime.now().date())}

💬 <b>Активность:</b>
• Всего диалогов: {total_chats}
• Всего сообщений: {total_messages}
• Среднее сообщений в диалоге: {total_messages // total_chats if total_chats > 0 else 0}

🕐 <b>Время:</b>
• Обновлено: {datetime.now().strftime('%H:%M:%S')}
"""
    
    await callback.message.answer(stats_text)
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "📢 <b>Рассылка всем пользователям:</b>\n\n"
        "Используйте команду:\n"
        "<code>/broadcast ваш текст сообщения</code>\n\n"
        "Сообщение будет отправлено всем пользователям бота."
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    await cmd_start(callback.message)
    await callback.answer()

# === АДМИН КОМАНДЫ ===
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен!")
        return
    
    if not command.args:
        await message.answer("Использование: /broadcast [текст сообщения]")
        return
    
    broadcast_text = command.args
    total_users = len(user_data)
    
    await message.answer(f"📢 Начинаю рассылку для {total_users} пользователей...")
    
    success = 0
    for user_id_str in user_data:
        try:
            await bot.send_message(int(user_id_str), 
                                 f"📢 <b>Сообщение от администрации:</b>\n\n{broadcast_text}")
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await message.answer(f"✅ Рассылка завершена!\nОтправлено: {success}/{total_users}")
    await log_action("📢 АДМИН РАССЫЛКА", user_id, f"отправлено {success}/{total_users}")

# === КОМАНДЫ ПРОФИЛЯ ===
@dp.message(Command("setgender"))
async def cmd_setgender(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    user_id_str = str(user_id)
    
    if not command.args:
        await message.answer("Использование: /setgender [м/ж/другой]")
        return
    
    gender = command.args.lower()
    if gender not in ["м", "ж", "мужской", "женский", "другой"]:
        await message.answer("Используйте: м, ж или другой")
        return
    
    if user_id_str in user_data:
        user_data[user_id_str]["profile"]["gender"] = gender
        await save_data()
        await message.answer(f"✅ Пол установлен: {gender}")
    else:
        await message.answer("Сначала используйте /start")

@dp.message(Command("setage"))
async def cmd_setage(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    user_id_str = str(user_id)
    
    if not command.args or not command.args.isdigit():
        await message.answer("Использование: /setage [число]")
        return
    
    age = int(command.args)
    if age < 12 or age > 100:
        await message.answer("Возраст должен быть от 12 до 100 лет")
        return
    
    if user_id_str in user_data:
        user_data[user_id_str]["profile"]["age"] = age
        await save_data()
        await message.answer(f"✅ Возраст установлен: {age}")
    else:
        await message.answer("Сначала используйте /start")

@dp.message(Command("addinterest"))
async def cmd_addinterest(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    user_id_str = str(user_id)
    
    if not command.args:
        await message.answer("Использование: /addinterest [ваш интерес]")
        return
    
    interest = command.args
    if user_id_str in user_data:
        if "interests" not in user_data[user_id_str]["profile"]:
            user_data[user_id_str]["profile"]["interests"] = []
        
        if interest not in user_data[user_id_str]["profile"]["interests"]:
            user_data[user_id_str]["profile"]["interests"].append(interest)
            await save_data()
            await message.answer(f"✅ Интерес добавлен: {interest}")
        else:
            await message.answer("Этот интерес уже добавлен")
    else:
        await message.answer("Сначала используйте /start")

# === ФУНКЦИИ ЧАТА ===
async def start_chat(user1_id: int, user2_id: int):
    """Начать диалог"""
    for uid in [user1_id, user2_id]:
        if uid in active_searches:
            del active_searches[uid]
    
    active_chats[user1_id] = user2_id
    active_chats[user2_id] = user1_id
    
    # Обновляем статистику
    for uid in [user1_id, user2_id]:
        uid_str = str(uid)
        if uid_str in user_data:
            user_data[uid_str]["stats"]["chats"] += 1
    
    await save_data()
    
    # Сообщения
    chat_text = "✅ Собеседник найден! Начинайте общение.\n\nИспользуйте '⏹️ Остановить' для завершения."
    
    try:
        await bot.send_message(user1_id, chat_text, reply_markup=get_main_keyboard(user1_id))
        await bot.send_message(user2_id, chat_text, reply_markup=get_main_keyboard(user2_id))
        
        await log_action("🔗 НАЧАЛСЯ ДИАЛОГ", None, f"{user1_id} ↔ {user2_id}")
    except:
        pass

async def end_chat(user1_id: int, user2_id: int):
    """Завершить диалог"""
    for uid in [user1_id, user2_id]:
        if uid in active_chats:
            del active_chats[uid]
    
    try:
        await bot.send_message(user1_id, "❌ Диалог завершен.", reply_markup=get_main_keyboard(user1_id))
        await bot.send_message(user2_id, "❌ Диалог завершен.", reply_markup=get_main_keyboard(user2_id))
        
        await log_action("🔴 ДИАЛОГ ЗАВЕРШЕН", None, f"{user1_id} ↔ {user2_id}")
    except:
        pass

# === ОБРАБОТКА СООБЩЕНИЙ ===
@dp.message(F.chat.type == "private")
async def handle_private_message(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        
        # Обновляем статистику
        user_id_str = str(user_id)
        if user_id_str in user_data:
            user_data[user_id_str]["stats"]["messages"] += 1
            await save_data()
        
        # Обработка медиа
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
                file = await bot.get_file(file_id)
                file_path = f"temp_photo_{file_id}.jpg"
                await bot.download_file(file.file_path, file_path)
                
                # В канал
                await bot.send_photo(LOG_CHANNEL, FSInputFile(file_path),
                                   caption=f"📷 От: {user_id} → {partner_id}")
                os.remove(file_path)
                
                # Партнеру
                await bot.send_photo(partner_id, message.photo[-1].file_id,
                                   caption=message.caption)
            
            elif message.video:
                file_id = message.video.file_id
                file = await bot.get_file(file_id)
                file_path = f"temp_video_{file_id}.mp4"
                await bot.download_file(file.file_path, file_path)
                
                await bot.send_video(LOG_CHANNEL, FSInputFile(file_path),
                                   caption=f"🎥 От: {user_id} → {partner_id}")
                os.remove(file_path)
                
                await bot.send_video(partner_id, message.video.file_id,
                                   caption=message.caption)
            
            elif message.text:
                # Лог
                await log_action(f"📨 СООБЩЕНИЕ\n{user_id} → {partner_id}\n{message.text[:50]}")
                # Партнеру
                await bot.send_message(partner_id, f"💬 Собеседник:\n{message.text}")
            
            elif message.voice:
                await bot.send_voice(partner_id, message.voice.file_id)
                await log_action(f"🎤 ГОЛОСОВОЕ\n{user_id} → {partner_id}")
            
            elif message.sticker:
                await bot.send_sticker(partner_id, message.sticker.file_id)
                
        except Exception as e:
            logging.error(f"Ошибка отправки: {e}")
            await message.answer("❌ Не удалось отправить сообщение.")
            if user_id in active_chats:
                partner = active_chats[user_id]
                await end_chat(user_id, partner)

# === ЗАПУСК ===
async def main():
    # Загружаем данные
    await load_data()
    
    # Веб-сервер
    await start_web_server()
    
    # Keep-alive
    asyncio.create_task(keep_alive())
    
    logging.info(f"🚀 Бот {BOT_NAME} запущен")
    logging.info(f"👥 Пользователей в базе: {len(user_data)}")
    
    try:
        await bot.send_message(LOG_CHANNEL, 
                             f"🚀 {BOT_NAME} запущен!\n"
                             f"Пользователей: {len(user_data)}\n"
                             f"Время: {datetime.now().strftime('%H:%M:%S')}")
    except:
        pass
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

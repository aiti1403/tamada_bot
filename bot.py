import asyncio
import logging
import random
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.types import BotCommand, BotCommandScopeDefault, ChatMemberUpdated

# Конфигурация бота
BOT_TOKEN = "7956575657:AAE-wEUTf6twUrFTgMxLjshmSzrriWf9Ubc"  # Замените на ваш токен
ADMIN_ID = 475354897  # Замените на ваш ID администратора

# Настройка логирования
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Класс для callback данных
class ContestCallback(CallbackData, prefix="contest"):
    action: str
    contest_id: str

# Класс для представления конкурса
class Contest:
    def __init__(self, contest_id, title, description, duration_minutes, chat_id=None):
        self.id = contest_id
        self.title = title
        self.description = description
        self.end_time = datetime.now() + timedelta(minutes=duration_minutes)
        self.participants = []  # список кортежей (user_id, user_name)
        self.is_active = True
        self.chat_id = chat_id  # ID чата, где был создан конкурс
    
    def add_participant(self, user_id, user_name):
        # Проверяем, не участвует ли пользователь уже
        for participant_id, _ in self.participants:
            if participant_id == user_id:
                return False
        
        self.participants.append((user_id, user_name))
        return True
    
    def is_expired(self):
        return datetime.now() > self.end_time
    
    def remaining_minutes(self):
        delta = self.end_time - datetime.now()
        return max(0, int(delta.total_seconds() // 60))

# Менеджер конкурсов
class ContestManager:
    def __init__(self):
        self.contests = {}  # {contest_id: Contest}
        self.next_id = 1
    
    def create_contest(self, title, description, duration_minutes, chat_id=None):
        contest_id = f"contest_{self.next_id}"
        self.next_id += 1
        
        contest = Contest(contest_id, title, description, duration_minutes, chat_id)
        self.contests[contest_id] = contest
        
        logger.info(f"Создан новый конкурс: {contest_id} - {title} в чате {chat_id}")
        return contest
    
    def get_contest(self, contest_id):
        return self.contests.get(contest_id)
    
    def get_active_contests(self, chat_id=None):
        if chat_id:
            return {cid: contest for cid, contest in self.contests.items() 
                    if contest.is_active and not contest.is_expired() and 
                    (contest.chat_id == chat_id or contest.chat_id is None)}
        else:
            return {cid: contest for cid, contest in self.contests.items() 
                    if contest.is_active and not contest.is_expired()}
    
    def end_contest(self, contest_id):
        if contest_id in self.contests:
            self.contests[contest_id].is_active = False
            logger.info(f"Конкурс {contest_id} завершен")
            return True
        return False

# Создаем менеджер конкурсов
contest_manager = ContestManager()

# Состояния FSM для создания конкурса
class ContestStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_duration = State()

# Установка команд бота
async def set_commands():
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="create", description="Создать новый конкурс (только для админа)"),
        BotCommand(command="list", description="Показать активные конкурсы"),
        BotCommand(command="debug", description="Отладочная информация (только для админа)")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

# Обработчик команды /start
@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я бот для проведения конкурсов.\n"
        "Если вы администратор, используйте /create для создания нового конкурса.\n"
        "Чтобы увидеть список активных конкурсов, используйте /list."
    )

# Проверка на админа в группе
async def is_admin(user_id, chat_id):
    if user_id == ADMIN_ID:
        return True
    
    if chat_id == user_id:  # Личный чат
        return False
    
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора: {e}")
        return False

# Обработчик команды /create
@router.message(Command("create"))
async def cmd_create(message: Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем, является ли пользователь администратором
    if not await is_admin(user_id, chat_id):
        await message.answer("Эта команда доступна только администраторам.")
        return
    
    # Сохраняем chat_id для дальнейшего использования
    await state.update_data(chat_id=chat_id)
    
    await message.answer("Давайте создадим новый конкурс. Введите название конкурса:")
    await state.set_state(ContestStates.waiting_for_title)

# Обработчик ввода названия конкурса
@router.message(ContestStates.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Отлично! Теперь введите описание конкурса:")
    await state.set_state(ContestStates.waiting_for_description)

# Обработчик ввода описания конкурса
@router.message(ContestStates.waiting_for_description)
async def process_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer(
        "Теперь укажите продолжительность конкурса в минутах (целое число):"
    )
    await state.set_state(ContestStates.waiting_for_duration)

# Обработчик ввода продолжительности конкурса
@router.message(ContestStates.waiting_for_duration)
async def process_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text)
        if duration <= 0:
            raise ValueError("Продолжительность должна быть положительным числом")
        
        data = await state.get_data()
        title = data["title"]
        description = data["description"]
        chat_id = data.get("chat_id", message.chat.id)
        
        # Создаем новый конкурс
        contest = contest_manager.create_contest(title, description, duration, chat_id)
        
        # Создаем клавиатуру с кнопкой участия
        builder = InlineKeyboardBuilder()
        callback_data = ContestCallback(action="join", contest_id=contest.id).pack()
        builder.button(text="Участвовать", callback_data=callback_data)
        
        # Отправляем сообщение о новом конкурсе
        await message.answer(
            f"🎉 Новый конкурс создан!\n\n"
            f"📌 <b>{title}</b>\n\n"
            f"{description}\n\n"
            f"⏱ Конкурс завершится через {duration} минут.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
        # Запускаем таймер для завершения конкурса
        asyncio.create_task(end_contest_timer(contest.id, duration))
        
        await state.clear()
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число минут.")

# Функция таймера для завершения конкурса
async def end_contest_timer(contest_id, duration):
    await asyncio.sleep(duration * 60)  # Переводим минуты в секунды
    
    logger.info(f"Таймер для конкурса {contest_id} завершен")
    
    contest = contest_manager.get_contest(contest_id)
    if contest and contest.is_active:
        participants = contest.participants
        
        if participants:
            # Выбираем случайного победителя
            winner_id, winner_name = random.choice(participants)
            
            # Формируем сообщение о победителе
            winner_message = (
                f"🎉 Конкурс '{contest.title}' завершен!\n\n"
                f"Победитель: {winner_name} (ID: {winner_id})\n"
                f"Всего участников: {len(participants)}"
            )
            
            # Отправляем сообщение о победителе
            if contest.chat_id:
                # Если конкурс был в группе или канале, отправляем результат туда
                await bot.send_message(contest.chat_id, winner_message)
            
            # Также отправляем админу
            if contest.chat_id != ADMIN_ID:
                await bot.send_message(ADMIN_ID, winner_message)
            
            # Уведомляем победителя в личку
            try:
                await bot.send_message(
                    winner_id,
                    f"🎉 Поздравляем! Вы выиграли в конкурсе '{contest.title}'!"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение победителю: {e}")
        else:
            no_participants_message = f"⚠️ Конкурс '{contest.title}' завершен, но никто не принял участие."
            
            # Отправляем сообщение о том, что никто не участвовал
            if contest.chat_id:
                await bot.send_message(contest.chat_id, no_participants_message)
            
            # Также отправляем админу
            if contest.chat_id != ADMIN_ID:
                await bot.send_message(ADMIN_ID, no_participants_message)
        
        # Отмечаем конкурс как неактивный
        contest_manager.end_contest(contest_id)

# Обработчик нажатия на кнопку "Участвовать"
@router.callback_query(ContestCallback.filter(F.action == "join"))
async def process_join(callback: CallbackQuery, callback_data: ContestCallback):
    contest_id = callback_data.contest_id
    
    logger.info(f"Получен callback для участия в конкурсе: {contest_id}")
    
    contest = contest_manager.get_contest(contest_id)
    if not contest or not contest.is_active or contest.is_expired():
        await callback.answer("Этот конкурс уже завершен или не существует.", show_alert=True)
        return
    
    user_id = callback.from_user.id
    user_name = callback.from_user.full_name
    
    # Добавляем пользователя в список участников
    if contest.add_participant(user_id, user_name):
        logger.info(f"Пользователь {user_id} ({user_name}) добавлен в конкурс {contest_id}")
        await callback.answer("Вы успешно зарегистрированы в конкурсе!", show_alert=True)
    else:
        await callback.answer("Вы уже участвуете в этом конкурсе!", show_alert=True)

# Обработчик команды /list для просмотра активных конкурсов
@router.message(Command("list"))
async def cmd_list(message: Message):
    chat_id = message.chat.id
    
    # Получаем конкурсы для текущего чата
    active_contests = contest_manager.get_active_contests(chat_id)
    
    if not active_contests:
        await message.answer("В данный момент нет активных конкурсов.")
        return
    
    text = "📋 Список активных конкурсов:\n\n"
    
    for contest_id, contest in active_contests.items():
        text += (
            f"📌 <b>{contest.title}</b>\n"
            f"{contest.description}\n"
            f"⏱ Осталось времени: {contest.remaining_minutes()} мин.\n"
            f"👥 Участников: {len(contest.participants)}\n\n"
        )
    
    # Создаем клавиатуру для каждого конкурса
    builder = InlineKeyboardBuilder()
    for contest_id, contest in active_contests.items():
        callback_data = ContestCallback(action="join", contest_id=contest.id).pack()
        builder.button(
            text=f"Участвовать в '{contest.title}'", 
            callback_data=callback_data
        )
    builder.adjust(1)  # Размещаем кнопки по одной в ряд
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# Обработчик для отладки (только для админа)
@router.message(Command("debug"))
async def cmd_debug(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем права администратора
    if user_id != ADMIN_ID and not await is_admin(user_id, chat_id):
        return
    
    active_contests = contest_manager.get_active_contests()
    all_contests = contest_manager.contests
    
    debug_info = (
        f"Всего конкурсов: {len(all_contests)}\n"
        f"Активных конкурсов: {len(active_contests)}\n\n"
    )
    
    for contest_id, contest in all_contests.items():
        status = "активен" if contest.is_active and not contest.is_expired() else "неактивен"
        chat_info = f"чат {contest.chat_id}" if contest.chat_id else "личный чат"
        debug_info += (
            f"Конкурс {contest_id}:\n"
            f"- Название: {contest.title}\n"
            f"- Статус: {status}\n"
            f"- Чат: {chat_info}\n"
            f"- Участники: {len(contest.participants)}\n"
            f"- Осталось: {contest.remaining_minutes()} мин.\n\n"
        )
    
    # Разбиваем длинное сообщение, если нужно
    if len(debug_info) > 4000:
        parts = [debug_info[i:i+4000] for i in range(0, len(debug_info), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(debug_info)

# Обработчик добавления бота в группу
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> IS_MEMBER))
async def bot_added_to_group(event: ChatMemberUpdated):
    chat_id = event.chat.id
    chat_title = event.chat.title
    
    logger.info(f"Бот добавлен в группу: {chat_title} (ID: {chat_id})")
    
    # Отправляем приветственное сообщение в группу
    await bot.send_message(
        chat_id,
        "Привет! Я бот для проведения конкурсов.\n"
        "Администраторы группы могут использовать /create для создания нового конкурса.\n"
        "Чтобы увидеть список активных конкурсов, используйте /list."
    )

# Обработчик удаления бота из группы
@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER >> IS_NOT_MEMBER))
async def bot_removed_from_group(event: ChatMemberUpdated):
    chat_id = event.chat.id
    chat_title = event.chat.title
    
    logger.info(f"Бот удален из группы: {chat_title} (ID: {chat_id})")

# Запуск бота
async def main():
    # Устанавливаем команды бота
    await set_commands()
    
    logger.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

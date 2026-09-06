"""
Инициализация и запуск Telegram-бота (aiogram 3.x).
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.config import settings
from app.bot.handlers import user, worker, admin

logger = logging.getLogger(__name__)

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()


async def set_commands():
    commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="pay", description="💳 Получить реквизиты для оплаты"),
        BotCommand(command="help", description="ℹ️ Помощь"),
    ]
    await bot.set_my_commands(commands)


async def start_bot():
    logger.info("Регистрация обработчиков...")
    dp.include_router(user.router)
    dp.include_router(worker.router)
    dp.include_router(admin.router)
    await set_commands()
    logger.info("Команды бота установлены.")
    logger.info("Запуск поллинга...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при поллинге: {e}")


async def stop_bot():
    try:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")
    except Exception as e:
        logger.error(f"Ошибка при закрытии сессии: {e}")

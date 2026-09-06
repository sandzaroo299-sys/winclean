"""
Обработчики команд для жильцов.
"""

import logging

from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart, Command

from app.config import settings
from app.db import SessionLocal
from app.models import User, Setting

logger = logging.getLogger(__name__)
router = Router()


def get_or_create_user(telegram_id: int) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            role = "resident"
            if telegram_id in settings.ADMIN_IDS:
                role = "admin"
            elif telegram_id in settings.WORKER_IDS:
                role = "worker"
            user = User(telegram_id=telegram_id, role=role)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = get_or_create_user(message.from_user.id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=settings.MINI_APP_URL))]
        ]
    )
    if user.role == "resident":
        text = (
            f"Здравствуйте, {message.from_user.full_name}!\n\n"
            "Вы можете зарегистрироваться и подать заявку на мойку окон или балкона через Mini App.\n"
            "Нажмите кнопку ниже, чтобы открыть приложение."
        )
    elif user.role == "worker":
        text = "Вы работник. Используйте команды для управления заявками."
    elif user.role == "admin":
        text = "Вы администратор. Вам доступны все функции."
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "Доступные команды:\n"
        "/start — главное меню\n"
        "/pay — получить реквизиты для оплаты\n"
        "/help — эта справка\n\n"
        "Для подачи заявки используйте кнопку «Открыть приложение»."
    )
    await message.answer(text)


@router.message(Command("pay"))
async def cmd_pay(message: Message):
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.key == "payment_details").first()
        if setting and setting.value:
            await message.answer(f"Реквизиты для оплаты:\n\n{setting.value}")
        else:
            await message.answer("Реквизиты пока не заданы администратором.")
    finally:
        db.close()

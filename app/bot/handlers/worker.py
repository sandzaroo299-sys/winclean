"""
Обработчики команд для работников.
"""

import logging
from datetime import datetime

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from app.db import SessionLocal
from app.models import User, Request, WorkLog, Notification, Setting

logger = logging.getLogger(__name__)
router = Router()


def get_db_user(telegram_id: int) -> User | None:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.telegram_id == telegram_id).first()
    finally:
        db.close()


def is_worker(telegram_id: int) -> bool:
    user = get_db_user(telegram_id)
    return user is not None and user.role == "worker"


@router.message(Command("requests"))
async def cmd_list_requests(message: Message):
    if not is_worker(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    db = SessionLocal()
    try:
        requests = db.query(Request).filter(Request.status.in_(["new", "urgent"])).order_by(Request.created_at).all()
        if not requests:
            await message.answer("Нет активных заявок.")
            return
        text = "Активные заявки:\n\n"
        for req in requests:
            text += (
                f"#{req.id} — {req.service_type}, "
                f"кв. {req.apartment.number} ({req.apartment.building.address}), "
                f"статус: {req.status}\n"
            )
        await message.answer(text)
    finally:
        db.close()


@router.message(Command("take"))
async def cmd_take_request(message: Message):
    if not is_worker(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /take <id>")
        return
    try:
        request_id = int(args[1])
    except ValueError:
        await message.answer("Неверный ID.")
        return

    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            await message.answer("Заявка не найдена.")
            return
        if req.status not in ("new", "urgent"):
            await message.answer(f"Нельзя взять заявку в статусе {req.status}.")
            return
        old_status = req.status
        req.status = "in_progress"
        req.updated_at = datetime.utcnow()
        worker = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        log = WorkLog(
            request_id=req.id,
            user_id=worker.id if worker else None,
            action="take",
            details=f"Статус изменён с {old_status} на in_progress",
        )
        db.add(log)
        if req.user_id:
            notif = Notification(
                user_id=req.user_id,
                request_id=req.id,
                type="status_changed",
                message_text=f"Ваша заявка #{req.id} взята в работу.",
                priority="normal",
            )
            db.add(notif)
        db.commit()
        await message.answer(f"Заявка #{req.id} взята в работу.")
    finally:
        db.close()


@router.message(Command("complete"))
async def cmd_complete_request(message: Message):
    if not is_worker(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /complete <id>")
        return
    try:
        request_id = int(args[1])
    except ValueError:
        await message.answer("Неверный ID.")
        return

    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            await message.answer("Заявка не найдена.")
            return
        if req.status != "in_progress":
            await message.answer(f"Нельзя завершить заявку в статусе {req.status}.")
            return
        req.status = "completed"
        req.updated_at = datetime.utcnow()
        worker = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        log = WorkLog(
            request_id=req.id,
            user_id=worker.id if worker else None,
            action="complete",
            details="Заявка завершена",
        )
        db.add(log)
        if req.user_id:
            payment_setting = db.query(Setting).filter(Setting.key == "payment_details").first()
            extra = ""
            if payment_setting and payment_setting.value:
                extra = f"\n\nРеквизиты для оплаты:\n{payment_setting.value}"
            notif = Notification(
                user_id=req.user_id,
                request_id=req.id,
                type="status_changed",
                message_text=f"Ваша заявка #{req.id} выполнена!{extra}",
                priority="high",
            )
            db.add(notif)
        db.commit()
        await message.answer(f"Заявка #{req.id} завершена.")
    finally:
        db.close()


@router.message(Command("reject"))
async def cmd_reject_request(message: Message):
    if not is_worker(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("Использование: /reject <id> [комментарий]")
        return
    try:
        request_id = int(args[1])
    except ValueError:
        await message.answer("Неверный ID.")
        return
    comment = args[2] if len(args) > 2 else ""
    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).first()
        if not req:
            await message.answer("Заявка не найдена.")
            return
        if req.status != "urgent":
            await message.answer("Отклонять можно только претензии (urgent).")
            return
        req.status = "rejected"
        req.comment = (req.comment + "\n" if req.comment else "") + f"Отклонено: {comment}"
        req.updated_at = datetime.utcnow()
        worker = db.query(User).filter(User.telegram_id == message.from_user.id).first()
        log = WorkLog(
            request_id=req.id,
            user_id=worker.id if worker else None,
            action="reject",
            details=f"Претензия отклонена: {comment}",
        )
        db.add(log)
        if req.user_id:
            notif = Notification(
                user_id=req.user_id,
                request_id=req.id,
                type="status_changed",
                message_text=f"Ваша претензия #{req.id} отклонена. Причина: {comment}",
                priority="high",
            )
            db.add(notif)
        db.commit()
        await message.answer(f"Претензия #{req.id} отклонена.")
    finally:
        db.close()

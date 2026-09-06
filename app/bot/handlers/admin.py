"""
Обработчики команд для администратора.
"""

import csv
import io
import logging

from aiogram import Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command

from app.db import SessionLocal
from app.models import User, Building, Apartment, Request, Setting, Notification

logger = logging.getLogger(__name__)
router = Router()


def get_db_user(telegram_id: int) -> User | None:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.telegram_id == telegram_id).first()
    finally:
        db.close()


def is_admin(telegram_id: int) -> bool:
    user = get_db_user(telegram_id)
    return user is not None and user.role == "admin"


@router.message(Command("add_building"))
async def cmd_add_building(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    args = message.text.split()
    if len(args) < 4:
        await message.answer("Использование: /add_building <адрес> <этажей> <подъездов> [широта] [долгота] [угол_фасада]")
        return
    address = args[1]
    try:
        floors = int(args[2])
        entrances = int(args[3])
    except ValueError:
        await message.answer("Этажи и подъезды должны быть числами.")
        return
    lat = float(args[4]) if len(args) > 4 else None
    lon = float(args[5]) if len(args) > 5 else None
    angle = float(args[6]) if len(args) > 6 else None

    db = SessionLocal()
    try:
        building = Building(
            address=address,
            floors_count=floors,
            entrances_count=entrances,
            latitude=lat,
            longitude=lon,
            facade_angle=angle,
        )
        db.add(building)
        db.flush()
        for entrance in range(1, entrances + 1):
            for floor in range(1, floors + 1):
                for apt_num in range(1, 5):
                    number = f"{entrance}{floor}{apt_num}"
                    apartment = Apartment(
                        building_id=building.id,
                        entrance=entrance,
                        floor=floor,
                        number=number,
                        window_side="unknown",
                    )
                    db.add(apartment)
        db.commit()
        await message.answer(f"Дом добавлен: {address}, этажей: {floors}, подъездов: {entrances}.")
    except Exception as e:
        db.rollback()
        await message.answer(f"Ошибка: {e}")
    finally:
        db.close()


@router.message(Command("list_buildings"))
async def cmd_list_buildings(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    db = SessionLocal()
    try:
        buildings = db.query(Building).all()
        if not buildings:
            await message.answer("Нет домов.")
            return
        text = "Список домов:\n\n"
        for b in buildings:
            text += f"ID {b.id}: {b.address}, этажей: {b.floors_count}, подъездов: {b.entrances_count}\n"
        await message.answer(text)
    finally:
        db.close()


@router.message(Command("set_payment"))
async def cmd_set_payment(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        await message.answer("Использование: /set_payment <реквизиты>")
        return
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.key == "payment_details").first()
        if setting:
            setting.value = text[1]
        else:
            setting = Setting(key="payment_details", value=text[1])
            db.add(setting)
        db.commit()
        await message.answer("Реквизиты обновлены.")
    finally:
        db.close()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    text = message.text.split(maxsplit=1)
    if len(text) < 2:
        await message.answer("Использование: /broadcast <текст>")
        return
    db = SessionLocal()
    try:
        residents = db.query(User).filter(User.role == "resident").all()
        for user in residents:
            notif = Notification(
                user_id=user.id,
                type="broadcast",
                message_text=text[1],
                priority="normal",
            )
            db.add(notif)
        db.commit()
        await message.answer(f"Рассылка создана для {len(residents)} жильцов.")
    finally:
        db.close()


@router.message(Command("export_requests"))
async def cmd_export_requests(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("У вас нет прав.")
        return
    db = SessionLocal()
    try:
        requests = db.query(Request).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Address", "Apartment", "Service", "Status", "Comment", "Created At", "User"])
        for req in requests:
            writer.writerow([
                req.id,
                req.apartment.building.address if req.apartment else "",
                req.apartment.number if req.apartment else "",
                req.service_type,
                req.status,
                req.comment or "",
                req.created_at.strftime("%Y-%m-%d %H:%M"),
                req.user.full_name or req.user.telegram_id,
            ])
        output.seek(0)
        file = BufferedInputFile(output.getvalue().encode("utf-8"), filename="requests.csv")
        await message.answer_document(file)
    finally:
        db.close()

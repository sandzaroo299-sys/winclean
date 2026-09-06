# app/db.py
"""
Подключение к базе данных и инициализация.

Создаёт движок SQLAlchemy, сессию и базовый класс для моделей.
При первом запуске (если база пуста) загружает дома и квартиры из data/houses.json.
"""

import json
import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Для SQLite включаем check_same_thread=False, чтобы избежать ошибок в многопоточном FastAPI
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""


def get_db():
    """
    Зависимость FastAPI: возвращает сессию БД и закрывает её после запроса.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def load_houses_from_json(db: Session, filepath: str = "data/houses.json") -> None:
    """
    Загружает дома и квартиры из JSON-файла, если файл существует и в базе ещё нет домов.
    """
    if not os.path.exists(filepath):
        print(f"Файл {filepath} не найден — пропускаем загрузку.")
        return

    from app.models import Apartment, Building  # импортируем здесь, чтобы избежать циклического импорта

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    buildings_data = data.get("buildings", [])
    for b_data in buildings_data:
        building = Building(
            address=b_data["address"],
            entrances_count=b_data.get("entrances_count", 1),
            floors_count=b_data.get("floors_count", 1),
            latitude=b_data.get("latitude"),
            longitude=b_data.get("longitude"),
            facade_angle=b_data.get("facade_angle"),
        )
        db.add(building)
        db.flush()  # получаем id здания

        for apt_data in b_data.get("apartments", []):
            apartment = Apartment(
                building_id=building.id,
                entrance=apt_data.get("entrance", 1),
                floor=apt_data.get("floor", 1),
                number=str(apt_data.get("number", "")),
                window_side=apt_data.get("window_side", "unknown"),
            )
            db.add(apartment)

    db.commit()
    print(f"Загружено {len(buildings_data)} домов из {filepath}")


def init_db() -> None:
    """
    Создаёт все таблицы и при необходимости загружает начальные данные.
    Вызывается при старте приложения.
    """
    # Импорт моделей обязателен, чтобы они были зарегистрированы в Base.metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Если в базе нет ни одного дома — пытаемся загрузить из JSON
    db = SessionLocal()
    try:
        from app.models import Building

        if db.query(Building).count() == 0:
            load_houses_from_json(db)
    finally:
        db.close()

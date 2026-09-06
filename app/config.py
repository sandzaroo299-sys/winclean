# app/config.py
"""
Конфигурация приложения.

Загружает переменные из .env файла, валидирует обязательные поля,
предоставляет объект настроек для использования во всех модулях.
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from dotenv import load_dotenv

# Загружаем .env файл, если он есть
load_dotenv()


@dataclass
class Settings:
    """Основные настройки проекта."""

    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS: List[int]
    WORKER_IDS: List[int]

    # Web / Mini App
    MINI_APP_URL: str

    # База данных
    DATABASE_URL: str

    # Погода
    WEATHER_PROVIDER: str = "openmeteo"  # openmeteo или yandex
    YANDEX_WEATHER_API_KEY: Optional[str] = None

    # Пороги погодных условий для предупреждений
    WIND_SPEED_THRESHOLD: float = 12.0   # м/с
    RAIN_PROBABILITY_THRESHOLD: int = 50  # %
    TEMPERATURE_THRESHOLD: float = 30.0  # °C

    # Интервал проверки погоды (в секундах, по умолчанию 1 час)
    WEATHER_CHECK_INTERVAL: int = 3600

    # Максимальное количество фотографий для претензии
    MAX_COMPLAINT_PHOTOS: int = 3


def _parse_ids(raw: str) -> List[int]:
    """Преобразует строку '123,456' в список целых чисел."""
    if not raw:
        return []
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise ValueError(f"Некорректный формат списка ID: {raw}")


def get_settings() -> Settings:
    """
    Возвращает объект настроек, заполненный из переменных окружения.
    При отсутствии обязательных переменных выбрасывает исключение.
    """
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise EnvironmentError("BOT_TOKEN не задан в .env файле")

    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    worker_ids_raw = os.getenv("WORKER_IDS", "")

    mini_app_url = os.getenv("MINI_APP_URL", "")
    if not mini_app_url:
        raise EnvironmentError("MINI_APP_URL не задан в .env файле")

    database_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    weather_provider = os.getenv("WEATHER_PROVIDER", "openmeteo").lower()
    if weather_provider not in ("openmeteo", "yandex"):
        weather_provider = "openmeteo"

    yandex_key = os.getenv("YANDEX_WEATHER_API_KEY")

    # Если выбран yandex, но ключ не указан — переключаемся на openmeteo
    if weather_provider == "yandex" and not yandex_key:
        weather_provider = "openmeteo"

    return Settings(
        BOT_TOKEN=bot_token,
        ADMIN_IDS=_parse_ids(admin_ids_raw),
        WORKER_IDS=_parse_ids(worker_ids_raw),
        MINI_APP_URL=mini_app_url.rstrip("/"),
        DATABASE_URL=database_url,
        WEATHER_PROVIDER=weather_provider,
        YANDEX_WEATHER_API_KEY=yandex_key,
    )


# Синглтон настроек
settings = get_settings()

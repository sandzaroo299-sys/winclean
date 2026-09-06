# app/services/weather.py
"""
Сервис погоды.

Использует бесплатный провайдер Open-Meteo (по умолчанию) или Яндекс.Погоду (если задан ключ).
Возвращает предупреждения для зданий, если погодные условия превышают допустимые пороги.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

import aiohttp

from app.config import settings
from app.models import Building


async def fetch_openmeteo_weather(lat: float, lon: float) -> dict:
    """
    Получает текущую погоду и прогноз на 24 часа от Open-Meteo.
    Возвращает словарь с нужными полями.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,wind_speed_10m,precipitation_probability",
        "hourly": "temperature_2m,wind_speed_10m,precipitation_probability",
        "forecast_days": 2,
        "timezone": "auto",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
    return data


async def fetch_yandex_weather(lat: float, lon: float) -> dict:
    """
    Получает погоду от Яндекс.Погоды (требует API-ключ).
    Возвращает словарь с нужными полями.
    """
    if not settings.YANDEX_WEATHER_API_KEY:
        raise ValueError("YANDEX_WEATHER_API_KEY не задан")
    url = "https://api.weather.yandex.ru/v2/forecast"
    headers = {"X-Yandex-API-Key": settings.YANDEX_WEATHER_API_KEY}
    params = {"lat": lat, "lon": lon, "limit": 2, "hours": True}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()
    return data


def _extract_openmeteo(data: dict, hours_offset: int = 0) -> dict:
    """Извлекает нужные параметры из ответа Open-Meteo для заданного смещения часов."""
    current = data.get("current", {})
    hourly = data.get("hourly", {})
    if hours_offset == 0:
        return {
            "temperature": current.get("temperature_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "precipitation_probability": current.get("precipitation_probability"),
        }
    # Берём значение из hourly с индексом hours_offset
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    winds = hourly.get("wind_speed_10m", [])
    precips = hourly.get("precipitation_probability", [])
    if hours_offset < len(temps):
        return {
            "temperature": temps[hours_offset],
            "wind_speed": winds[hours_offset],
            "precipitation_probability": precips[hours_offset],
        }
    return {}


def _extract_yandex(data: dict, hours_offset: int = 0) -> dict:
    """Извлекает нужные параметры из ответа Яндекс.Погоды."""
    fact = data.get("fact", {})
    forecasts = data.get("forecasts", [])
    if hours_offset == 0:
        return {
            "temperature": fact.get("temp"),
            "wind_speed": fact.get("wind_speed"),
            "precipitation_probability": fact.get("prec_prob", 0),
        }
    # Прогноз по часам
    for forecast in forecasts:
        hours = forecast.get("hours", [])
        if hours_offset - 1 < len(hours):
            hour_data = hours[hours_offset - 1]
            return {
                "temperature": hour_data.get("temp"),
                "wind_speed": hour_data.get("wind_speed"),
                "precipitation_probability": hour_data.get("prec_prob", 0),
            }
    return {}


async def _get_weather_for_coords(lat: float, lon: float, hours_offset: int = 0) -> dict:
    """
    Получает погоду для координат с учётом смещения времени (0 = сейчас, 12 = через 12 часов и т.д.).
    Возвращает словарь с temperature, wind_speed, precipitation_probability.
    """
    if not lat or not lon:
        return {}
    try:
        if settings.WEATHER_PROVIDER == "yandex":
            data = await fetch_yandex_weather(lat, lon)
            return _extract_yandex(data, hours_offset)
        else:
            data = await fetch_openmeteo_weather(lat, lon)
            return _extract_openmeteo(data, hours_offset)
    except Exception as e:
        print(f"Ошибка получения погоды: {e}")
        return {}


def check_thresholds(weather: dict) -> Optional[str]:
    """
    Проверяет, превышают ли значения погоды допустимые пороги.
    Возвращает текст предупреждения или None.
    """
    warnings = []
    wind = weather.get("wind_speed")
    temp = weather.get("temperature")
    precip = weather.get("precipitation_probability")

    if wind is not None and wind > settings.WIND_SPEED_THRESHOLD:
        warnings.append(f"Ветер {wind:.1f} м/с (порог {settings.WIND_SPEED_THRESHOLD} м/с)")
    if temp is not None and temp > settings.TEMPERATURE_THRESHOLD:
        warnings.append(f"Температура {temp:.1f}°C (порог {settings.TEMPERATURE_THRESHOLD}°C)")
    if precip is not None and precip > settings.RAIN_PROBABILITY_THRESHOLD:
        warnings.append(f"Вероятность дождя {precip}% (порог {settings.RAIN_PROBABILITY_THRESHOLD}%)")

    if warnings:
        return "⚠️ Неблагоприятные условия: " + ", ".join(warnings) + ". Рекомендуется перенести работы."
    return None


def get_weather_alert_for_building(building: Building) -> dict:
    """
    Синхронная обёртка для API: возвращает предупреждение о погоде для здания.
    Вызывается из endpoint'а.
    """
    if not building.latitude or not building.longitude:
        return {
            "building_id": building.id,
            "wind_speed": 0,
            "rain_probability": 0,
            "temperature": 0,
            "message": "Нет координат для здания",
            "recommended_action": "Добавьте координаты",
        }
    # Так как endpoint синхронный, а запросы асинхронные, используем asyncio.run
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    weather = loop.run_until_complete(_get_weather_for_coords(building.latitude, building.longitude, 0))
    loop.close()

    message = check_thresholds(weather)
    if message:
        return {
            "building_id": building.id,
            "wind_speed": weather.get("wind_speed", 0),
            "rain_probability": weather.get("precipitation_probability", 0),
            "temperature": weather.get("temperature", 0),
            "message": message,
            "recommended_action": "Перенесите работы на другое время",
        }
    return {
        "building_id": building.id,
        "wind_speed": weather.get("wind_speed", 0),
        "rain_probability": weather.get("precipitation_probability", 0),
        "temperature": weather.get("temperature", 0),
        "message": "Погода в норме",
        "recommended_action": "Можно работать",
    }


async def check_weather_and_notify(db_session_maker, buildings: List[Building]) -> None:
    """
    Периодическая проверка погоды для всех зданий.
    Если обнаружены превышения порогов, создаёт уведомления для админов и работников.
    """
    from app.models import Notification, User
    from app.db import SessionLocal

    for building in buildings:
        if not building.latitude or not building.longitude:
            continue
        # Проверяем текущую погоду и прогноз на 1, 12, 24 часа вперёд
        for hours_offset in [0, 1, 12, 24]:
            weather = await _get_weather_for_coords(building.latitude, building.longitude, hours_offset)
            message = check_thresholds(weather)
            if message:
                # Получаем работников и админов
                recipients = db_session_maker.query(User).filter(User.role.in_(["worker", "admin"])).all()
                for user in recipients:
                    notification = Notification(
                        user_id=user.id,
                        type="weather_warning",
                        message_text=f"🏠 {building.address}: {message} (через {hours_offset} ч)",
                        priority="high" if hours_offset <= 1 else "normal",
                    )
                    db_session_maker.add(notification)
        db_session_maker.commit()

# app/services/solar.py
"""
Сервис солнечного планирования.

Рассчитывает положение солнца для здания и определяет,
какая сторона фасада освещена в данный момент.
Также формирует план работы на день: утро/день/вечер с рекомендациями.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple

from astral import LocationInfo
from astral.sun import sun


from app.models import Building


def _get_location(building: Building) -> Optional[LocationInfo]:
    """Создаёт объект LocationInfo из координат здания."""
    if not building.latitude or not building.longitude:
        return None
    return LocationInfo(
        name="building",
        region="",
        timezone="UTC",  # время в UTC, потом переведём локально
        latitude=building.latitude,
        longitude=building.longitude,
    )


def _get_sun_times(building: Building, date: datetime) -> Optional[dict]:
    """Возвращает времена восхода/заката и полдня для здания."""
    location = _get_location(building)
    if not location:
        return None
    # astral ожидает date без времени
    day = date.date()
    try:
        s = sun(location.observer, date=day)
        return s  # dict с ключами sunrise, sunset, noon и др.
    except Exception:
        return None


def _calculate_solar_position(building: Building, date: datetime) -> Optional[Tuple[float, float]]:
    """
    Рассчитывает азимут и высоту солнца для здания в заданный момент времени.
    Возвращает (azimuth, elevation) в градусах.
    """
    location = _get_location(building)
    if not location:
        return None
    # Переводим время в UTC, так как astral работает с UTC?
    # Лучше использовать библиотеку suncalc, но astral тоже можно: используем observer и date с tz.
    # Для простоты будем считать, что координаты и время передаются в UTC.
    # Мы можем использовать astral.sun.elevation, но он требует observer и date.
    # В документации astral есть метод sun.elevation(observer, date) - вернёт высоту.
    # Для азимута есть sun.azimuth(observer, date).
    from astral.sun import elevation, azimuth
    try:
        elev = elevation(location.observer, date)
        azim = azimuth(location.observer, date)
        return azim, elev
    except Exception:
        return None


def determine_illuminated_side(azimuth: float, building: Building) -> str:
    """
    Определяет, какая сторона здания освещена на основе азимута солнца и угла фасада.
    Упрощение: предполагаем, что фасад ориентирован по facade_angle (0 = север, 90 = восток).
    Стороны: north (0°), east (90°), south (180°), west (270°).
    Если сторона квартир задана как street/yard, то это отдельная логика, но для MVP вернём стороны света.
    """
    # Нормализуем азимут в диапазон [0, 360)
    azimuth = azimuth % 360

    # Определяем сектор: 45° вокруг каждого направления
    if 315 <= azimuth or azimuth < 45:
        return "north"
    elif 45 <= azimuth < 135:
        return "east"
    elif 135 <= azimuth < 225:
        return "south"
    elif 225 <= azimuth < 315:
        return "west"
    return "unknown"


def get_solar_position_for_building(building: Building) -> dict:
    """
    Возвращает текущую информацию о солнце для здания: времена восхода/заката,
    текущие азимут и высоту, освещённую сторону.
    """
    now = datetime.utcnow()  # UTC, так как здания могут быть в разных часовых поясах
    # Но лучше использовать local time? Для простоты оставим UTC, но учтём, что координаты в России -> нужно смещение.
    # Мы можем использовать timezone из настроек или автоматически определять по координатам, но это сложно.
    # Пока возвращаем как есть, пользователь может скорректировать.
    sun_times = _get_sun_times(building, now)
    sunrise = sun_times["sunrise"] if sun_times else None
    sunset = sun_times["sunset"] if sun_times else None

    position = _calculate_solar_position(building, now)
    azimuth, elevation = position if position else (0, 0)

    illuminated_side = determine_illuminated_side(azimuth, building)

    return {
        "building_id": building.id,
        "date": now,
        "sunrise": sunrise,
        "sunset": sunset,
        "current_azimuth": azimuth,
        "current_elevation": elevation,
        "illuminated_side": illuminated_side,
    }


def generate_daily_plan(building: Building) -> list:
    """
    Генерирует план работы на день: утро, день, вечер.
    Для каждого периода определяет освещённую сторону и рекомендацию.
    """
    # Предположим, что рабочие часы с 8:00 до 20:00 местного времени (UTC+3 для Москвы)
    # Для простоты будем использовать UTC, но можно добавить смещение.
    # Мы не знаем часовой пояс здания, поэтому возьмём приблизительно, используя долготу.
    # Для MVP: просто разобьём день на три части: 8-12, 12-16, 16-20 по UTC.
    plan = []
    now = datetime.utcnow().replace(hour=8, minute=0, second=0, microsecond=0)
    periods = [
        ("morning", now, now + timedelta(hours=4)),
        ("afternoon", now + timedelta(hours=4), now + timedelta(hours=8)),
        ("evening", now + timedelta(hours=8), now + timedelta(hours=12)),
    ]
    for period_name, start, end in periods:
        # Берём середину периода для расчёта
        mid_time = start + (end - start) / 2
        position = _calculate_solar_position(building, mid_time)
        if position:
            azimuth, elevation = position
            side = determine_illuminated_side(azimuth, building)
            plan.append({
                "period": period_name,
                "start": start,
                "end": end,
                "illuminated_side": side,
                "recommendation": f"Работать на теневой стороне (противоположной {side})",
            })
        else:
            plan.append({
                "period": period_name,
                "start": start,
                "end": end,
                "illuminated_side": "unknown",
                "recommendation": "Нет данных",
            })
    return plan

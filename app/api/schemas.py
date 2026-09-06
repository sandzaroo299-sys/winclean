# app/api/schemas.py
"""
Pydantic-схемы для API.

Используются для валидации входящих данных и сериализации ответов.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------- Базовые схемы ----------
class UserOut(BaseModel):
    """Информация о пользователе для ответа."""
    id: int
    telegram_id: int
    full_name: Optional[str] = None
    role: str
    apartment_id: Optional[int] = None

    class Config:
        from_attributes = True


class BuildingOut(BaseModel):
    """Краткая информация о доме."""
    id: int
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    facade_angle: Optional[float] = None
    entrances_count: int
    floors_count: int

    class Config:
        from_attributes = True


class ApartmentOut(BaseModel):
    """Краткая информация о квартире."""
    id: int
    building_id: int
    entrance: int
    floor: int
    number: str
    window_side: str

    class Config:
        from_attributes = True


# ---------- Схемы регистрации ----------
class RegisterRequest(BaseModel):
    """Данные для регистрации жильца."""
    building_id: int
    apartment_number: str
    full_name: Optional[str] = None
    window_side: Optional[str] = "unknown"


class RegisterResponse(BaseModel):
    """Ответ после регистрации."""
    user: UserOut
    apartment: ApartmentOut


# ---------- Схемы заявок ----------
class RequestCreate(BaseModel):
    """Создание новой заявки."""
    service_type: str = Field(..., description="windows, balcony, both")
    comment: Optional[str] = None
    planned_date: Optional[datetime] = None


class RequestOut(BaseModel):
    """Ответ с данными заявки."""
    id: int
    apartment_id: int
    user_id: int
    service_type: str
    status: str
    comment: Optional[str] = None
    planned_date: Optional[datetime] = None
    parent_request_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    apartment: Optional[ApartmentOut] = None
    user: Optional[UserOut] = None

    class Config:
        from_attributes = True


class RequestStatusUpdate(BaseModel):
    """Изменение статуса заявки."""
    status: str = Field(..., description="new, in_progress, completed, paid, cancelled, urgent, completed_second, rejected")
    comment: Optional[str] = None


# ---------- Претензии ----------
class ComplaintCreate(BaseModel):
    """Создание претензии к завершённой заявке."""
    request_id: int  # исходная заявка
    comment: str = Field(..., min_length=1, description="Описание проблемы")
    photos: Optional[List[str]] = None  # base64 или пути, но в MVP пусть будет список URL?


class ComplaintOut(BaseModel):
    """Ответ с данными претензии."""
    id: int
    parent_request_id: int
    comment: str
    status: str
    created_at: datetime


# ---------- Уведомления ----------
class NotificationOut(BaseModel):
    """Уведомление для ответа."""
    id: int
    user_id: Optional[int]
    request_id: Optional[int]
    type: str
    message_text: str
    priority: str
    sent_at: Optional[datetime]
    is_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Настройки ----------
class SettingOut(BaseModel):
    """Настройка."""
    key: str
    value: str

    class Config:
        from_attributes = True


class SettingUpdate(BaseModel):
    """Обновление настройки."""
    key: str
    value: str


# ---------- Погода и солнце ----------
class SolarPositionOut(BaseModel):
    """Информация о положении солнца для дома."""
    building_id: int
    date: datetime
    sunrise: datetime
    sunset: datetime
    current_azimuth: float
    current_elevation: float
    illuminated_side: str  # north, south, east, west, unknown


class WeatherAlertOut(BaseModel):
    """Предупреждение о неблагоприятной погоде."""
    building_id: int
    wind_speed: float
    rain_probability: float
    temperature: float
    message: str
    recommended_action: str


# ---------- Экспорт ----------
class ExportRequest(BaseModel):
    """Запрос на экспорт заявок в CSV (возвращает строку CSV)."""
    format: str = "csv"

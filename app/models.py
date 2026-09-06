# app/models.py
"""
Модели SQLAlchemy для всех сущностей проекта.

Используются как в FastAPI (через сессии), так и в aiogram (через те же сессии).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    """Пользователь бота / Mini App."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="resident")  # resident | worker | admin
    apartment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("apartments.id"), nullable=True)

    # Связи
    apartment: Mapped[Optional["Apartment"]] = relationship(back_populates="residents")
    requests: Mapped[list["Request"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, role={self.role})>"


class Building(Base):
    """Жилой дом."""

    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    address: Mapped[str] = mapped_column(String(255), index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    facade_angle: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # угол фасада в градусах (0-360)
    entrances_count: Mapped[int] = mapped_column(Integer, default=1)
    floors_count: Mapped[int] = mapped_column(Integer, default=1)

    # Связи
    apartments: Mapped[list["Apartment"]] = relationship(back_populates="building", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Building(id={self.id}, address={self.address})>"


class Apartment(Base):
    """Квартира в доме."""

    __tablename__ = "apartments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"), index=True)
    entrance: Mapped[int] = mapped_column(Integer, default=1)
    floor: Mapped[int] = mapped_column(Integer, default=1)
    number: Mapped[str] = mapped_column(String(20))
    window_side: Mapped[str] = mapped_column(String(20), default="unknown")  # street, yard, north, south, east, west, unknown

    # Связи
    building: Mapped["Building"] = relationship(back_populates="apartments")
    residents: Mapped[list["User"]] = relationship(back_populates="apartment")
    requests: Mapped[list["Request"]] = relationship(back_populates="apartment")

    def __repr__(self) -> str:
        return f"<Apartment(id={self.id}, building={self.building_id}, number={self.number})>"


class Request(Base):
    """Заявка (на услугу или претензия)."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    apartment_id: Mapped[int] = mapped_column(ForeignKey("apartments.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    service_type: Mapped[str] = mapped_column(String(30))  # windows, balcony, both, complaint
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)  # new, in_progress, completed, paid, cancelled, urgent, completed_second, rejected
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    planned_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    parent_request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("requests.id"), nullable=True)  # для претензий
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    apartment: Mapped["Apartment"] = relationship(back_populates="requests")
    user: Mapped["User"] = relationship(back_populates="requests")
    parent_request: Mapped[Optional["Request"]] = relationship(remote_side=[id], backref="child_requests")
    work_logs: Mapped[list["WorkLog"]] = relationship(back_populates="request", cascade="all, delete-orphan")
    photos: Mapped[list["ComplaintPhoto"]] = relationship(back_populates="request", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="request")

    def __repr__(self) -> str:
        return f"<Request(id={self.id}, type={self.service_type}, status={self.status})>"


class WorkLog(Base):
    """Журнал действий по заявке."""

    __tablename__ = "work_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))  # например "status_changed", "comment_added"
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Связи
    request: Mapped["Request"] = relationship(back_populates="work_logs")
    user: Mapped["User"] = relationship()  # простая связь без обратного поля

    def __repr__(self) -> str:
        return f"<WorkLog(id={self.id}, request={self.request_id}, action={self.action})>"


class ComplaintPhoto(Base):
    """Фотография к претензии."""

    __tablename__ = "complaint_photos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))  # путь к файлу на сервере

    # Связи
    request: Mapped["Request"] = relationship(back_populates="photos")

    def __repr__(self) -> str:
        return f"<ComplaintPhoto(id={self.id}, request={self.request_id})>"


class Notification(Base):
    """Уведомление пользователю."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)  # null для массовых
    request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("requests.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(50))  # new_request, status_changed, weather_warning, etc.
    message_text: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # normal, high, urgent
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Связи
    user: Mapped[Optional["User"]] = relationship()
    request: Mapped[Optional["Request"]] = relationship(back_populates="notifications")

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, type={self.type}, is_sent={self.is_sent})>"


class Setting(Base):
    """Настройки приложения (ключа-значение)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<Setting(key={self.key})>"

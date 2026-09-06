# app/api/routes.py
"""
API-эндпоинты для Mini App и внешних запросов.

Все эндпоинты имеют префикс /api и идентифицируют пользователя по telegram_id,
передаваемому как query-параметр (или в заголовке X-Telegram-Id).
"""

import csv
import io
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    Apartment,
    Building,
    ComplaintPhoto,
    Notification,
    Request,
    Setting,
    User,
    WorkLog,
)
from app.config import settings
from app.api.schemas import (
    ApartmentOut,
    BuildingOut,
    ComplaintCreate,
    ComplaintOut,
    NotificationOut,
    RegisterRequest,
    RegisterResponse,
    RequestCreate,
    RequestOut,
    RequestStatusUpdate,
    SettingOut,
    SettingUpdate,
    SolarPositionOut,
    UserOut,
    WeatherAlertOut,
)
from app.services.weather import get_weather_alert_for_building
from app.services.solar import get_solar_position_for_building
from app.services.qr import generate_qr_code

router = APIRouter(prefix="/api")


# ---------- Вспомогательные функции ----------
def get_user_by_telegram(db: Session, telegram_id: int) -> Optional[User]:
    """Возвращает пользователя по telegram_id или None."""
    return db.query(User).filter(User.telegram_id == telegram_id).first()


def get_user_or_404(db: Session, telegram_id: int) -> User:
    """Возвращает пользователя или выбрасывает 404."""
    user = get_user_by_telegram(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


def check_role(user: User, allowed_roles: List[str]) -> None:
    """Проверяет, что роль пользователя входит в allowed_roles, иначе 403."""
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Недостаточно прав")


# ---------- Регистрация и информация ----------
@router.post("/register", response_model=RegisterResponse)
def register(
    data: RegisterRequest,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(get_db),
):
    """
    Регистрация жильца: привязка к квартире.
    Если пользователь уже существует и является worker/admin — запрещено.
    """
    # Проверяем, существует ли пользователь
    user = get_user_by_telegram(db, telegram_id)
    if user:
        if user.role in ("worker", "admin"):
            raise HTTPException(status_code=403, detail="Сотрудники не могут регистрироваться как жильцы")
        # Обновляем данные, если уже есть
    else:
        user = User(
            telegram_id=telegram_id,
            full_name=data.full_name,
            role="resident",
        )
        db.add(user)
        db.flush()

    # Ищем квартиру по building_id и номеру
    apartment = (
        db.query(Apartment)
        .filter(Apartment.building_id == data.building_id, Apartment.number == data.apartment_number)
        .first()
    )
    if not apartment:
        raise HTTPException(status_code=404, detail="Квартира не найдена")

    # Привязываем
    user.apartment_id = apartment.id
    if data.full_name:
        user.full_name = data.full_name
    if data.window_side and data.window_side != "unknown":
        apartment.window_side = data.window_side
        # Экстраполяция по вертикали: обновляем все квартиры в том же подъезде на других этажах с тем же номером квартиры
        same_number_apartments = (
            db.query(Apartment)
            .filter(
                Apartment.building_id == apartment.building_id,
                Apartment.entrance == apartment.entrance,
                Apartment.number == apartment.number,
            )
            .all()
        )
        for apt in same_number_apartments:
            apt.window_side = data.window_side

    db.commit()
    db.refresh(user)
    db.refresh(apartment)

    return RegisterResponse(
        user=UserOut.from_orm(user),
        apartment=ApartmentOut.from_orm(apartment),
    )


@router.get("/buildings", response_model=List[BuildingOut])
def get_buildings(db: Session = Depends(get_db)):
    """Возвращает список всех домов."""
    buildings = db.query(Building).all()
    return [BuildingOut.from_orm(b) for b in buildings]


@router.get("/apartments/by_number", response_model=ApartmentOut)
def get_apartment_by_number(
    building_id: int,
    apartment_number: str,
    db: Session = Depends(get_db),
):
    """Возвращает квартиру по номеру и ID дома."""
    apartment = (
        db.query(Apartment)
        .filter(Apartment.building_id == building_id, Apartment.number == apartment_number)
        .first()
    )
    if not apartment:
        raise HTTPException(status_code=404, detail="Квартира не найдена")
    return ApartmentOut.from_orm(apartment)


@router.get("/me", response_model=UserOut)
def get_me(
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """Возвращает информацию о текущем пользователе."""
    user = get_user_or_404(db, telegram_id)
    return UserOut.from_orm(user)


# ---------- Заявки ----------
@router.post("/requests", response_model=RequestOut)
def create_request(
    data: RequestCreate,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Создание новой заявки жильцом.
    Требуется, чтобы пользователь был resident и был привязан к квартире.
    """
    user = get_user_or_404(db, telegram_id)
    if user.role != "resident":
        raise HTTPException(status_code=403, detail="Только жильцы могут создавать заявки")
    if not user.apartment_id:
        raise HTTPException(status_code=400, detail="Вы не привязаны к квартире. Пройдите регистрацию.")

    if data.service_type not in ("windows", "balcony", "both"):
        raise HTTPException(status_code=400, detail="Неверный тип услуги")

    request = Request(
        apartment_id=user.apartment_id,
        user_id=user.id,
        service_type=data.service_type,
        comment=data.comment,
        planned_date=data.planned_date,
        status="new",
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    # Логируем действие
    log = WorkLog(
        request_id=request.id,
        user_id=user.id,
        action="created",
        details=f"Заявка создана: {data.service_type}",
    )
    db.add(log)

    # Создаём уведомление админу
    admins = db.query(User).filter(User.role == "admin").all()
    for admin in admins:
        notification = Notification(
            user_id=admin.id,
            request_id=request.id,
            type="new_request",
            message_text=f"Новая заявка #{request.id} от {user.full_name or user.telegram_id}",
            priority="normal",
        )
        db.add(notification)

    db.commit()
    db.refresh(request)

    return RequestOut.from_orm(request)


@router.get("/requests/my", response_model=List[RequestOut])
def get_my_requests(
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """Возвращает список заявок текущего пользователя (жильца)."""
    user = get_user_or_404(db, telegram_id)
    requests = db.query(Request).filter(Request.user_id == user.id).order_by(Request.created_at.desc()).all()
    return [RequestOut.from_orm(r) for r in requests]


@router.get("/requests/all", response_model=List[RequestOut])
def get_all_requests(
    telegram_id: int = Query(...),
    status: Optional[str] = None,
    service_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Возвращает список всех заявок (для работников и админов).
    Поддерживает фильтрацию по статусу и типу услуги.
    """
    user = get_user_or_404(db, telegram_id)
    check_role(user, ["worker", "admin"])

    query = db.query(Request)
    if status:
        query = query.filter(Request.status == status)
    if service_type:
        query = query.filter(Request.service_type == service_type)

    requests = query.order_by(Request.created_at.desc()).all()
    return [RequestOut.from_orm(r) for r in requests]


@router.get("/requests/{request_id}", response_model=RequestOut)
def get_request(
    request_id: int,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """Возвращает информацию о конкретной заявке."""
    user = get_user_or_404(db, telegram_id)
    request = db.query(Request).filter(Request.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # Жилец может видеть только свои заявки, работники/админы — все
    if user.role == "resident" and request.user_id != user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к чужой заявке")

    return RequestOut.from_orm(request)


@router.patch("/requests/{request_id}/status", response_model=RequestOut)
def update_request_status(
    request_id: int,
    data: RequestStatusUpdate,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Изменение статуса заявки (работник или админ).
    Допустимые переходы статусов (простейшая логика).
    """
    user = get_user_or_404(db, telegram_id)
    check_role(user, ["worker", "admin"])

    request = db.query(Request).filter(Request.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    old_status = request.status
    new_status = data.status

    # Проверка допустимых переходов (можно расширить)
    allowed_transitions = {
        "new": ["in_progress", "cancelled", "urgent"],
        "in_progress": ["completed", "cancelled"],
        "urgent": ["in_progress", "completed_second", "rejected"],
        "completed": ["paid", "complaint"],  # complaint обрабатывается отдельно
        "completed_second": ["paid"],
        "paid": [],
        "cancelled": [],
        "rejected": [],
    }
    if new_status not in allowed_transitions.get(old_status, []):
        raise HTTPException(status_code=400, detail=f"Недопустимый переход из {old_status} в {new_status}")

    request.status = new_status
    request.updated_at = datetime.utcnow()

    # Логируем
    log = WorkLog(
        request_id=request.id,
        user_id=user.id,
        action="status_changed",
        details=f"Статус изменён с {old_status} на {new_status}. Комментарий: {data.comment or ''}",
    )
    db.add(log)

    # Уведомление жильцу
    if request.user_id:
        notification = Notification(
            user_id=request.user_id,
            request_id=request.id,
            type="status_changed",
            message_text=f"Статус вашей заявки #{request.id} изменён на {new_status}",
            priority="normal" if new_status != "completed_second" else "high",
        )
        db.add(notification)

    db.commit()
    db.refresh(request)

    return RequestOut.from_orm(request)


# ---------- Претензии ----------
@router.post("/requests/{request_id}/complaint", response_model=ComplaintOut)
def create_complaint(
    request_id: int,
    data: ComplaintCreate,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Создание претензии к завершённой заявке.
    Только жилец, владелец исходной заявки, если она в статусе completed.
    """
    user = get_user_or_404(db, telegram_id)
    if user.role != "resident":
        raise HTTPException(status_code=403, detail="Только жильцы могут подавать претензии")

    original_request = db.query(Request).filter(Request.id == request_id).first()
    if not original_request:
        raise HTTPException(status_code=404, detail="Исходная заявка не найдена")
    if original_request.user_id != user.id:
        raise HTTPException(status_code=403, detail="Вы не можете подать претензию на чужую заявку")
    if original_request.status != "completed":
        raise HTTPException(status_code=400, detail="Претензия возможна только для завершённых заявок")

    # Создаём претензию
    complaint = Request(
        apartment_id=original_request.apartment_id,
        user_id=user.id,
        service_type="complaint",
        status="urgent",
        comment=data.comment,
        parent_request_id=original_request.id,
    )
    db.add(complaint)
    db.flush()  # получаем id

    # Сохраняем фото (если переданы base64 строки)
    if data.photos:
        # Папка для загрузок
        upload_dir = "static/uploads/complaints"
        os.makedirs(upload_dir, exist_ok=True)

        for idx, photo_b64 in enumerate(data.photos[: settings.MAX_COMPLAINT_PHOTOS]):
            try:
                # Простейший способ: декодируем base64 в бинарный файл
                import base64

                img_data = base64.b64decode(photo_b64.split(",")[-1])  # убираем data:image/...;base64,
                filename = f"complaint_{complaint.id}_{idx}.jpg"
                filepath = os.path.join(upload_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(img_data)

                photo = ComplaintPhoto(request_id=complaint.id, file_path=filepath)
                db.add(photo)
            except Exception as e:
                # Логируем ошибку, но не прерываем создание претензии
                print(f"Ошибка сохранения фото: {e}")

    # Логируем
    log = WorkLog(
        request_id=complaint.id,
        user_id=user.id,
        action="complaint_created",
        details=f"Претензия к заявке #{request_id}: {data.comment}",
    )
    db.add(log)

    # Уведомления всем работникам и админам (срочно)
    workers = db.query(User).filter(User.role.in_(["worker", "admin"])).all()
    for worker in workers:
        notification = Notification(
            user_id=worker.id,
            request_id=complaint.id,
            type="complaint_urgent",
            message_text=f"Срочная претензия #{complaint.id} по заявке #{request_id}",
            priority="urgent",
        )
        db.add(notification)

    db.commit()
    db.refresh(complaint)

    return ComplaintOut(
        id=complaint.id,
        parent_request_id=complaint.parent_request_id or 0,
        comment=complaint.comment or "",
        status=complaint.status,
        created_at=complaint.created_at,
    )


# ---------- Уведомления ----------
@router.get("/notifications", response_model=List[NotificationOut])
def get_my_notifications(
    telegram_id: int = Query(...),
    only_unread: bool = False,
    db: Session = Depends(get_db),
):
    """Возвращает уведомления текущего пользователя."""
    user = get_user_or_404(db, telegram_id)
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if only_unread:
        query = query.filter(Notification.is_sent == False)  # is_sent используется как прочитано?
    notifications = query.order_by(Notification.created_at.desc()).all()
    return [NotificationOut.from_orm(n) for n in notifications]


# ---------- Настройки (реквизиты и т.д.) ----------
@router.get("/settings/{key}", response_model=SettingOut)
def get_setting(
    key: str,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """Возвращает значение настройки по ключу."""
    user = get_user_or_404(db, telegram_id)
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Настройка не найдена")
    return SettingOut.from_orm(setting)


@router.post("/settings", response_model=SettingOut)
def create_or_update_setting(
    data: SettingUpdate,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Создаёт или обновляет настройку (только админ).
    Например, реквизиты для оплаты.
    """
    user = get_user_or_404(db, telegram_id)
    check_role(user, ["admin"])

    setting = db.query(Setting).filter(Setting.key == data.key).first()
    if setting:
        setting.value = data.value
    else:
        setting = Setting(key=data.key, value=data.value)
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return SettingOut.from_orm(setting)


# ---------- Погода и солнце ----------
@router.get("/weather/alert", response_model=WeatherAlertOut)
def get_weather_alert(
    building_id: int,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Возвращает предупреждение о погоде для конкретного дома.
    """
    user = get_user_or_404(db, telegram_id)
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Дом не найден")

    alert = get_weather_alert_for_building(building)
    return alert


@router.get("/solar/position", response_model=SolarPositionOut)
def get_solar_position(
    building_id: int,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Возвращает информацию о текущем положении солнца и освещённой стороне дома.
    """
    user = get_user_or_404(db, telegram_id)
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Дом не найден")

    position = get_solar_position_for_building(building)
    return position


# ---------- QR-код ----------
@router.get("/qr/{building_id}")
def get_qr_code(
    building_id: int,
    telegram_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """
    Генерирует QR-код для дома со ссылкой на Mini App.
    Только для админов.
    """
    user = get_user_or_404(db, telegram_id)
    check_role(user, ["admin"])

    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Дом не найден")

    qr_image = generate_qr_code(building_id)
    return StreamingResponse(qr_image, media_type="image/png")


# ---------- Экспорт CSV ----------
@router.get("/export/requests")
def export_requests_csv(
    telegram_id: int = Query(...),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Экспорт всех заявок в CSV (для админа).
    """
    user = get_user_or_404(db, telegram_id)
    check_role(user, ["admin"])

    query = db.query(Request)
    if status:
        query = query.filter(Request.status == status)
    requests = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Address", "Apartment", "Service Type", "Status", "Comment", "Created At", "User"])
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
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=requests.csv"},
    )

# app/services/qr.py
"""
Генерация QR-кодов для домов.

QR-код содержит ссылку на Mini App с параметром building_id,
чтобы жилец мог сразу открыть нужный дом для регистрации.
"""

import io

import qrcode

from app.config import settings


def generate_qr_code(building_id: int) -> io.BytesIO:
    """
    Создаёт PNG-изображение QR-кода со ссылкой на Mini App для конкретного дома.

    :param building_id: ID дома в базе данных
    :return: BytesIO с PNG-изображением
    """
    # Формируем URL с параметром building_id
    url = f"{settings.MINI_APP_URL}/?building_id={building_id}"

    # Настраиваем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    # Создаём изображение
    img = qr.make_image(fill_color="black", back_color="white")

    # Сохраняем в буфер
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return buffer

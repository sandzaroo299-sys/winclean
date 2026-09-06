# app/main.py
"""
Точка входа приложения.

Запускает FastAPI сервер, подключает API-роуты, раздаёт статические файлы Mini App,
инициализирует базу данных и запускает Telegram-бота в фоновом режиме.

Деплой на Render.com: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router as api_router
from app.config import settings
from app.db import init_db
from app.bot.main import start_bot, stop_bot

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения задачи бота
bot_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Контекст жизненного цикла приложения.
    Выполняется при старте и завершении.
    """
    global bot_task
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("База данных готова.")

    logger.info("Запуск Telegram-бота...")
    bot_task = asyncio.create_task(start_bot())
    logger.info("Бот запущен.")

    yield  # Здесь приложение работает

    logger.info("Остановка Telegram-бота...")
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    await stop_bot()
    logger.info("Бот остановлен.")


# Создаём FastAPI приложение с lifespan
app = FastAPI(
    title="Промышленный альпинизм - Мойка окон",
    description="Сервис для бригады промышленных альпинистов",
    version="1.0.0",
    lifespan=lifespan,
)

# Подключаем API-роутер
app.include_router(api_router)

# Раздаём статические файлы Mini App
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
else:
    logger.warning("Папка static не найдена! Mini App может не работать.")

@app.get("/")
async def serve_index():
    """
    Отдаёт index.html Mini App при обращении к корню.
    """
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Mini App не найден. Разместите файлы в папке static/"}


@app.get("/health")
async def health_check():
    """
    Эндпоинт проверки работоспособности (для Render.com).
    """
    return {"status": "ok", "bot_token_set": bool(settings.BOT_TOKEN)}

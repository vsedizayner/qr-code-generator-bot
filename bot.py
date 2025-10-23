"""
Telegram бот для генерации QR-кодов из URL-ссылок
Отправляет QR-коды в форматах SVG и PNG
"""

import io
import re
import logging
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
import qrcode
import qrcode.image.svg

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Токен бота (из переменной окружения)
import os
BOT_TOKEN = os.getenv("BOT_TOKEN", "6160411169:AAH9vy489abOPhimUXugV-uhemaRRs6Tcjo")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_valid_url(url: str) -> bool:
    """
    Проверяет, является ли строка валидным URL с http/https протоколом
    """
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except Exception:
        return False


def extract_single_url(text: str) -> str | None:
    """
    Извлекает URL из текста. Возвращает URL только если:
    - Текст содержит ровно одну ссылку
    - Ссылка является единственным содержимым сообщения (без дополнительного текста)
    """
    # Паттерн для поиска URL
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)
    
    # Проверяем, что найдена ровно одна ссылка
    if len(urls) != 1:
        return None
    
    url = urls[0]
    
    # Проверяем, что текст состоит только из этой ссылки (с возможными пробелами)
    if text.strip() != url:
        return None
    
    # Проверяем валидность URL
    if not is_valid_url(url):
        return None
    
    return url


def generate_qr_svg(url: str) -> bytes:
    """
    Генерирует QR-код в формате SVG
    """
    factory = qrcode.image.svg.SvgPathImage
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
        image_factory=factory
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Создаем SVG в памяти
    img = qr.make_image(fill_color="black", back_color="white")
    svg_buffer = io.BytesIO()
    img.save(svg_buffer)
    svg_buffer.seek(0)
    
    return svg_buffer.read()


def generate_qr_png(url: str) -> bytes:
    """
    Генерирует QR-код в формате PNG высокого качества
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=20,  # Увеличенный размер для высокого качества
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Создаем PNG в памяти
    img = qr.make_image(fill_color="black", back_color="white")
    png_buffer = io.BytesIO()
    img.save(png_buffer, format='PNG', dpi=(300, 300))
    png_buffer.seek(0)
    
    return png_buffer.read()


def sanitize_filename(url: str) -> str:
    """
    Создает безопасное имя файла из URL
    """
    # Удаляем протокол
    name = re.sub(r'^https?://', '', url)
    # Заменяем небезопасные символы
    name = re.sub(r'[^\w\-.]', '_', name)
    # Ограничиваем длину
    if len(name) > 50:
        name = name[:50]
    return name


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """
    Обработчик команды /start
    """
    await message.answer(
        "👋 Привет! Я бот для генерации QR-кодов.\n\n"
        "📎 Отправьте мне одну ссылку (начинающуюся с http:// или https://), "
        "и я создам для вас QR-код в форматах SVG и PNG.\n\n"
        "✅ Пример: https://example.com"
    )


@dp.message()
async def handle_message(message: types.Message):
    """
    Основной обработчик сообщений
    """
    try:
        # Извлекаем URL из сообщения
        url = extract_single_url(message.text)
        
        if not url:
            await message.answer(
                "❌ Пожалуйста, отправьте одну корректную ссылку "
                "(начинается с http:// или https://)."
            )
            return
        
        # Информируем пользователя о начале генерации
        status_msg = await message.answer("⏳ Генерирую QR-коды...")
        
        # Генерируем QR-коды
        try:
            svg_data = generate_qr_svg(url)
            png_data = generate_qr_png(url)
        except Exception as e:
            logger.error(f"Ошибка при генерации QR-кода: {e}")
            await status_msg.edit_text(
                "❌ Произошла ошибка при генерации QR-кода. Попробуйте еще раз."
            )
            return
        
        # Создаем имена файлов
        base_filename = sanitize_filename(url)
        svg_filename = f"{base_filename}_qr-code.svg"
        png_filename = f"{base_filename}_qr-code.png"
        
        # Подготавливаем файлы для отправки
        svg_file = BufferedInputFile(svg_data, filename=svg_filename)
        png_file = BufferedInputFile(png_data, filename=png_filename)
        
        # Отправляем файлы
        await message.answer_document(
            svg_file,
            caption=f"📊 QR-код для: {url}"
        )
        await message.answer_document(png_file)
        
        # Удаляем статусное сообщение
        await status_msg.delete()
        
        logger.info(f"QR-коды успешно отправлены для URL: {url}")
        
    except Exception as e:
        logger.error(f"Необработанная ошибка: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
        )


async def main():
    """
    Главная функция запуска бота
    """
    logger.info("Запуск бота...")
    try:
        # Удаляем вебхуки если они были установлены
        await bot.delete_webhook(drop_pending_updates=True)
        # Запускаем polling
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
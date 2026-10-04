import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ========= НАСТРОЙКА =========
# Вставить сюда ваш токен от @BotFather
BOT_TOKEN = "8951994357:AAFZtPZy_wnq68Wuqxxs311K4Asd2xLh9fM"

# Настройка логирования (чтобы видеть ошибки)
logging.basicConfig(level=logging.INFO)

# Создаём бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========= ОБРАБОТЧИКИ (ХЭНДЛЕРЫ) =========

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.reply(
        f"👋 Привет, {message.from_user.first_name}!\n"
        f"Я — <b>Omni | Чат Менеджер</b>.\n\n"
        f"Пока что я умею немного, но это только начало! 🚀"
    )

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.reply(
        "📖 <b>Доступные команды:</b>\n"
        "/start — Начать работу\n"
        "/help — Показать это сообщение\n"
        "/ping — Проверить, жив ли бот"
    )

# Команда /ping
@dp.message(Command("ping"))
async def cmd_ping(message: types.Message):
    await message.reply("🏓 Pong! Я на месте.")

# Эхо на обычные текстовые сообщения (не команды)
@dp.message()
async def echo_handler(message: types.Message):
    # Чтобы бот не спамил в ответ на все подряд,
    # отвечаем только если это не команда (команды начинаются с /)
    if not message.text.startswith("/"):
        await message.reply(f"Ты написал: {message.text}")

# ========= ЗАПУСК =========
async def main():
    print("🤖 Бот Omni запускается...")
    # Запускаем бота в режиме polling (постоянного опроса серверов Telegram)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
# run.py
import threading
import asyncio
from App import app  # твой Flask-приложение
from simple_bot import main as bot_main  # async функция из simple_bot.py


def run_flask():
    app.run(host="0.0.0.0", port=9000, debug=True)  # debug=True для разработки


if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Запускаем Telegram-бота в основном потоке
    asyncio.run(bot_main())
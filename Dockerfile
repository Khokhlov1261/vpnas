# Используем официальный образ Python
FROM python:3.12-slim

# Рабочая директория
WORKDIR /app

# Копируем файлы проекта
COPY . /app

# Устанавливаем pip и зависимости
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir python-telegram-bot psycopg2-binary python-dotenv python-dateutil gunicorn

# Делаем скрипт запуска исполняемым
RUN chmod +x start.sh

# Открываем порты
EXPOSE 8080 9000

# Запуск
CMD ["./start.sh"]
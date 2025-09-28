FROM python:3.12-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Создаём рабочую директорию
WORKDIR /app

# Копируем файлы
COPY requirements.txt .
COPY App.py .
COPY simple_bot.py .
COPY start.sh .
COPY nginx/default.conf /etc/nginx/sites-enabled/default

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Делаем скрипт запуска исполняемым
RUN chmod +x start.sh

# expose порты
EXPOSE 80 9000

# Запуск всех процессов
CMD ["./start.sh"]
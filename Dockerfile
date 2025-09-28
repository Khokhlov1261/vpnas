FROM python:3.12-slim

# Устанавливаем базовые пакеты и nginx
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libffi-dev \
    python3-dev \
    nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .

# Делаем start.sh исполняемым
RUN chmod +x start.sh

# Копируем конфиг nginx
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

# Порты: 80 для Nginx, 9000 для Gunicorn (внутренний)
EXPOSE 80 9000

CMD ["./start.sh"]
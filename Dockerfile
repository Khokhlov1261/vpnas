FROM python:3.12-slim

# Базовые пакеты для сборки и pip
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Убедимся, что скрипт исполняемый
RUN chmod +x start.sh

EXPOSE 8080 9000
CMD ["./start.sh"]
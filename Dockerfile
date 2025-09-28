FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Если не используем nginx, просто стартуем бота через start.sh
EXPOSE 8080 9000
CMD ["./start.sh"]
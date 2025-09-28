#!/bin/bash
set -e

# Запускаем Flask через Gunicorn
gunicorn -w 4 -b 0.0.0.0:9000 App:app &

# Запускаем Nginx
nginx -g "daemon off;" &

# Запускаем Aiogram бота
python3 simple_bot.py
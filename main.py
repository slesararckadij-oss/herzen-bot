# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
import asyncio
from datetime import datetime
from flask import Flask, send_from_directory, request, Response, jsonify
import pytz
import requests # requests стабильнее для простых POST в Flask
from parser import HerzenParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
TZ = pytz.timezone("Europe/Moscow")
PORT = int(os.environ.get("PORT", 8080))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Инициализируем парсер один раз
parser = HerzenParser()
user_groups = {}

def load_users():
    global user_groups
    if os.path.exists("users.json"):
        try:
            with open("users.json", encoding="utf-8") as f:
                user_groups = {int(k): v for k, v in json.load(f).items()}
        except Exception as e:
            logger.error(f"Load users error: {e}")
            user_groups = {}

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(user_groups, f, ensure_ascii=False)

load_users()

def send_message(chat_id, text, keyboard=None):
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "HTML",
        "reply_markup": keyboard if keyboard else {}
    }
    try:
        requests.post(f"{API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        logger.error(f"Send message error: {e}")

def webapp_keyboard():
    return {
        "inline_keyboard": [[{
            "text": "📅 Открыть расписание",
            "web_app": {"url": WEBAPP_URL}
        }]]
    }

# --- FLASK APP ---
flask_app = Flask(__name__, static_folder="webapp")

@flask_app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

# Хелпер для запуска асинхронных функций в Flask
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@flask_app.route("/api/groups")
def api_groups():
    groups = run_async(parser.get_all_groups())
    # Сортируем группы по алфавиту для удобства выбора
    groups.sort(key=lambda x: x['name'])
    return jsonify({"groups": groups})

@flask_app.route("/api/schedule")
def api_schedule():
    group_id = request.args.get("group_id") # id группы из атласа
    date_str = request.args.get("date")    # формат YYYY-MM-DD
    
    if not group_id or not date_str:
        return jsonify({"error": "No params"}), 400
        
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        # Вызываем парсинг конкретного дня
        lessons = run_async(parser.get_schedule_for_date(group_id, target_date))
        return jsonify({"lessons": lessons})
    except Exception as e:
        logger.error(f"API Schedule error: {e}")
        return jsonify({"lessons": []})

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    if not update or "message" not in update:
        return "ok"
    
    msg = update["message"]
    chat_id = msg.get("chat", {}).get("id")
    text = msg.get("text", "")

    if text == "/start":
        load_users()
        current_group = user_groups.get(chat_id, {}).get("group_name", "не выбрана ❌")
        send_message(
            chat_id,
            f"<b>Привет!</b> 👋\n\nТвоя текущая группа: <code>{current_group}</code>\n\nНажми кнопку, чтобы посмотреть расписание или выбрать группу:",
            keyboard=webapp_keyboard()
        )
    return "ok"

# Запуск Flask
if __name__ == "__main__":
    # Установка вебхука
    if WEBAPP_URL:
        requests.post(f"{API}/setWebhook", json={"url": f"{WEBAPP_URL}/webhook"})
    
    flask_app.run(host="0.0.0.0", port=PORT)
    

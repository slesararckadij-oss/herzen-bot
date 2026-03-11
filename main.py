# -*- coding: utf-8 -*-
import os
import json
import logging
import asyncio
import requests
from flask import Flask, send_from_directory, request, jsonify
from parser import HerzenParser

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__, static_folder="webapp")
parser = HerzenParser()

# Хранилище групп (в памяти)
user_groups = {}

def run_async(coro):
    """Помощник для запуска асинхронного кода в Flask-потоке"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

@app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@app.route("/api/groups")
def api_groups():
    try:
        groups = run_async(parser.get_all_groups())
        return jsonify({"groups": groups})
    except Exception as e:
        logger.error(f"Error fetching groups: {e}")
        return jsonify({"groups": [], "error": str(e)}), 500

@app.route("/api/schedule")
def api_schedule():
    g_id = request.args.get("group_id")
    date_str = request.args.get("date")
    
    if not g_id or not date_str:
        return jsonify({"error": "Missing params"}), 400

    logger.info(f"==> Запрос API: группа {g_id}, дата {date_str}")
    
    try:
        # Передаем group_id как строку
        lessons = run_async(parser.get_schedule_for_date(str(g_id), date_str))
        logger.info(f"<== Найдено занятий: {len(lessons)}")
        return jsonify({"lessons": lessons})
    except Exception as e:
        logger.error(f"Ошибка API расписания: {e}")
        return jsonify({"lessons": [], "error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data or "message" not in data:
        return "ok"
    
    msg = data["message"]
    chat_id = str(msg["chat"]["id"])

    # Команда /start
    if msg.get("text") == "/start":
        requests.post(f"{API}/sendMessage", json={
            "chat_id": chat_id,
            "text": "📅 Привет! Нажми кнопку ниже, чтобы открыть расписание РГПУ:",
            "reply_markup": {
                "inline_keyboard": [[{
                    "text": "📅 Открыть расписание",
                    "web_app": {"url": WEBAPP_URL}
                }]]
            }
        })
        
    return "ok"

if __name__ == "__main__":
    # Авто-установка вебхука
    if WEBAPP_URL and BOT_TOKEN:
        requests.post(f"{API}/setWebhook", json={"url": f"{WEBAPP_URL}/webhook"})
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

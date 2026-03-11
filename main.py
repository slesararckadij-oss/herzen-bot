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

# Временное хранилище групп (в памяти)
user_groups = {}

def send_tg(method, payload):
    """Отправка запросов в Telegram API"""
    try:
        url = f"{API}/{method}"
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка отправки в TG: {e}")
        return {}

@app.route("/")
def index():
    """Главная страница WebApp"""
    return send_from_directory("webapp", "index.html")

@app.route("/api/groups")
def api_groups():
    """Получение списка всех групп"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        groups = loop.run_until_complete(parser.get_all_groups())
        return jsonify({"groups": groups})
    finally:
        loop.close()

@app.route("/api/schedule")
def api_schedule():
    """Получение расписания для конкретной группы и даты"""
    g_id = request.args.get("group_id")
    date_str = request.args.get("date") # Ожидается YYYY-MM-DD
    
    if not g_id or not date_str:
        return jsonify({"error": "Missing params"}), 400

    logger.info(f"Запрос расписания: группа {g_id}, дата {date_str}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Парсер теперь устойчив к строковому формату даты
        lessons = loop.run_until_complete(parser.get_schedule_for_date(str(g_id), date_str))
        return jsonify({"lessons": lessons})
    except Exception as e:
        logger.error(f"Ошибка API расписания: {e}")
        return jsonify({"lessons": [], "error": str(e)}), 500
    finally:
        loop.close()

@app.route("/api/user_group")
def api_user_group():
    """Получение сохраненной группы пользователя"""
    chat_id = request.args.get("chat_id")
    if chat_id and chat_id in user_groups:
        return jsonify(user_groups[chat_id])
    return jsonify({})

@app.route("/webhook", methods=["POST"])
def webhook():
    """Обработка обновлений от Telegram"""
    data = request.json
    if not data or "message" not in data:
        return "ok"
    
    msg = data["message"]
    chat_id = str(msg["chat"]["id"])

    # Обработка данных из WebApp (кнопка "Сохранить группу")
    if "web_app_data" in msg:
        try:
            wa_data = json.loads(msg["web_app_data"]["data"])
            if wa_data.get("action") == "set_group":
                user_groups[chat_id] = {
                    "group_id": wa_data["group_id"],
                    "group_name": wa_data["group_name"]
                }
                send_tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": f"✅ Группа <b>{wa_data['group_name']}</b> сохранена!",
                    "parse_mode": "HTML"
                })
        except Exception as e:
            logger.error(f"Ошибка обработки WebAppData: {e}")
        return "ok"

    # Команда /start
    if msg.get("text") == "/start":
        send_tg("sendMessage", {
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
    # Установка вебхука при запуске
    if WEBAPP_URL and BOT_TOKEN:
        res = requests.post(f"{API}/setWebhook", json={"url": f"{WEBAPP_URL}/webhook"})
        logger.info(f"Webhook set status: {res.json()}")
    
    port = int(os.environ.get("PORT", 8080))
    # Запуск Flask
    app.run(host="0.0.0.0", port=port)

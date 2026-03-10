import os
import json
import logging
import threading
from datetime import datetime
from flask import Flask, send_from_directory, jsonify, request
import requests as req
import pytz
import asyncio

from parser import HerzenParser

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
TZ = pytz.timezone("Europe/Moscow")
PORT = int(os.environ.get("PORT", 8080))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== STORAGE =====
user_groups: dict = {}

def save_users():
    with open("users.json", "w") as f:
        json.dump(user_groups, f, ensure_ascii=False)

def load_users():
    global user_groups
    if os.path.exists("users.json"):
        with open("users.json") as f:
            data = json.load(f)
            user_groups = {int(k): v for k, v in data.items()}

load_users()

# ===== TELEGRAM HELPERS =====
def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    req.post(f"{API}/sendMessage", json=payload)

def answer_callback(callback_id, text=""):
    req.post(f"{API}/answerCallbackQuery", json={"callback_query_id": callback_id, "text": text})

def set_webhook(url):
    req.post(f"{API}/setWebhook", json={"url": url, "drop_pending_updates": True})

def open_webapp_keyboard():
    return {
        "inline_keyboard": [[{
            "text": "📅 Открыть расписание",
            "web_app": {"url": WEBAPP_URL}
        }]]
    }

# ===== FLASK APP =====
flask_app = Flask(__name__, static_folder="webapp")

@flask_app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@flask_app.route("/api/groups")
def api_groups():
    loop = asyncio.new_event_loop()
    parser = HerzenParser()
    groups = loop.run_until_complete(parser.get_all_groups())
    loop.close()
    return jsonify({"groups": groups})

@flask_app.route("/api/schedule")
def api_schedule():
    group_id = request.args.get("group_id", type=int)
    date_str = request.args.get("date")
    if not group_id or not date_str:
        return jsonify({"error": "missing params"}), 400
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"error": "bad date"}), 400
    loop = asyncio.new_event_loop()
    parser = HerzenParser()
    lessons = loop.run_until_complete(parser.get_schedule_for_date(group_id, target))
    loop.close()
    return jsonify({"lessons": lessons})

@flask_app.route("/api/schedule/week")
def api_schedule_week():
    group_id = request.args.get("group_id", type=int)
    date_str = request.args.get("date")
    if not group_id or not date_str:
        return jsonify({"error": "missing params"}), 400
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"error": "bad date"}), 400
    loop = asyncio.new_event_loop()
    parser = HerzenParser()
    week = loop.run_until_complete(parser.get_schedule_week(group_id, target))
    loop.close()
    return jsonify({"week": week})

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return "ok"

    # Обычное сообщение
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        # WebApp data
        if "web_app_data" in msg:
            try:
                wa = json.loads(msg["web_app_data"]["data"])
                uid = chat_id
                if wa.get("action") == "set_group":
                    user_groups[uid] = {
                        "group_id": wa["group_id"],
                        "group_name": wa["group_name"],
                        "notify": user_groups.get(uid, {}).get("notify", True)
                    }
                    save_users()
                    send_message(uid, f"✅ Группа <b>{wa['group_name']}</b> сохранена!")
                elif wa.get("action") == "toggle_notify":
                    if uid in user_groups:
                        user_groups[uid]["notify"] = wa.get("notify", True)
                        save_users()
                    status = "включены ✅" if wa.get("notify") else "отключены ❌"
                    send_message(uid, f"🔔 Уведомления {status}")
            except Exception as e:
                logger.error(f"webapp_data error: {e}")
            return "ok"

        if text == "/start":
            load_users()
            name = user_groups.get(chat_id, {}).get("group_name", "не выбрана")
            send_message(
                chat_id,
                f"👋 Привет! Я бот расписания РГПУ им. Герцена.\n\n"
                f"Твоя группа: <b>{name}</b>\n\n"
                f"Нажми кнопку ниже 👇",
                keyboard=open_webapp_keyboard()
            )

    return "ok"

# ===== SCHEDULER =====
def run_scheduler():
    import time
    notified = set()
    while True:
        try:
            now = datetime.now(TZ)
            load_users()
            for user_id, data in list(user_groups.items()):
                if not data.get("notify", True):
                    continue
                group_id = data["group_id"]
                loop = asyncio.new_event_loop()
                parser = HerzenParser()
                lessons = loop.run_until_complete(parser.get_schedule_for_date(group_id, now.date()))
                loop.close()

                for lesson in lessons:
                    key = (user_id, str(now.date()), lesson["time_start"])
                    if key in notified:
                        continue
                    try:
                        h, m = map(int, lesson["time_start"].split(":"))
                        lesson_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    except Exception:
                        continue
                    diff = (lesson_dt - now).total_seconds() / 60
                    if 0 < diff <= 15:
                        notified.add(key)
                        text = (
                            f"🔔 <b>Через {int(diff)} мин — пара!</b>\n\n"
                            f"📚 {lesson['subject']}\n"
                            f"⏰ {lesson['time_start']} – {lesson['time_end']}\n"
                        )
                        if lesson.get("room"):
                            text += f"🏛 {lesson['room']}\n"
                        if lesson.get("teacher"):
                            text += f"👤 {lesson['teacher']}\n"
                        send_message(user_id, text)
            notified = {k for k in notified if k[1] == str(now.date())}
        except Exception as e:
            logger.error(f"scheduler error: {e}")
        time.sleep(60)

# ===== MAIN =====
if __name__ == "__main__":
    # Установить webhook
    if WEBAPP_URL:
        webhook_url = WEBAPP_URL.rstrip("/") + "/webhook"
        set_webhook(webhook_url)
        logger.info(f"Webhook set: {webhook_url}")

    # Запуск планировщика в фоне
    t = threading.Thread(target=run_scheduler, daemon=True)
    t.start()

    # Запуск Flask
    flask_app.run(host="0.0.0.0", port=PORT)
                

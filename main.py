# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, request, Response
import pytz
import urllib.request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
TZ = pytz.timezone("Europe/Moscow")
PORT = int(os.environ.get("PORT", 8080))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

user_groups = {}

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(user_groups, f, ensure_ascii=False)

def load_users():
    global user_groups
    if os.path.exists("users.json"):
        with open("users.json", encoding="utf-8") as f:
            user_groups = {int(k): v for k, v in json.load(f).items()}

load_users()

def tg_request(method, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/{method}",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"tg_request {method} error: {e}")
        return None

def send_message(chat_id, text, keyboard=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard:
        payload["reply_markup"] = keyboard
    tg_request("sendMessage", payload)

def set_webhook(url):
    tg_request("setWebhook", {"url": url, "drop_pending_updates": True})
    logger.info(f"Webhook set: {url}")

def webapp_keyboard():
    return {
        "inline_keyboard": [[{
            "text": "📅 Открыть расписание",
            "web_app": {"url": WEBAPP_URL}
        }]]
    }

# Flask
flask_app = Flask(__name__, static_folder="webapp")

def json_response(data):
    return Response(
        json.dumps(data, ensure_ascii=False),
        mimetype="application/json; charset=utf-8"
    )

@flask_app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@flask_app.route("/api/groups")
def api_groups():
    import asyncio
    from parser import HerzenParser
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    groups = loop.run_until_complete(HerzenParser().get_all_groups())
    loop.close()
    return json_response({"groups": groups})

@flask_app.route("/api/schedule")
def api_schedule():
    import asyncio
    from parser import HerzenParser
    group_id = request.args.get("group_id", type=int)
    date_str = request.args.get("date")
    if not group_id or not date_str:
        return json_response({"error": "missing params"})
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return json_response({"error": "bad date"})
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    lessons = loop.run_until_complete(HerzenParser().get_schedule_for_date(group_id, target))
    loop.close()
    return json_response({"lessons": lessons})

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True)
    if not data:
        return "ok"

    msg = data.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    if not chat_id:
        return "ok"

    # WebApp data
    if "web_app_data" in msg:
        try:
            wa = json.loads(msg["web_app_data"]["data"])
            if wa.get("action") == "set_group":
                user_groups[chat_id] = {
                    "group_id": wa["group_id"],
                    "group_name": wa["group_name"],
                    "notify": user_groups.get(chat_id, {}).get("notify", True)
                }
                save_users()
                send_message(chat_id, f"✅ Группа <b>{wa['group_name']}</b> сохранена!")
            elif wa.get("action") == "toggle_notify":
                if chat_id in user_groups:
                    user_groups[chat_id]["notify"] = wa.get("notify", True)
                    save_users()
                status = "включены ✅" if wa.get("notify") else "отключены ❌"
                send_message(chat_id, f"🔔 Уведомления {status}")
        except Exception as e:
            logger.error(f"webapp_data error: {e}")
        return "ok"

    text = msg.get("text", "")
    if text == "/start":
        load_users()
        name = user_groups.get(chat_id, {}).get("group_name", "не выбрана")
        send_message(
            chat_id,
            f"👋 Привет! Я бот расписания РГПУ им. Герцена.\n\nТвоя группа: <b>{name}</b>\n\nНажми кнопку ниже 👇",
            keyboard=webapp_keyboard()
        )

    return "ok"

def run_scheduler():
    import time, asyncio
    from parser import HerzenParser
    notified = set()
    while True:
        try:
            now = datetime.now(TZ)
            load_users()
            for user_id, data in list(user_groups.items()):
                if not data.get("notify", True):
                    continue
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                lessons = loop.run_until_complete(
                    HerzenParser().get_schedule_for_date(data["group_id"], now.date())
                )
                loop.close()
                for lesson in lessons:
                    key = (user_id, str(now.date()), lesson["time_start"])
                    if key in notified:
                        continue
                    try:
                        h, m = map(int, lesson["time_start"].split(":"))
                        lesson_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        diff = (lesson_dt - now).total_seconds() / 60
                        if 0 < diff <= 10:  # Напоминание за 10 минут
                            notified.add(key)
                            t = f"🔔 <b>Через {int(diff)} мин — пара!</b>\n\n📚 {lesson['subject']}\n⏰ {lesson['time_start']} – {lesson['time_end']}\n"
                            if lesson.get("room"): t += f"🏛 {lesson['room']}\n"
                            if lesson.get("teacher"): t += f"👤 {lesson['teacher']}\n"
                            send_message(user_id, t)
                    except Exception:
                        continue
            # Оставляем только текущие день-ключи
            notified = {k for k in notified if k[1] == str(now.date())}
        except Exception as e:
            logger.error(f"scheduler: {e}")
        time.sleep(60)

if __name__ == "__main__":
    if WEBAPP_URL:
        set_webhook(WEBAPP_URL.rstrip("/") + "/webhook")
    threading.Thread(target=run_scheduler, daemon=True).start()
    flask_app.run(host="0.0.0.0", port=PORT)

# -*- coding: utf-8 -*-
import os
import json
import logging
import threading
from datetime import datetime
from flask import Flask, send_from_directory, jsonify, request
import pytz

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
TZ = pytz.timezone("Europe/Moscow")
PORT = int(os.environ.get("PORT", 8080))
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

user_groups: dict = {}

def save_users():
    with open("users.json", "w", encoding="utf-8") as f:
        json.dump(user_groups, f, ensure_ascii=False)

def load_users():
    global user_groups
    if os.path.exists("users.json"):
        with open("users.json", encoding="utf-8") as f:
            data = json.load(f)
            user_groups = {int(k): v for k, v in data.items()}

load_users()

import urllib.request
import urllib.parse

def send_message(chat_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = keyboard
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error(f"send_message error: {e}")

def set_webhook(url):
    payload = json.dumps({"url": url, "drop_pending_updates": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/setWebhook",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.info(f"Webhook set: {url}")
    except Exception as e:
        logger.error(f"set_webhook error: {e}")

def open_webapp_keyboard():
    return {
        "inline_keyboard": [[{
            "text": "📅 Открыть расписание",
            "web_app": {"url": WEBAPP_URL}
        }]]
    }

flask_app = Flask(__name__, static_folder="webapp")
flask_app.config["JSON_AS_ASCII"] = False

@flask_app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@flask_app.route("/api/groups")
def api_groups():
    import asyncio
    from parser import HerzenParser
    loop = asyncio.new_event_loop()
    groups = loop.run_until_complete(HerzenParser().get_all_groups())
    loop.close()
    return flask_app.response_class(
        json.dumps({"groups": groups}, ensure_ascii=False),
        mimetype="application/json"
    )

@flask_app.route("/api/schedule")
def api_schedule():
    import asyncio
    from parser import HerzenParser
    group_id = request.args.get("group_id", type=int)
    date_str = request.args.get("date")
    if not group_id or not date_str:
        return jsonify({"error": "missing params"}), 400
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"error": "bad date"}), 400
    loop = asyncio.new_event_loop()
    lessons = loop.run_until_complete(HerzenParser().get_schedule_for_date(group_id, target))
    loop.close()
    return flask_app.response_class(
        json.dumps({"lessons": lessons}, ensure_ascii=False),
        mimetype="application/json"
    )

@flask_app.route("/api/schedule/week")
def api_schedule_week():
    import asyncio
    from parser import HerzenParser
    group_id = request.args.get("group_id", type=int)
    date_str = request.args.get("date")
    if not group_id or not date_str:
        return jsonify({"error": "missing params"}), 400
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"error": "bad date"}), 400
    loop = asyncio.new_event_loop()
    week = loop.run_until_complete(HerzenParser().get_schedule_week(group_id, target))
    loop.close()
    return flask_app.response_class(
        json.dumps({"week": week}, ensure_ascii=False),
        mimetype="application/json"
    )

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if not data:
        return "ok"

    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

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
                f"👋 Привет! Я бот расписания РГПУ им. Герцена.\n\nТвоя группа: <b>{name}</b>\n\nНажми кнопку ниже 👇",
                keyboard=open_webapp_keyboard()
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
                group_id = data["group_id"]
                loop = asyncio.new_event_loop()
                lessons = loop.run_until_complete(HerzenParser().get_schedule_for_date(group_id, now.date()))
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
                        text = f"🔔 <b>Через {int(diff)} мин — пара!</b>\n\n📚 {lesson['subject']}\n⏰ {lesson['time_start']} – {lesson['time_end']}\n"
                        if lesson.get("room"):
                            text += f"🏛 {lesson['room']}\n"
                        if lesson.get("teacher"):
                            text += f"👤 {lesson['teacher']}\n"
                        send_message(user_id, text)
            notified = {k for k in notified if k[1] == str(now.date())}
        except Exception as e:
            logger.error(f"scheduler error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    if WEBAPP_URL:
        set_webhook(WEBAPP_URL.rstrip("/") + "/webhook")
    threading.Thread(target=run_scheduler, daemon=True).start()
    flask_app.run(host="0.0.0.0", port=PORT)
    

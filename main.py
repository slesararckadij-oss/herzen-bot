# -*- coding: utf-8 -*-
import os
import json
import logging
import asyncio
import sqlite3
import threading
import requests
from datetime import datetime, date, timedelta
from flask import Flask, send_from_directory, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from parser import HerzenParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__, static_folder="webapp")
parser = HerzenParser()
db_lock = threading.Lock()

# ─── DB ──────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect("reminders.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id     INTEGER PRIMARY KEY,
                group_id    TEXT,
                remind_min  INTEGER DEFAULT 15
            )
        """)
        conn.commit()

init_db()

def get_user(chat_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(row) if row else None

def upsert_user(chat_id, group_id=None, remind_min=None):
    with db_lock:
        with get_db() as conn:
            existing = conn.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
            if existing:
                if group_id is not None:
                    conn.execute("UPDATE users SET group_id=? WHERE chat_id=?", (group_id, chat_id))
                if remind_min is not None:
                    conn.execute("UPDATE users SET remind_min=? WHERE chat_id=?", (remind_min, chat_id))
            else:
                conn.execute(
                    "INSERT INTO users (chat_id, group_id, remind_min) VALUES (?,?,?)",
                    (chat_id, group_id, remind_min or 15)
                )
            conn.commit()

def get_all_users():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM users WHERE group_id IS NOT NULL").fetchall()]

# ─── HELPERS ─────────────────────────────────────────────
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(f"{API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        logger.error(f"sendMessage error: {e}")

def set_menu_button(chat_id):
    """Ставит кнопку меню (Menu Button) для конкретного чата."""
    try:
        requests.post(f"{API}/setChatMenuButton", json={
            "chat_id": chat_id,
            "menu_button": {
                "type": "web_app",
                "text": "📅 Расписание",
                "web_app": {"url": WEBAPP_URL}
            }
        }, timeout=10)
    except Exception as e:
        logger.error(f"setChatMenuButton error: {e}")

# ─── REMINDERS ───────────────────────────────────────────
def check_and_send_reminders():
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    users = get_all_users()

    for user in users:
        chat_id = user["chat_id"]
        group_id = user["group_id"]
        remind_min = user.get("remind_min", 15)

        try:
            lessons = run_async(parser.get_schedule_for_date(group_id, today_str))
        except Exception as e:
            logger.error(f"Reminder parse error for {chat_id}: {e}")
            continue

        for lesson in lessons:
            try:
                lesson_time = datetime.strptime(f"{today_str} {lesson['time_start']}", "%Y-%m-%d %H:%M")
                diff_minutes = (lesson_time - now).total_seconds() / 60
                # Отправляем если до пары осталось remind_min ± 1 минута
                if remind_min - 1 <= diff_minutes <= remind_min + 1:
                    text = (
                        f"🔔 <b>Напоминание о паре!</b>\n\n"
                        f"⏰ <b>{lesson['time_start']} — {lesson['time_end']}</b>\n"
                        f"📚 {lesson['subject']}\n"
                        f"🏛️ {lesson['room']}\n"
                        f"👤 {lesson['teacher']}"
                    )
                    send_message(chat_id, text, reply_markup={
                        "inline_keyboard": [[
                            {"text": "📅 Открыть расписание", "web_app": {"url": WEBAPP_URL}}
                        ]]
                    })
                    logger.info(f"Reminder sent to {chat_id} for {lesson['subject']}")
            except Exception as e:
                logger.error(f"Reminder send error: {e}")

# ─── SCHEDULER ───────────────────────────────────────────
scheduler = BackgroundScheduler(timezone="Europe/Moscow")
scheduler.add_job(check_and_send_reminders, "interval", minutes=1)
scheduler.start()

# ─── FLASK ROUTES ────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@app.route("/api/groups")
def api_groups():
    return jsonify({"groups": run_async(parser.get_all_groups())})

@app.route("/api/schedule")
def api_schedule():
    g_id = request.args.get("group_id")
    date_str = request.args.get("date")
    if not g_id or not date_str:
        return jsonify({"error": "No params"}), 400
    lessons = run_async(parser.get_schedule_for_date(str(g_id), date_str))
    return jsonify({"lessons": lessons})

@app.route("/api/set_reminder", methods=["POST"])
def api_set_reminder():
    """Вызывается из WebApp для сохранения настроек напоминания."""
    data = request.json
    chat_id = data.get("chat_id")
    group_id = data.get("group_id")
    remind_min = data.get("remind_min")
    if not chat_id:
        return jsonify({"error": "No chat_id"}), 400
    upsert_user(int(chat_id), group_id=group_id, remind_min=remind_min)
    return jsonify({"ok": True})

@app.route("/api/get_settings")
def api_get_settings():
    chat_id = request.args.get("chat_id")
    if not chat_id:
        return jsonify({"error": "No chat_id"}), 400
    user = get_user(int(chat_id))
    return jsonify(user or {"chat_id": int(chat_id), "group_id": None, "remind_min": 15})

# ─── WEBHOOK ─────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        return "ok"

    # Обычное сообщение
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        if text == "/start":
            upsert_user(chat_id)
            set_menu_button(chat_id)
            send_message(chat_id,
                "👋 Привет! Я бот расписания РГПУ.\n\n"
                "📅 Нажми кнопку <b>«Расписание»</b> внизу чтобы открыть расписание.\n"
                "🔔 Там же можно настроить напоминания о парах.",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "📅 Открыть расписание", "web_app": {"url": WEBAPP_URL}}
                    ]]
                }
            )

        elif text.startswith("/remind"):
            # /remind 15 — установить напоминание за 15 минут
            parts = text.split()
            if len(parts) == 2 and parts[1].isdigit():
                minutes = int(parts[1])
                if 1 <= minutes <= 120:
                    upsert_user(chat_id, remind_min=minutes)
                    send_message(chat_id, f"✅ Буду напоминать за <b>{minutes} мин</b> до пары!")
                else:
                    send_message(chat_id, "⚠️ Укажи от 1 до 120 минут.")
            else:
                send_message(chat_id, "Использование: /remind 15\nНапоминание придёт за указанное кол-во минут до пары.")

        elif text == "/stop":
            upsert_user(chat_id, remind_min=0)
            send_message(chat_id, "🔕 Напоминания отключены.")

    # Данные из WebApp
    if "message" in data and data["message"].get("web_app_data"):
        chat_id = data["message"]["chat"]["id"]
        try:
            wa_data = json.loads(data["message"]["web_app_data"]["data"])
            group_id = wa_data.get("group_id")
            remind_min = wa_data.get("remind_min")
            if group_id:
                upsert_user(chat_id, group_id=group_id, remind_min=remind_min)
                logger.info(f"WebApp data saved for {chat_id}: group={group_id}, remind={remind_min}")
        except Exception as e:
            logger.error(f"WebApp data parse error: {e}")

    return "ok"

# ─── MAIN ────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

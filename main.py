import asyncio
import logging
import os
import json
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask, send_from_directory, jsonify, request
import pytz

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage

from parser import HerzenParser
from scheduler import run_scheduler

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN", "СЮДА_ВСТАВЬ_ТОКЕН")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://твой-сайт.onrender.com")  # заменится автоматически на Render
TZ = pytz.timezone("Europe/Moscow")
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)

# ===== FLASK APP (сервер для Mini App + API) =====
flask_app = Flask(__name__, static_folder="webapp")

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
        from datetime import date
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


# ===== TELEGRAM BOT =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    uid = msg.from_user.id
    load_users()
    name = user_groups.get(uid, {}).get("group_name", "не выбрана")

    builder = InlineKeyboardBuilder()
    builder.button(
        text="📅 Открыть расписание",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )
    builder.adjust(1)

    await msg.answer(
        f"👋 Привет! Я бот расписания РГПУ им. Герцена.\n\n"
        f"Твоя группа: <b>{name}</b>\n\n"
        f"Нажми кнопку ниже — откроется удобное расписание прямо внутри Telegram 👇",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@dp.message(F.web_app_data)
async def on_webapp_data(msg: Message):
    try:
        data = json.loads(msg.web_app_data.data)
        uid = msg.from_user.id

        if data.get("action") == "set_group":
            user_groups[uid] = {
                "group_id": data["group_id"],
                "group_name": data["group_name"],
                "notify": user_groups.get(uid, {}).get("notify", True)
            }
            save_users()
            await msg.answer(f"✅ Группа <b>{data['group_name']}</b> сохранена!", parse_mode="HTML")

        elif data.get("action") == "toggle_notify":
            if uid in user_groups:
                user_groups[uid]["notify"] = data.get("notify", True)
                save_users()
            status = "включены ✅" if data.get("notify") else "отключены ❌"
            await msg.answer(f"🔔 Уведомления {status}")

    except Exception as e:
        logging.error(f"webapp_data error: {e}")


# ===== ЗАПУСК =====
def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

async def main():
    load_users()
    # Flask в отдельном потоке
    t = Thread(target=run_flask, daemon=True)
    t.start()
    # Scheduler уведомлений
    asyncio.create_task(run_scheduler(bot, user_groups, TZ, notify_before=15))
    # Бот
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

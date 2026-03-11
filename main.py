# -*- coding: utf-8 -*-
import os
import json
import logging
import asyncio
import requests
from flask import Flask, send_from_directory, request, jsonify
from parser import HerzenParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__, static_folder="webapp")
parser = HerzenParser()

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: return loop.run_until_complete(coro)
    finally: loop.close()

@app.route("/")
def index(): return send_from_directory("webapp", "index.html")

@app.route("/api/groups")
def api_groups():
    return jsonify({"groups": run_async(parser.get_all_groups())})

@app.route("/api/schedule")
def api_schedule():
    g_id = request.args.get("group_id")
    date = request.args.get("date")
    if not g_id or not date: return jsonify({"error": "No params"}), 400
    lessons = run_async(parser.get_schedule_for_date(str(g_id), date))
    return jsonify({"lessons": lessons})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        if data["message"].get("text") == "/start":
            requests.post(f"{API}/sendMessage", json={
                "chat_id": chat_id,
                "text": "📅 Расписание РГПУ открыто!",
                "reply_markup": {"inline_keyboard": [[{"text": "📅 Открыть", "web_app": {"url": WEBAPP_URL}}]]}
            })
    return "ok"

if __name__ == "__main__":
    if WEBAPP_URL and BOT_TOKEN:
        requests.post(f"{API}/setWebhook", json={"url": f"{WEBAPP_URL}/webhook"})
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

import os, json, logging, asyncio, requests
from flask import Flask, send_from_directory, request, jsonify
from datetime import datetime
from parser import HerzenParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__, static_folder="webapp")
parser = HerzenParser()

def send_tg(method, payload):
    return requests.post(f"{API}/{method}", json=payload).json()

@app.route("/")
def index(): return send_from_directory("webapp", "index.html")

@app.route("/api/groups")
def api_groups():
    loop = asyncio.new_event_loop()
    groups = loop.run_until_complete(parser.get_all_groups())
    return jsonify({"groups": groups})

@app.route("/api/schedule")
def api_schedule():
    g_id = request.args.get("group_id")
    date_str = request.args.get("date")
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    loop = asyncio.new_event_loop()
    lessons = loop.run_until_complete(parser.get_schedule_for_date(g_id, target))
    return jsonify({"lessons": lessons})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        
        if "web_app_data" in msg:
            wa_data = json.loads(msg["web_app_data"]["data"])
            if wa_data["action"] == "set_group":
                send_tg("sendMessage", {
                    "chat_id": chat_id, 
                    "text": f"✅ Группа <b>{wa_data['group_name']}</b> выбрана!",
                    "parse_mode": "HTML"
                })
            return "ok"

        if msg.get("text") == "/start":
            send_tg("sendMessage", {
                "chat_id": chat_id,
                "text": "📅 Нажми кнопку ниже, чтобы открыть расписание:",
                "reply_markup": {
                    "inline_keyboard": [[{"text": "Открыть", "web_app": {"url": WEBAPP_URL}}]]
                }
            })
    return "ok"

if __name__ == "__main__":
    if WEBAPP_URL: requests.post(f"{API}/setWebhook", json={"url": f"{WEBAPP_URL}/webhook"})
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

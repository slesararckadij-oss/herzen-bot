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

# Хранилище групп пользователей: {chat_id: {group_id, group_name}}
user_groups = {}

def send_tg(method, payload):
    return requests.post(f"{API}/{method}", json=payload).json()

@app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@app.route("/api/groups")
def api_groups():
    # Используем asyncio.run для чистоты, если Flask не в асинхронном режиме
    groups = asyncio.run(parser.get_all_groups())
    return jsonify({"groups": groups})

@app.route("/api/schedule")
def api_schedule():
    g_id = request.args.get("group_id")
    date_str = request.args.get("date") # Формат YYYY-MM-DD
    
    if not g_id or not date_str:
        return jsonify({"error": "Missing params"}), 400

    logger.info(f"Запрос расписания для группы {g_id} на {date_str}")
    
    # Передаем date_str как строку, парсер сам её обработает
    lessons = asyncio.run(parser.get_schedule_for_date(str(g_id), date_str))
    
    return jsonify({"lessons": lessons})

@app.route("/api/user_group")
def api_user_group():
    chat_id = request.args.get("chat_id")
    if chat_id and chat_id in user_groups:
        return jsonify(user_groups[chat_id])
    return jsonify({})

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data: return "ok"
    
    if "message" in data:
        msg = data["message"]
        chat_id = str(msg["chat"]["id"])

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
                logger.error(f"WA Data error: {e}")
            return "ok"

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
    if WEBAPP_URL and BOT_TOKEN:
        # Устанавливаем вебхук при запуске
        res = requests.post(f"{API}/setWebhook", json={"url": f"{WEBAPP_URL}/webhook"})
        logger.info(f"Webhook set: {res.json()}")
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

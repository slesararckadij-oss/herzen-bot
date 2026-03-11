import os, json, logging, asyncio, requests
from flask import Flask, send_from_directory, request, jsonify
from parser import HerzenParser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEBAPP_URL")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__, static_folder="webapp")
parser = HerzenParser()
user_groups = {}

def send_tg(method, payload):
    try:
        return requests.post(f"{API}/{method}", json=payload).json()
    except: return {}

@app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@app.route("/api/groups")
def api_groups():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    groups = loop.run_until_complete(parser.get_all_groups())
    loop.close()
    return jsonify({"groups": groups})

@app.route("/api/schedule")
def api_schedule():
    g_id = request.args.get("group_id")
    date_str = request.args.get("date")
    if not g_id or not date_str:
        return jsonify({"error": "Missing params"}), 400
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    lessons = loop.run_until_complete(parser.get_schedule_for_date(str(g_id), date_str))
    loop.close()
    return jsonify({"lessons": lessons})

@app.route("/api/user_group")
def api_user_group():
    chat_id = request.args.get("chat_id")
    return jsonify(user_groups.get(chat_id, {}))

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data or "message" not in data: return "ok"
    
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
            logger.error(f"WA Error: {e}")
    
    elif msg.get("text") == "/start":
        send_tg("sendMessage", {
            "chat_id": chat_id,
            "text": "📅 Привет! Нажми кнопку ниже, чтобы открыть расписание:",
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
        requests.post(f"{API}/setWebhook", json={"url": f"{WEBAPP_URL}/webhook"})
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

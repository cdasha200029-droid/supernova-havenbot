import re
import logging
import requests
from flask import Flask, request, abort

app = Flask(name)
logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 5749770178
PUBLIC_URL = os.environ.get("PUBLIC_URL")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else ""

# Здесь бот хранит этап заполнения анкеты
user_steps = {}
processed_updates = set()


def send_message(chat_id, text):
    response = requests.post(
        f"{API}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=20
    )
    response.raise_for_status()
    return response.json()


def setup_webhook():
    if not TOKEN or not PUBLIC_URL or not WEBHOOK_SECRET:
        logging.warning("Не заданы переменные окружения для webhook.")
        return

    url = f"{PUBLIC_URL.rstrip('/')}/telegram/{WEBHOOK_SECRET}"

    try:
        response = requests.post(
            f"{API}/setWebhook",
            json={
                "url": url,
                "secret_token": WEBHOOK_SECRET
            },
            timeout=20
        )
        logging.info("Webhook: %s", response.text)
    except requests.RequestException as error:
        logging.error("Ошибка настройки webhook: %s", error)


@app.route("/")
def home():
    return "Бот работает!"


@app.route("/health")
def health():
    return "OK", 200


@app.route("/telegram/<secret>", methods=["POST"])
def telegram_webhook(secret):
    if not WEBHOOK_SECRET or secret != WEBHOOK_SECRET:
        abort(403)

    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)

    update = request.get_json(silent=True) or {}
    update_id = update.get("update_id")

    if update_id in processed_updates:
        return "OK", 200

    if update_id is not None:
        processed_updates.add(update_id)

    message = update.get("message")
    if not message:
        return "OK", 200

    chat_id = message["chat"]["id"]
    sender_id = message["from"]["id"]
    text = message.get("text", "")

    # Ответ администратора на анкету
    if sender_id == ADMIN_ID:
        reply = message.get("reply_to_message")

        if reply and reply.get("text"):
            match = re.search(r"ID пользователя: (\d+)", reply["text"])

            if match:
                target_id = int(match.group(1))
                try:
                    send_message(
                        target_id,
                        "Ответ администратора:\n\n" + text
                    )
                    send_message(ADMIN_ID, "Ответ отправлен пользователю.")
                except requests.RequestException:
                    send_message(ADMIN_ID, "Не удалось отправить ответ.")
        return "OK", 200

    # Начало заполнения анкеты
    if text.startswith("/start"):
        user_steps[sender_id] = {"step": "username"}
        send_message(
            chat_id,
            "Привет! Давай заполним анкету.\n\n"
            "1. Напиши свой Telegram Username (например, @username)."
        )
        return "OK", 200

    if sender_id not in user_steps:
        send_message(chat_id, "Чтобы начать заполнение анкеты, нажми /start.")
        return "OK", 200

    step = user_steps[sender_id]["step"]

    if step == "username":
        user_steps[sender_id]["username"] = text
        user_steps[sender_id]["step"] = "role"
        send_message(chat_id, "2. Напиши, какую роль ты хочешь получить.")
        return "OK", 200

    if step == "role":
        username = user_steps[sender_id]["username"]
        role = text

        first_name = message["from"].get("first_name", "Не указано")

        form_text = (
            "НОВАЯ АНКЕТА\n\n"
            f"Имя: {first_name}\n"
            f"Telegram Username: {username}\n"
            f"Желаемая роль: {role}\n\n"
            f"ID пользователя: {sender_id}\n\n"
            "Чтобы ответить, нажми Reply на это сообщение."
        )
 send_message(ADMIN_ID, form_text)
            send_message(chat_id, "Анкета отправлена! Ожидай ответа администратора.")
            del user_steps[sender_id]
        except requests.RequestException:
            send_message(chat_id, "Не удалось отправить анкету. Попробуй позже.")

        return "OK", 200

    return "OK", 200


if TOKEN and PUBLIC_URL and WEBHOOK_SECRET:
    setup_webhook()
else:
    logging.warning("Проверь настройки BOT_TOKEN, PUBLIC_URL и WEBHOOK_SECRET.")


if name == "main":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

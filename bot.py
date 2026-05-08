import os
import json
import threading
import urllib.parse
from flask import Flask, jsonify, request, send_from_directory
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import asyncio

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
PORT = int(os.environ.get("PORT", 8080))

SUBJECTS = [
    "Методы и средства проектирования ИС и Т",
    "Технологии Front-end разработки веб-приложений",
    "Современные операционные системы",
    "Администрирование баз данных",
]
SUBJECT_SHORT = ["МиСПИСиТ", "Front-end", "СОС", "АБД"]

queues: dict[str, list[dict]] = {s: [] for s in SUBJECTS}
lock = threading.Lock()


def save_state():
    with open("state.json", "w", encoding="utf-8") as f:
        json.dump(queues, f, ensure_ascii=False, indent=2)


def load_state():
    global queues
    if os.path.exists("state.json"):
        with open("state.json", encoding="utf-8") as f:
            data = json.load(f)
        for s in SUBJECTS:
            queues[s] = data.get(s, [])


# ── FLASK ──────────────────────────────────────────────────────────────────

flask_app = Flask(__name__, static_folder="webapp")


@flask_app.route("/")
def index():
    return send_from_directory("webapp", "index.html")


@flask_app.route("/api/queues")
def api_queues():
    with lock:
        data = {str(i): queues[s] for i, s in enumerate(SUBJECTS)}
    return jsonify(data)


@flask_app.route("/api/action", methods=["POST"])
def api_action():
    body = request.get_json(force=True)
    action = body.get("action")
    idx = int(body.get("idx", 0))
    user_id = int(body.get("user_id", 0))
    user_name = body.get("user_name", "Аноним")
    username = body.get("username") or None

    if not user_id:
        return jsonify({"ok": False, "error": "no user_id"}), 400

    subject = SUBJECTS[idx]

    with lock:
        q = queues[subject]

        if action == "join":
            if any(u["id"] == user_id for u in q):
                return jsonify({"ok": False, "error": "already_in"})
            q.append({"id": user_id, "name": user_name, "username": username})
            save_state()
            return jsonify({"ok": True, "pos": len(q)})

        elif action == "leave":
            idx_user = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
            if idx_user is None:
                return jsonify({"ok": False, "error": "not_in"})
            q.pop(idx_user)
            save_state()
            return jsonify({"ok": True})

        elif action == "skip":
            idx_user = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
            if idx_user is None:
                return jsonify({"ok": False, "error": "not_in"})
            if idx_user + 1 >= len(q):
                return jsonify({"ok": False, "error": "last"})
            q[idx_user], q[idx_user + 1] = q[idx_user + 1], q[idx_user]
            save_state()
            return jsonify({"ok": True, "pos": idx_user + 2})

    return jsonify({"ok": False, "error": "unknown_action"}), 400


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False)


# ── TELEGRAM BOT ───────────────────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for i, short in enumerate(SUBJECT_SHORT):
        buttons.append([InlineKeyboardButton(f"📚 {short}", callback_data=f"subj:{i}")])
    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton(
            "🌐 Открыть веб-очередь",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )])
    return InlineKeyboardMarkup(buttons)


def queue_text(idx: int) -> str:
    subject = SUBJECTS[idx]
    q = queues[subject]
    if not q:
        return f"📋 <b>{subject}</b>\n\nОчередь пуста."
    lines = [f"📋 <b>{subject}</b>\n"]
    for i, u in enumerate(q, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        lines.append(f"{medal} {u['name']}")
    return "\n".join(lines)


def subject_keyboard(idx: int, user_id: int) -> InlineKeyboardMarkup:
    subject = SUBJECTS[idx]
    q = queues[subject]
    in_queue = any(u["id"] == user_id for u in q)
    buttons = []
    if not in_queue:
        buttons.append([InlineKeyboardButton("✅ Встать в очередь", callback_data=f"join:{idx}")])
    else:
        pos = next(i + 1 for i, u in enumerate(q) if u["id"] == user_id)
        buttons.append([InlineKeyboardButton(f"⏭ Пропустить ход (поз. {pos})", callback_data=f"skip:{idx}")])
        buttons.append([InlineKeyboardButton("❌ Выйти из очереди", callback_data=f"leave:{idx}")])
    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton("🌐 Веб-просмотр", web_app=WebAppInfo(url=WEBAPP_URL))])
    buttons.append([InlineKeyboardButton("🔄 Обновить", callback_data=f"ref:{idx}")])
    buttons.append([InlineKeyboardButton("« Назад", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Очередь ИСТ-321</b>\n\nВыбери предмет или открой веб-приложение:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 Выбери предмет:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    user_name = query.from_user.full_name or query.from_user.username or str(user_id)
    username = query.from_user.username

    if data == "menu":
        await query.edit_message_text(
            "📚 Выбери предмет:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    action, idx_str = data.split(":")
    idx = int(idx_str)
    subject = SUBJECTS[idx]

    if action in ("subj", "ref"):
        await query.edit_message_text(
            queue_text(idx),
            parse_mode="HTML",
            reply_markup=subject_keyboard(idx, user_id),
        )
        return

    with lock:
        q = queues[subject]

        if action == "join":
            if any(u["id"] == user_id for u in q):
                await query.answer("Ты уже в очереди!", show_alert=True)
                return
            q.append({"id": user_id, "name": user_name, "username": username})
            save_state()
            pos = len(q)
            await query.edit_message_text(
                queue_text(idx) + f"\n\n✅ Ты добавлен на позицию <b>{pos}</b>",
                parse_mode="HTML",
                reply_markup=subject_keyboard(idx, user_id),
            )
            if pos > 1:
                prev = q[pos - 2]
                try:
                    await context.bot.send_message(
                        chat_id=prev["id"],
                        text=f"ℹ️ <b>{subject}</b>\nПосле тебя встал <b>{user_name}</b>.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            return

        if action == "skip":
            idx_user = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
            if idx_user is None:
                await query.answer("Тебя нет в очереди.", show_alert=True)
                return
            if idx_user + 1 >= len(q):
                await query.answer("Ты последний — пропускать некого.", show_alert=True)
                return
            q[idx_user], q[idx_user + 1] = q[idx_user + 1], q[idx_user]
            save_state()
            moved_up = q[idx_user]
            try:
                await context.bot.send_message(
                    chat_id=moved_up["id"],
                    text=f"🔔 <b>{subject}</b>\n<b>{user_name}</b> пропустил ход — ты поднялся!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            await query.edit_message_text(
                queue_text(idx) + f"\n\n⏭ Ты на позиции <b>{idx_user + 2}</b>",
                parse_mode="HTML",
                reply_markup=subject_keyboard(idx, user_id),
            )
            return

        if action == "leave":
            idx_user = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
            if idx_user is None:
                await query.answer("Тебя нет в очереди.", show_alert=True)
                return
            q.pop(idx_user)
            save_state()
            if idx_user == 0 and len(q) > 0:
                try:
                    await context.bot.send_message(
                        chat_id=q[0]["id"],
                        text=f"🔔 <b>{subject}</b>\nТы теперь <b>первый</b>!",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            await query.edit_message_text(
                queue_text(idx) + "\n\n❌ Ты вышел из очереди.",
                parse_mode="HTML",
                reply_markup=subject_keyboard(idx, user_id),
            )
            return


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("queue", "Посмотреть очереди"),
    ])


def main():
    load_state()

    # Flask в отдельном потоке
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    # Telegram bot
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

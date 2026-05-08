import os
import json
import urllib.parse
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    BotCommand,
    MenuButtonWebApp,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")

SUBJECTS = [
    "Методы и средства проектирования ИС и Т",
    "Технологии Front-end разработки веб-приложений",
    "Современные операционные системы",
    "Администрирование баз данных",
]

SUBJECT_SHORT = ["МиСПИСиТ", "Front-end", "СОС", "АБД"]

queues: dict[str, list[dict]] = {s: [] for s in SUBJECTS}


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


def build_webapp_url() -> str:
    """Передаём данные очередей в Mini App через URL-параметр."""
    # Формат: {0: [...], 1: [...], 2: [...], 3: [...]}
    data = {str(i): queues[s] for i, s in enumerate(SUBJECTS)}
    encoded = urllib.parse.quote(json.dumps(data, ensure_ascii=False))
    return f"{WEBAPP_URL}?data={encoded}"


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


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    for i, short in enumerate(SUBJECT_SHORT):
        buttons.append([InlineKeyboardButton(f"📚 {short}", callback_data=f"subj:{i}")])
    if WEBAPP_URL:
        buttons.append([InlineKeyboardButton(
            "🌐 Открыть веб-очередь",
            web_app=WebAppInfo(url=build_webapp_url())
        )])
    return InlineKeyboardMarkup(buttons)


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
        buttons.append([InlineKeyboardButton(
            "🌐 Веб-просмотр",
            web_app=WebAppInfo(url=build_webapp_url())
        )])
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


async def webapp_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает действия из Mini App."""
    data = json.loads(update.effective_message.web_app_data.data)
    action = data.get("action")
    idx = data.get("idx", 0)
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name or update.effective_user.username or str(user_id)
    username = update.effective_user.username

    subject = SUBJECTS[idx]
    q = queues[subject]

    if action == "join":
        if not any(u["id"] == user_id for u in q):
            q.append({"id": user_id, "name": user_name, "username": username})
            save_state()
            pos = len(q)
            await update.message.reply_text(
                f"✅ Ты добавлен в очередь <b>{SUBJECT_SHORT[idx]}</b> на позицию <b>{pos}</b>",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
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
        else:
            await update.message.reply_text("Ты уже в этой очереди.", reply_markup=main_menu_keyboard())

    elif action == "leave":
        idx_user = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
        if idx_user is not None:
            q.pop(idx_user)
            save_state()
            await update.message.reply_text(
                f"❌ Ты вышел из очереди <b>{SUBJECT_SHORT[idx]}</b>",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
            if idx_user == 0 and len(q) > 0:
                try:
                    await context.bot.send_message(
                        chat_id=q[0]["id"],
                        text=f"🔔 <b>{subject}</b>\nТы теперь <b>первый</b>!",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    elif action == "skip":
        idx_user = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
        if idx_user is not None and idx_user + 1 < len(q):
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
            await update.message.reply_text(
                f"⏭ Ты переместился на позицию <b>{idx_user + 2}</b>",
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )

    elif action == "refresh":
        await update.message.reply_text(
            "🔄 Данные обновлены. Открой приложение заново:",
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

    if action == "join":
        q = queues[subject]
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
        q = queues[subject]
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
            queue_text(idx) + f"\n\n⏭ Ты переместился на позицию <b>{idx_user + 2}</b>",
            parse_mode="HTML",
            reply_markup=subject_keyboard(idx, user_id),
        )
        return

    if action == "leave":
        q = queues[subject]
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
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

import os
import json
import asyncio
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

TOKEN = os.environ.get("BOT_TOKEN", "")

SUBJECTS = [
    "Методы и средства проектирования ИС и Т",
    "Технологии Front-end разработки веб-приложений",
    "Современные операционные системы",
    "Администрирование баз данных",
]

SUBJECT_SHORT = {
    "Методы и средства проектирования ИС и Т": "МиСПИСиТ",
    "Технологии Front-end разработки веб-приложений": "Front-end",
    "Современные операционные системы": "СОС",
    "Администрирование баз данных": "АБД",
}

# queues: {subject_name: [{"id": user_id, "name": str}, ...]}
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


def get_user_name(update: Update) -> str:
    user = update.effective_user
    name = user.full_name or user.username or str(user.id)
    return name


def queue_text(subject: str) -> str:
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
    for s in SUBJECTS:
        short = SUBJECT_SHORT[s]
        buttons.append([InlineKeyboardButton(f"📚 {short}", callback_data=f"subj|{s}")])
    return InlineKeyboardMarkup(buttons)


def subject_keyboard(subject: str, user_id: int) -> InlineKeyboardMarkup:
    q = queues[subject]
    in_queue = any(u["id"] == user_id for u in q)
    buttons = []
    if not in_queue:
        buttons.append([InlineKeyboardButton("✅ Встать в очередь", callback_data=f"join|{subject}")])
    else:
        pos = next(i + 1 for i, u in enumerate(q) if u["id"] == user_id)
        buttons.append([InlineKeyboardButton(f"⏭ Пропустить ход (позиция {pos})", callback_data=f"skip|{subject}")])
        buttons.append([InlineKeyboardButton("❌ Выйти из очереди", callback_data=f"leave|{subject}")])
    buttons.append([InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh|{subject}")])
    buttons.append([InlineKeyboardButton("« Назад", callback_data="menu")])
    return InlineKeyboardMarkup(buttons)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Бот управления очередью</b>\n\nВыбери предмет:",
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

    if data == "menu":
        await query.edit_message_text(
            "📚 Выбери предмет:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    action, subject = data.split("|", 1)

    if action == "subj" or action == "refresh":
        await query.edit_message_text(
            queue_text(subject),
            parse_mode="HTML",
            reply_markup=subject_keyboard(subject, user_id),
        )
        return

    if action == "join":
        q = queues[subject]
        if any(u["id"] == user_id for u in q):
            await query.answer("Ты уже в очереди!", show_alert=True)
            return
        q.append({"id": user_id, "name": user_name})
        save_state()
        pos = len(q)
        await query.edit_message_text(
            queue_text(subject) + f"\n\n✅ Ты добавлен на позицию <b>{pos}</b>",
            parse_mode="HTML",
            reply_markup=subject_keyboard(subject, user_id),
        )
        # уведомление тому, кто стоит перед новым участником
        if pos > 1:
            prev = q[pos - 2]
            try:
                await context.bot.send_message(
                    chat_id=prev["id"],
                    text=f"ℹ️ <b>{subject}</b>\nПосле тебя встал <b>{user_name}</b> (позиция {pos}).",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        return

    if action == "skip":
        q = queues[subject]
        idx = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
        if idx is None:
            await query.answer("Тебя нет в очереди.", show_alert=True)
            return
        if idx + 1 >= len(q):
            await query.answer("Ты последний — пропускать некого.", show_alert=True)
            return
        # меняем местами с следующим
        q[idx], q[idx + 1] = q[idx + 1], q[idx]
        save_state()
        new_pos = idx + 2
        # уведомляем того, кто занял освободившееся место
        moved_up = q[idx]
        try:
            await context.bot.send_message(
                chat_id=moved_up["id"],
                text=f"🔔 <b>{subject}</b>\n<b>{user_name}</b> пропустил ход — ты поднялся на позицию <b>{idx + 1}</b>!",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await query.edit_message_text(
            queue_text(subject) + f"\n\n⏭ Ты переместился на позицию <b>{new_pos}</b>",
            parse_mode="HTML",
            reply_markup=subject_keyboard(subject, user_id),
        )
        return

    if action == "leave":
        q = queues[subject]
        idx = next((i for i, u in enumerate(q) if u["id"] == user_id), None)
        if idx is None:
            await query.answer("Тебя нет в очереди.", show_alert=True)
            return
        q.pop(idx)
        save_state()
        # уведомляем нового первого, если он сдвинулся
        if idx == 0 and len(q) > 0:
            try:
                await context.bot.send_message(
                    chat_id=q[0]["id"],
                    text=f"🔔 <b>{subject}</b>\nТы теперь <b>первый</b> в очереди!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await query.edit_message_text(
            queue_text(subject) + "\n\n❌ Ты вышел из очереди.",
            parse_mode="HTML",
            reply_markup=subject_keyboard(subject, user_id),
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
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

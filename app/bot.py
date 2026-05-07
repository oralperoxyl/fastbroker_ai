import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import load_settings
from app.memory import ConversationMemory
from app.obsidian import ObsidianVault
from app.openai_client import OpenAIResponder


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


TASKS = {
    "analyze": {
        "title": "Анализ объявления",
        "button": "🔍 Анализ объявления",
        "prompt": (
            "Ты AI-ассистент брокера по недвижимости. Проанализируй объявление или описание объекта. "
            "Верни структурированный ответ: 1) кратко объект, 2) вероятный тип продавца, "
            "3) мотивация и сигналы срочности, 4) риски и красные флаги, "
            "5) вопросы продавцу, 6) стратегия первого контакта, 7) стоит ли брать в работу. "
            "Пиши конкретно, без воды."
        ),
    },
    "reply": {
        "title": "Ответ продавцу",
        "button": "✍️ Ответить продавцу",
        "prompt": (
            "Ты помогаешь брокеру ответить продавцу в переписке. Сформулируй 2-3 варианта ответа: "
            "мягкий, более деловой и ведущий к встрече. Не дави, не звучи как массовая рассылка. "
            "Цель: продолжить диалог, выявить мотивацию и приблизить встречу."
        ),
    },
    "meeting": {
        "title": "Подвод к встрече",
        "button": "🤝 Назначить встречу",
        "prompt": (
            "Ты помогаешь брокеру назначить встречу с продавцом. Проанализируй контекст переписки "
            "и дай: 1) лучший следующий ход, 2) точный текст сообщения, 3) запасной вариант, "
            "4) что спросить перед встречей. Цель: встреча без давления."
        ),
    },
    "leadplan": {
        "title": "План по лиду",
        "button": "📋 План по лиду",
        "prompt": (
            "Ты sales-стратег брокера по недвижимости. На основе лида дай рабочий план: "
            "1) статус лида, 2) шанс на встречу, 3) ключевой рычаг мотивации, "
            "4) следующий шаг, 5) follow-up, 6) что записать в CRM, 7) риск потери лида."
        ),
    },
}


def main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(TASKS["analyze"]["button"], callback_data="task:analyze")],
        [InlineKeyboardButton(TASKS["reply"]["button"], callback_data="task:reply")],
        [InlineKeyboardButton(TASKS["meeting"]["button"], callback_data="task:meeting")],
        [InlineKeyboardButton(TASKS["leadplan"]["button"], callback_data="task:leadplan")],
        [InlineKeyboardButton("🗑 Очистить память", callback_data="task:reset")],
    ]
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я AI-ассистент брокера по недвижимости.\n\n"
        "Выбери что нужно сделать — или просто напиши мне сообщение:",
        reply_markup=main_keyboard(),
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    memory: ConversationMemory = context.application.bot_data["memory"]
    memory.clear(update.effective_chat.id)
    await update.message.reply_text("Память очищена.", reply_markup=main_keyboard())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "task:reset":
        memory: ConversationMemory = context.application.bot_data["memory"]
        memory.clear(update.effective_chat.id)
        await query.edit_message_text("Память очищена.", reply_markup=main_keyboard())
        return

    task_name = data.replace("task:", "")
    if task_name not in TASKS:
        return

    pending_tasks = context.application.bot_data["pending_tasks"]
    pending_tasks[update.effective_chat.id] = task_name
    await query.edit_message_text(
        f"Режим: *{TASKS[task_name]['title']}*\n\nПришли текст объявления, переписку или описание лида — и я разберу.",
        parse_mode="Markdown",
    )


async def obsidian_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    vault: ObsidianVault = context.application.bot_data["obsidian"]
    if not vault.is_enabled():
        await update.message.reply_text("Obsidian не подключен или папка не найдена.")
        return

    note_count = len(list(vault.vault_path.rglob("*.md")))
    await update.message.reply_text(f"Obsidian подключен. Найдено заметок: {note_count}.")


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    command = update.message.text.split(maxsplit=1)[0].lstrip("/").split("@")[0]
    text = update.message.text.split(maxsplit=1)[1].strip() if len(update.message.text.split(maxsplit=1)) > 1 else ""

    if text:
        await run_task(update, context, command, text)
        return

    pending_tasks = context.application.bot_data["pending_tasks"]
    pending_tasks[update.effective_chat.id] = command
    await update.message.reply_text(
        f"Ок, режим: {TASKS[command]['title']}.\n"
        "Пришлите следующим сообщением текст объявления, переписку или описание лида."
    )


async def run_task(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_name: str,
    user_text: str,
) -> None:
    chat_id = update.effective_chat.id
    memory: ConversationMemory = context.application.bot_data["memory"]
    responder: OpenAIResponder = context.application.bot_data["responder"]
    vault: ObsidianVault = context.application.bot_data["obsidian"]
    task = TASKS[task_name]

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except TelegramError:
        logging.warning("Could not send typing action", exc_info=True)

    try:
        obsidian_context = vault.build_context(user_text)
        answer = await responder.answer(
            memory.get(chat_id),
            user_text,
            obsidian_context,
            task["prompt"],
        )
    except Exception:
        logging.exception("AI task failed")
        await update.message.reply_text("Не получилось обработать задачу через AI. Попробуйте ещё раз.")
        return

    memory.add(chat_id, "user", f"/{task_name}\n{user_text}")
    memory.add(chat_id, "assistant", answer)
    await update.message.reply_text(answer, reply_markup=main_keyboard())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text.strip()
    memory: ConversationMemory = context.application.bot_data["memory"]
    responder: OpenAIResponder = context.application.bot_data["responder"]
    vault: ObsidianVault = context.application.bot_data["obsidian"]
    pending_tasks = context.application.bot_data["pending_tasks"]

    pending_task = pending_tasks.pop(chat_id, None)
    if pending_task:
        await run_task(update, context, pending_task, user_text)
        return

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except TelegramError:
        logging.warning("Could not send typing action", exc_info=True)

    try:
        obsidian_context = vault.build_context(user_text)
        answer = await responder.answer(memory.get(chat_id), user_text, obsidian_context)
    except Exception:
        logging.exception("AI request failed")
        await update.message.reply_text(
            "Не получилось получить ответ от AI. Проверьте ключ OpenAI и попробуйте еще раз."
        )
        return

    memory.add(chat_id, "user", user_text)
    memory.add(chat_id, "assistant", answer)
    await update.message.reply_text(answer, reply_markup=main_keyboard())


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Unhandled bot error", exc_info=context.error)


def run_bot() -> None:
    settings = load_settings()
    memory = ConversationMemory(f"{settings.data_dir}/memory.json", settings.max_history_messages)
    responder = OpenAIResponder(settings.openai_api_key, settings.openai_model)
    vault = ObsidianVault(settings.obsidian_vault_path)

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["memory"] = memory
    application.bot_data["responder"] = responder
    application.bot_data["obsidian"] = vault
    application.bot_data["pending_tasks"] = {}

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("obsidian", obsidian_status))
    for command in TASKS:
        application.add_handler(CommandHandler(command, task_command))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern="^task:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(handle_error)

    print("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

import datetime
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import load_settings
from app.memory import ConversationMemory
from app.obsidian import ObsidianVault
from app.openai_client import OpenAIResponder
from app.poster import ChannelPoster, MOSCOW_TZ


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


TASKS = {
    "seller": {
        "title": "Новый продавец",
        "button": "👤 Новый продавец",
        "prompt": (
            "Брокер даёт тебе вводные по продавцу и его ситуации. Твоя задача — провести глубокий анализ "
            "и выстроить стратегию работы. Структура ответа:\n\n"
            "1. ПСИХОЛОГИЧЕСКИЙ ПОРТРЕТ — кто этот человек, что им движет, какой у него тип принятия решений\n"
            "2. РЕАЛЬНАЯ МОТИВАЦИЯ — что он говорит vs что происходит на самом деле\n"
            "3. БОЛЕВЫЕ ТОЧКИ — страхи, сомнения, возражения которые будут\n"
            "4. РЫЧАГИ ВЛИЯНИЯ — что реально сдвинет его с места\n"
            "5. СТРАТЕГИЯ — как вести себя с этим конкретным человеком, какой подход работает\n"
            "6. ПЕРВЫЙ ШАГ — точное действие прямо сейчас с формулировкой\n"
            "7. КРАСНЫЕ ФЛАГИ — что может пойти не так и как это предотвратить\n"
            "8. CRM — статус, следующее касание, что зафиксировать\n\n"
            "Думай как опытный переговорщик, не как консультант. Конкретика, без воды."
        ),
    },
    "analyze": {
        "title": "Анализ объявления",
        "button": "🔍 Анализ объявления",
        "prompt": (
            "Брокер присылает текст объявления о продаже недвижимости. Проведи профессиональный разбор:\n\n"
            "1. ОБЪЕКТ — что продаётся, ключевые характеристики\n"
            "2. ПРОДАВЕЦ — кто скорее всего продаёт (собственник/инвестор/наследник/разводящиеся и т.д.) "
            "и почему ты так думаешь\n"
            "3. РЕАЛЬНАЯ МОТИВАЦИЯ — читай между строк: срочность, финансовое давление, эмоции\n"
            "4. ЦЕНА — адекватна ли, есть ли пространство для торга и сколько\n"
            "5. КРАСНЫЕ ФЛАГИ — юридические риски, скрытые проблемы, тревожные сигналы\n"
            "6. ПЕРВЫЙ КОНТАКТ — точный текст первого сообщения продавцу\n"
            "7. ВОПРОСЫ — 3-4 вопроса которые нужно задать при первом разговоре\n"
            "8. ВЕРДИКТ — брать в работу или нет, и почему\n\n"
            "Пиши как эксперт который видел тысячи таких объявлений."
        ),
    },
    "reply": {
        "title": "Ответ продавцу",
        "button": "✍️ Ответить продавцу",
        "prompt": (
            "Брокер присылает переписку с продавцом или его последнее сообщение. "
            "Твоя задача — разобрать ситуацию и дать конкретные варианты ответа.\n\n"
            "1. АНАЛИЗ СООБЩЕНИЯ — что продавец реально говорит/чувствует/хочет\n"
            "2. ВАРИАНТЫ ОТВЕТА — дай 2-3 варианта под разные тактики:\n"
            "   — мягкий (выстраивание доверия)\n"
            "   — деловой (ведущий к конкретному шагу)\n"
            "   — по Кэмпу (позиция 'ок, не нужно' — создаёт дефицит интереса)\n"
            "3. РЕКОМЕНДАЦИЯ — какой вариант использовать и почему\n"
            "4. ЧЕГО НЕ ДЕЛАТЬ — типичные ошибки в этой ситуации\n\n"
            "Тексты должны звучать по-человечески, не как скрипт."
        ),
    },
    "meeting": {
        "title": "Подвод к встрече",
        "button": "🤝 Назначить встречу",
        "prompt": (
            "Брокер хочет назначить встречу с продавцом. Дай конкретный план:\n\n"
            "1. ОЦЕНКА ГОТОВНОСТИ — насколько продавец готов к встрече прямо сейчас (1-10) и почему\n"
            "2. ЛУЧШИЙ МОМЕНТ — когда и как предложить встречу в этой конкретной ситуации\n"
            "3. ТОЧНЫЙ ТЕКСТ — сообщение для назначения встречи (звучит как предложение, не как просьба)\n"
            "4. ЗАПАСНОЙ ВАРИАНТ — если откажет или уйдёт в молчание\n"
            "5. ПОДГОТОВКА — что узнать/сделать до встречи\n"
            "6. ЦЕЛЬ ВСТРЕЧИ — что конкретно должно произойти на встрече, критерий успеха\n\n"
            "Применяй принцип: встреча продаётся легче чем сделка."
        ),
    },
    "leadplan": {
        "title": "План по лиду",
        "button": "📋 План по лиду",
        "prompt": (
            "Брокер описывает лида. Составь полный рабочий план:\n\n"
            "1. СТАТУС ЛИДА — горячий/тёплый/холодный и обоснование\n"
            "2. ВЕРОЯТНОСТЬ СДЕЛКИ — процент и от чего зависит\n"
            "3. ГЛАВНЫЙ РЫЧАГ — одна ключевая вещь которая решает всё в этом кейсе\n"
            "4. СТРАТЕГИЯ — общий подход к работе с этим лидом\n"
            "5. СЛЕДУЮЩИЙ ШАГ — конкретное действие в ближайшие 24 часа\n"
            "6. ПЛАН КАСАНИЙ — когда и как касаться дальше (даты и форматы)\n"
            "7. РИСК ПОТЕРИ — главная угроза и как её нейтрализовать\n"
            "8. CRM — что записать: статус, следующая дата касания, ключевые факты о продавце\n\n"
            "Думай как тренер по продажам который разбирает кейс с брокером."
        ),
    },
}


def main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(TASKS["seller"]["button"], callback_data="task:seller")],
        [InlineKeyboardButton(TASKS["analyze"]["button"], callback_data="task:analyze")],
        [InlineKeyboardButton(TASKS["reply"]["button"], callback_data="task:reply")],
        [InlineKeyboardButton(TASKS["meeting"]["button"], callback_data="task:meeting")],
        [InlineKeyboardButton(TASKS["leadplan"]["button"], callback_data="task:leadplan")],
        [InlineKeyboardButton("✏️ Пост в канал", callback_data="task:post"),
         InlineKeyboardButton("📬 Очередь постов", callback_data="task:queue")],
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

    if data.startswith("cancel_post:"):
        job_id = data.replace("cancel_post:", "")
        scheduler: AsyncIOScheduler = context.application.bot_data["scheduler"]
        job = scheduler.get_job(job_id)
        if job:
            run_date = job.next_run_time.astimezone(MOSCOW_TZ).strftime("%d.%m в %H:%M")
            job.remove()
            await query.edit_message_text(f"✅ Пост на {run_date} отменён.", reply_markup=main_keyboard())
        else:
            await query.edit_message_text("Пост уже отправлен или не найден.", reply_markup=main_keyboard())
        return

    if data == "task:menu":
        await query.edit_message_text(
            "Выбери что нужно сделать:",
            reply_markup=main_keyboard(),
        )
        return

    if data == "task:queue":
        scheduler: AsyncIOScheduler = context.application.bot_data["scheduler"]
        jobs = scheduler.get_jobs()
        if not jobs:
            await query.edit_message_text("Очередь пустая — нет запланированных постов.", reply_markup=main_keyboard())
            return
        lines = []
        buttons = []
        for job in jobs:
            if job.next_run_time:
                label = job.next_run_time.astimezone(MOSCOW_TZ).strftime("%d.%m в %H:%M")
                preview = str(job.args[0])[:60].replace("\n", " ")
                if len(str(job.args[0])) > 60:
                    preview += "..."
                lines.append(f"📅 *{label}*\n_{preview}_")
                buttons.append([InlineKeyboardButton(f"❌ Отменить {label}", callback_data=f"cancel_post:{job.id}")])
        buttons.append([InlineKeyboardButton("« Назад", callback_data="task:menu")])
        await query.edit_message_text(
            "Запланированные посты:\n\n" + "\n\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    if data == "task:post":
        pending_tasks = context.application.bot_data["pending_tasks"]
        pending_tasks[update.effective_chat.id] = "post"
        await query.edit_message_text(
            "✏️ *Пост в канал*\n\n"
            "Напиши тему поста. Можно сразу указать время:\n\n"
            "_Примеры:_\n"
            "• `про продавца который 2 года не может продать`\n"
            "• `завтра 10:00 | про покупателей которые смотрят 50 квартир`\n"
            "• `в пятницу вечером | про торг`\n"
            "• `через 3 дня | наблюдение про тишину после показа`",
            parse_mode="Markdown",
        )
        return

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
    if pending_task == "post":
        await _generate_and_schedule_post(update, context, user_text)
        return
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
    await update.message.reply_text(answer)


async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = update.message.text.split(maxsplit=1)
    user_input = text[1].strip() if len(text) > 1 else ""

    if not user_input:
        pending_tasks = context.application.bot_data["pending_tasks"]
        pending_tasks[update.effective_chat.id] = "post"
        await update.message.reply_text(
            "✏️ *Пост в канал*\n\n"
            "Напиши тему поста. Можно сразу указать время:\n\n"
            "_Примеры:_\n"
            "• `про продавца который 2 года не может продать`\n"
            "• `завтра 10:00 | про покупателей которые смотрят 50 квартир`\n"
            "• `в пятницу вечером | про торг`\n"
            "• `через 3 дня | наблюдение про тишину после показа`\n\n"
            "Если время не указать — запланирую через 3 дня в 10:00.",
            parse_mode="Markdown",
        )
        return

    await _generate_and_schedule_post(update, context, user_input)


async def _generate_and_schedule_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_input: str,
) -> None:
    poster: ChannelPoster = context.application.bot_data["poster"]
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        schedule_dt = await poster.parse_schedule_time(user_input)
        if not schedule_dt:
            schedule_dt = poster.default_schedule_time()

        topic = poster.extract_topic(user_input)
        post_text = await poster.generate_post(topic)
    except Exception:
        logging.exception("Post generation failed")
        await update.message.reply_text("Не получилось сгенерировать пост. Попробуй ещё раз.")
        return

    try:
        scheduler: AsyncIOScheduler = context.application.bot_data["scheduler"]
        scheduler.add_job(
            poster.send_to_channel,
            trigger="date",
            run_date=schedule_dt,
            args=[post_text],
            misfire_grace_time=3600,
        )
        logging.info("Post scheduled for %s", schedule_dt)
    except Exception as e:
        logging.exception("Failed to schedule post")
        await update.message.reply_text(f"⚠️ Не удалось запланировать: {e}")
        return

    label = poster.format_schedule_label(schedule_dt)
    await update.message.reply_text(
        f"✅ Запланировано на *{label}*\n\n"
        f"{post_text}\n\n"
        f"_Найдёшь в отложенных канала._",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    scheduler: AsyncIOScheduler = context.application.bot_data["scheduler"]
    jobs = scheduler.get_jobs()

    if not jobs:
        await update.message.reply_text("Очередь пустая — нет запланированных постов.", reply_markup=main_keyboard())
        return

    lines = []
    buttons = []
    for job in jobs:
        run_date = job.next_run_time
        if run_date:
            label = run_date.astimezone(MOSCOW_TZ).strftime("%d.%m в %H:%M")
            # Первые 60 символов текста поста
            preview = str(job.args[0])[:60].replace("\n", " ") + "..." if len(str(job.args[0])) > 60 else str(job.args[0])
            lines.append(f"📅 *{label}*\n_{preview}_")
            buttons.append([InlineKeyboardButton(f"❌ Отменить {label}", callback_data=f"cancel_post:{job.id}")])

    buttons.append([InlineKeyboardButton("« Назад", callback_data="task:menu")])
    text = "Запланированные посты:\n\n" + "\n\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Unhandled bot error", exc_info=context.error)


def run_bot() -> None:
    settings = load_settings()
    memory = ConversationMemory(f"{settings.data_dir}/memory.json", settings.max_history_messages)
    responder = OpenAIResponder(settings.openai_api_key, settings.openai_model)
    vault = ObsidianVault(settings.obsidian_vault_path)
    poster = ChannelPoster(settings.openai_api_key, settings.openai_model, settings.channel_id, settings.telegram_bot_token, settings.post_interval_days)

    scheduler = AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=MOSCOW_TZ,
    )
    scheduler.start()

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["memory"] = memory
    application.bot_data["responder"] = responder
    application.bot_data["obsidian"] = vault
    application.bot_data["poster"] = poster
    application.bot_data["scheduler"] = scheduler
    application.bot_data["pending_tasks"] = {}

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("post", post_command))
    application.add_handler(CommandHandler("queue", queue_command))
    for command in TASKS:
        application.add_handler(CommandHandler(command, task_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(handle_error)

    print("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

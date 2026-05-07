import datetime
import json
import re
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

CHANNEL_STYLE_PROMPT = """Ты пишешь пост для Telegram-канала "между показами".

ГОЛОС КАНАЛА:
Автор — брокер по недвижимости. Пишет о людях, решениях, рынке. Говорит как человек, \
не как эксперт с трибуны. Наблюдает без осуждения. Видит за цифрами — людей.

СТИЛЬ:
- Живые истории и наблюдения из практики
- Созерцательный тон с лёгкой иронией и сухим юмором
- Контраст между тем что говорят люди и тем что происходит на самом деле
- Никаких мотивационных клише, воды, призывов "подписывайтесь"
- Минимум эмодзи — только если органично вписываются
- Чистые абзацы, воздух между мыслями
- Заканчивать наблюдением или вопросом — не призывом к действию

ФОРМАТЫ (выбирай сам под тему):
— Короткое наблюдение (3-8 строк): мысль, парадокс, инсайт
— История с рынка (15-30 строк): случай + вывод
— Разбор ситуации (30-50 строк): детали + контекст + мысль

Пиши в первом лице. Пост должен вызывать мысль — не продавать и не учить."""

TIME_PARSE_PROMPT = """Извлеки из сообщения брокера дату и время для публикации поста.
Сегодня: {today} (московское время).

Если явно указано время/дата — верни его.
Если не указано — верни null.

Формат ответа — только JSON:
{{"schedule": "YYYY-MM-DD HH:MM" или null}}

Примеры:
"завтра 10:00 про продавца..." → {{"schedule": "2024-05-08 10:00"}}
"в пятницу вечером | текст" → {{"schedule": "2024-05-10 19:00"}}
"через 3 дня текст" → {{"schedule": "2024-05-10 10:00"}}
"просто напиши пост про..." → {{"schedule": null}}"""

POST_GEN_PROMPT = """Напиши пост для канала на тему: {topic}

{style_prompt}

Верни только текст поста, без пояснений и комментариев."""


class ChannelPoster:
    def __init__(self, api_key: str, model: str, channel_id: int, interval_days: int = 3) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.channel_id = channel_id
        self.interval_days = interval_days

    async def parse_schedule_time(self, user_text: str) -> datetime.datetime | None:
        now_moscow = datetime.datetime.now(MOSCOW_TZ)
        today_str = now_moscow.strftime("%Y-%m-%d %H:%M (%A)")

        resp = await self.client.responses.create(
            model=self.model,
            input=[{
                "role": "user",
                "content": TIME_PARSE_PROMPT.format(today=today_str) + f"\n\nСообщение: {user_text}"
            }],
        )

        text = resp.output_text.strip()
        json_match = re.search(r'\{.*?\}', text, re.DOTALL)
        if not json_match:
            return None

        try:
            data = json.loads(json_match.group())
            schedule_str = data.get("schedule")
            if not schedule_str:
                return None
            dt = datetime.datetime.strptime(schedule_str, "%Y-%m-%d %H:%M")
            return dt.replace(tzinfo=MOSCOW_TZ)
        except (json.JSONDecodeError, ValueError):
            return None

    def default_schedule_time(self, last_scheduled: datetime.datetime | None = None) -> datetime.datetime:
        now = datetime.datetime.now(MOSCOW_TZ)
        base = last_scheduled if last_scheduled and last_scheduled > now else now
        result = base + datetime.timedelta(days=self.interval_days)
        return result.replace(hour=10, minute=0, second=0, microsecond=0)

    def extract_topic(self, user_text: str) -> str:
        # Убираем временные маркеры из темы
        cleaned = re.sub(
            r'(завтра|послезавтра|через\s+\d+\s+дн\w+|в\s+\w+|'
            r'\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2})\s*[|,]?\s*',
            '', user_text, flags=re.IGNORECASE
        ).strip()
        return cleaned or user_text

    async def generate_post(self, topic: str) -> str:
        resp = await self.client.responses.create(
            model=self.model,
            input=[{
                "role": "user",
                "content": POST_GEN_PROMPT.format(topic=topic, style_prompt=CHANNEL_STYLE_PROMPT)
            }],
        )
        return resp.output_text.strip()

    def format_schedule_label(self, dt: datetime.datetime) -> str:
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        day = days[dt.weekday()]
        return dt.strftime(f"{day} %d.%m в %H:%M")

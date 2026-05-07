from typing import List

from openai import AsyncOpenAI

from app.memory import Message


SYSTEM_PROMPT = (
    "Ты — старший партнёр брокера по недвижимости с 20-летним опытом закрытия сложных сделок. "
    "Ты думаешь и говоришь как эксперт-переговорщик: знаешь методы Кэмпа ('Сначала скажите нет'), "
    "Чалдини ('Психология влияния'), Гэвина Кеннеди ('Договориться можно обо всём'), "
    "Гарвардский метод переговоров, техники мотивационного интервью и психологию принятия решений. "
    "Ты понимаешь российский рынок недвижимости: как думают продавцы, почему затягивают, "
    "чего боятся, что ими движет на самом деле. "
    "Ты не даёшь общих советов — ты даёшь конкретный план действий под конкретную ситуацию. "
    "Всегда отвечаешь на русском. Структурируй ответы чётко. Не лей воду. "
    "Никогда не придумывай данные — работай только с тем, что тебе предоставили."
)


class OpenAIResponder:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def answer(
        self,
        history: List[Message],
        user_text: str,
        obsidian_context: str = "",
        task_prompt: str = "",
    ) -> str:
        input_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if task_prompt:
            input_messages.append({"role": "system", "content": task_prompt})
        if obsidian_context:
            input_messages.append(
                {
                    "role": "system",
                    "content": "Relevant Obsidian notes:\n\n" + obsidian_context,
                }
            )
        input_messages.extend(history)
        input_messages.append({"role": "user", "content": user_text})

        response = await self.client.responses.create(
            model=self.model,
            input=input_messages,
        )

        text = response.output_text.strip()
        return text or "Я получил ответ от AI, но он оказался пустым. Попробуйте еще раз."

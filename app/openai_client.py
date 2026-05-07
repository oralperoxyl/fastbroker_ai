from typing import List

from openai import AsyncOpenAI

from app.memory import Message


SYSTEM_PROMPT = (
    "You are a helpful AI assistant inside Telegram. "
    "Reply in the user's language. Keep answers practical and concise. "
    "When Obsidian notes are provided, use them as the user's private knowledge base. "
    "If the notes do not contain enough information, say so briefly instead of inventing facts."
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

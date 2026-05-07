import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    openai_model: str
    max_history_messages: int
    obsidian_vault_path: str
    data_dir: str


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    max_history_messages = int(os.getenv("MAX_HISTORY_MESSAGES", "12"))
    obsidian_vault_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    data_dir = os.getenv("DATA_DIR", "data").strip()

    missing = []
    if not telegram_bot_token or telegram_bot_token == "PASTE_TELEGRAM_TOKEN_HERE":
        missing.append("TELEGRAM_BOT_TOKEN")
    if not openai_api_key or openai_api_key == "PASTE_OPENAI_API_KEY_HERE":
        missing.append("OPENAI_API_KEY")

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required values in .env: {names}")

    return Settings(
        telegram_bot_token=telegram_bot_token,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        max_history_messages=max_history_messages,
        obsidian_vault_path=obsidian_vault_path,
        data_dir=data_dir,
    )

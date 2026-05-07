import json
from pathlib import Path
from typing import Dict, List


Message = Dict[str, str]


class ConversationMemory:
    def __init__(self, path: str, max_messages: int) -> None:
        self.path = Path(path)
        self.max_messages = max_messages
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: Dict[str, List[Message]] = self._load()

    def get(self, chat_id: int) -> List[Message]:
        return list(self._items.get(str(chat_id), []))

    def add(self, chat_id: int, role: str, content: str) -> None:
        key = str(chat_id)
        messages = self._items.setdefault(key, [])
        messages.append({"role": role, "content": content})
        self._items[key] = messages[-self.max_messages :]
        self._save()

    def clear(self, chat_id: int) -> None:
        self._items.pop(str(chat_id), None)
        self._save()

    def _load(self) -> Dict[str, List[Message]]:
        if not self.path.exists():
            return {}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

        if not isinstance(data, dict):
            return {}

        return data

    def _save(self) -> None:
        self.path.write_text(
            json.dumps(self._items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class NoteMatch:
    title: str
    path: str
    content: str
    score: int


class ObsidianVault:
    def __init__(self, vault_path: str, max_file_chars: int = 12000) -> None:
        self.vault_path = Path(vault_path).expanduser()
        self.max_file_chars = max_file_chars

    def is_enabled(self) -> bool:
        return bool(str(self.vault_path)) and self.vault_path.exists()

    def search(self, query: str, limit: int = 4) -> List[NoteMatch]:
        if not self.is_enabled():
            return []

        query_terms = self._terms(query)
        if not query_terms:
            return []

        matches: List[NoteMatch] = []
        for path in self.vault_path.rglob("*.md"):
            if "/.obsidian/" in path.as_posix():
                continue

            content = self._read_note(path)
            if not content:
                continue

            title = path.stem.replace("_", " ")
            score = self._score(title, content, query_terms)
            if score > 0:
                matches.append(
                    NoteMatch(
                        title=title,
                        path=str(path.relative_to(self.vault_path)),
                        content=self._compact(content),
                        score=score,
                    )
                )

        matches.sort(key=lambda item: item.score, reverse=True)
        return matches[:limit]

    def build_context(self, query: str, limit: int = 4) -> str:
        matches = self.search(query, limit=limit)
        if not matches:
            return ""

        blocks = []
        for match in matches:
            blocks.append(
                f"Note: {match.title}\n"
                f"Path: {match.path}\n"
                f"Content:\n{match.content}"
            )

        return "\n\n---\n\n".join(blocks)

    def _read_note(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")[: self.max_file_chars]
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="utf-8-sig")[: self.max_file_chars]
            except OSError:
                return ""
        except OSError:
            return ""

    def _terms(self, text: str) -> List[str]:
        return [term.lower() for term in re.findall(r"[\wа-яА-ЯёЁ]{3,}", text)]

    def _score(self, title: str, content: str, query_terms: List[str]) -> int:
        title_lower = title.lower()
        content_lower = content.lower()
        score = 0

        for term in query_terms:
            if term in title_lower:
                score += 8
            score += min(content_lower.count(term), 8)

        return score

    def _compact(self, content: str, max_chars: int = 2500) -> str:
        text = re.sub(r"\n{3,}", "\n\n", content).strip()
        text = re.sub(r"[ \t]+", " ", text)
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rsplit(" ", 1)[0] + "..."

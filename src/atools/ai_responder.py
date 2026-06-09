from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .aiasist_bridge import AiAsistBridge
from .models import Report, VipChatMessage
from .paths import ai_config_path, ai_resource_path


DEFAULT_BASE_URL = "http://localhost:3264/api"
FILE_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251", "cp866", "utf-16")

DEFAULT_CONFIG: dict[str, Any] = {
    "base_url": DEFAULT_BASE_URL,
    "api_keys": ["dummy-key"],
    "preferred_models": ["qwen3.7-max"],
    "skip_models": [],
    "request": {
        "temperature": 0.2,
        "max_completion_tokens": 320,
        "timeout_seconds": 90,
    },
    "retrieval": {
        "top_k": 4,
        "chunk_size": 1600,
        "chunk_overlap": 250,
        "max_context_chars": 6000,
    },
}

VIP_CLASSIFICATION_BATCH_SIZE = 6
REPORT_EXAMPLE_MIN_OVERLAP = 2
REPORT_EXAMPLE_MIN_SCORE = 0.66
REPORT_EXAMPLE_STRONG_SCORE = 0.82
REPORT_EXAMPLE_MIN_MARGIN = 0.07
REPORT_EXAMPLE_CONTEXT_TOP_K = 4
REPORT_EXAMPLE_CONTEXT_MIN_SCORE = 0.56
MECHANIC_MATCH_TOP_K = 3
MECHANIC_FAST_REPLY_MIN_SCORE = 26
REPORT_GENERIC_FALLBACK_TEXT = "Вітаю! Дізнайтесь у гравців."

DEFAULT_VIP_AD_POLICY = """
Ти модеруєш VIP-чат і визначаєш намір повідомлення, а не окремі слова.

Вважай повідомлення забороненим, якщо його мета:
- купити, продати, обміняти, орендувати, замовити або знайти товар чи послугу;
- знайти продавця, покупця, ціну, пропозицію або домовитися про угоду;
- почати торгову взаємодію навіть у формі питання.

Питальне формулювання теж є порушенням, якщо за ним стоїть намір купівлі, продажу, обміну, пошуку пропозиції або домовленості.

Вважай повідомлення дозволеним, якщо його мета:
- просто дізнатися інформацію, правила, механіку, місце, спосіб отримання або пораду;
- уточнити факти без наміру купити, продати чи домовитися про угоду;
- безкоштовно допомогти, передати щось без оплати, покликати на роботу або попросити службову дію.

Якщо сумніваєшся, дивись на загальний намір:
- якщо є ціль угоди або пошуку пропозиції, це реклама або торгівля;
- якщо текст двозначний, короткий або неповний і в ньому немає явного факту угоди, не вважай це порушенням;
- якщо є лише бажання щось з'ясувати, це не реклама.

Не вважай порушенням такі приклади:
- "Конан хелле завези товари в салон" — прохання завезти товари в бізнес;
- "кто на инкосатора" — запрошення на роботу;
- "2 штуки есть" — двозначна коротка фраза без факту продажу;
- "я тебе так могу дать, едь на азс возле тк" — безкоштовна пропозиція;
- "нужны?" — немає факту продажу, купівлі чи оренди.

Вважай порушенням такі приклади:
- "скільки бубликів хочеш за штучку?";
- "продаю чип 4 тип R клас авто B";
- "кейс квітучий треба кому?";
- "Візьму в оренду Актроса L";
- "хто має квадроцикл?" — якщо це виглядає як пошук власника для угоди.

У reason пиши коротку людську причину.
У tags пиши 1-3 короткі мітки.
""".strip()

STOPWORDS = {
    "або",
    "але",
    "без",
    "би",
    "був",
    "бути",
    "в",
    "ви",
    "все",
    "він",
    "вона",
    "вони",
    "де",
    "для",
    "до",
    "дуже",
    "з",
    "за",
    "же",
    "й",
    "і",
    "із",
    "його",
    "її",
    "коли",
    "має",
    "мені",
    "ми",
    "на",
    "не",
    "ні",
    "ну",
    "о",
    "от",
    "під",
    "по",
    "про",
    "при",
    "працювати",
    "працює",
    "та",
    "так",
    "також",
    "те",
    "ти",
    "то",
    "той",
    "у",
    "це",
    "цей",
    "ці",
    "що",
    "щоб",
    "як",
    "яка",
    "який",
    "якщо",
}

RETRYABLE_HINTS = (
    "quota",
    "daily quota",
    "token",
    "tokens",
    "rate limit",
    "too many requests",
    "credits",
    "insufficient",
    "exceeded",
    "exhausted",
    "capacity",
    "temporarily unavailable",
    "model not found",
    "not available",
)

REPORT_LOOKUP_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\btp\b", "тп"),
    (r"\bteleport\b", "телепорт"),
    (r"промо[\s-]*код", "промокод"),
    (r"\bивент\b", "івент"),
    (r"\bэвент\b", "івент"),
    (r"\bкогда\b", "коли"),
    (r"\bгде\b", "де"),
    (r"\bгдє\b", "де"),
    (r"\bтавари\b", "товари"),
    (r"\bтоварри\b", "товари"),
    (r"евакувац", "евакуац"),
    (r"транспору", "транспорту"),
    (r"\bмое\b", "моє"),
    (r"\bадмин\b", "адмін"),
)


@dataclass(slots=True)
class Chunk:
    title: str
    text: str
    normalized: str
    tokens: Counter[str]


@dataclass(slots=True)
class ModelInfo:
    model_id: str
    display_name: str
    context_window: int = 0
    max_tokens: int = 0
    quota_hint: int = 0
    developer: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class KeyPool:
    key_index: int
    api_key: str
    models: list[ModelInfo]
    disabled: bool = False
    disabled_reason: str = ""


@dataclass(slots=True)
class ChatResult:
    content: str
    model_name: str
    key_index: int
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GeneratedAIReply:
    text: str
    model_name: str
    key_index: int
    context_preview: str


@dataclass(slots=True)
class VipAdDecision:
    is_ad: bool
    reason: str
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class ReportExample:
    question: str
    normalized_question: str
    answer: str
    support: int
    tokens: Counter[str]


@dataclass(slots=True)
class ReportExampleMatch:
    answer: str
    source_question: str
    score: float
    support: int


@dataclass(slots=True)
class MechanicMemoryEntry:
    title: str
    summary: str
    facts: tuple[str, ...]
    normalized_title: str
    normalized_summary: str
    normalized_text: str
    tokens: Counter[str]


@dataclass(slots=True)
class MechanicMemoryMatch:
    entry: MechanicMemoryEntry
    score: int
    overlap: int


class APIRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    @property
    def combined_text(self) -> str:
        return f"{self.args[0]} {self.response_body}".strip()

    def short_text(self, limit: int = 220) -> str:
        text = normalize_space(self.combined_text)
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_report_lookup_text(text: str) -> str:
    normalized = normalize_space(normalize_newlines(text).casefold())
    normalized = re.sub(r"(.)\1{2,}", r"\1", normalized)
    for pattern, replacement in REPORT_LOOKUP_REPLACEMENTS:
        normalized = re.sub(pattern, replacement, normalized)
    return normalized


def text_has_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle in text for needle in needles)


def text_has_all(text: str, groups: Sequence[str | Sequence[str]]) -> bool:
    for group in groups:
        if isinstance(group, str):
            if group not in text:
                return False
            continue
        if not any(item in text for item in group):
            return False
    return True


def is_vehicle_lookup_report(text: str) -> bool:
    return (
        text_has_any(text, ("моє авто", "мое авто", "авто"))
        and text_has_any(text, ("де", "где", "евакуац"))
    )


def is_goods_restock_report(text: str) -> bool:
    return text_has_all(text, (("товар", "товари"), ("завез", "завести", "завезти")))


def is_cleanup_report(text: str) -> bool:
    return text_has_all(text, (("цр", "cr"), ("почист", "очист", "зачист")))


def is_event_report(text: str) -> bool:
    return "івент" in text and text_has_any(text, ("коли", "зроб", "сдел", "буде"))


def is_promo_report(text: str) -> bool:
    return "промокод" in text or text_has_all(text, (("промо",), ("код", "коди")))


def is_staff_punishment_report(text: str) -> bool:
    return text_has_any(text, ("мут", "mute", "бан", "ban", "варн", "warn", "покаран", "наказан")) and text_has_any(
        text,
        ("за що", "за что", "чому", "почему", "неправ", "адмін", "админ"),
    )


def is_state_org_report(text: str) -> bool:
    return text_has_any(
        text,
        ("держ", "гос", "сбу", "дбр", "дснс", "поліці", "полици", "військ", "воен", "мед", "лікар"),
    ) and text_has_any(
        text,
        ("неправ", "незакон", "без прич", "затрим", "арешт", "штраф", "посад", "діють", "действ"),
    )


def is_tp_request_report(text: str) -> bool:
    if not text_has_any(text, (" тп", "тп ", " tp", "tp ", "телепорт")):
        return False
    stripped = normalize_space(text)
    if stripped in {"тп", "tp", "телепорт"}:
        return False
    if text_has_any(stripped, ("як тп", "как тп", "де тп", "где тп", "що таке тп", "что такое тп")):
        return False
    significant_tokens = [
        token
        for token in tokenize(stripped)
        if token not in {"тп", "tp", "телепорт", "телепорта", "телепорту"}
    ]
    return bool(significant_tokens)


def is_stuck_report(text: str) -> bool:
    return text_has_any(text, ("застряг", "завис", "вишу", "забаг", "провалився"))


def is_help_ping_report(text: str) -> bool:
    if not text_has_any(text, ("help", "хелп", "помог", "помож", "допом")):
        return False
    tokens = tokenize(text)
    return 1 <= len(tokens) <= 5


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    last_error: Exception | None = None

    for encoding in FILE_ENCODINGS:
        try:
            return normalize_newlines(raw.decode(encoding))
        except UnicodeDecodeError as exc:
            last_error = exc

    raise RuntimeError(f"Не вдалося прочитати {path.name}: {last_error}")


def load_aiasist_provider_snapshot() -> tuple[str, list[str], list[str]]:
    try:
        providers = AiAsistBridge().provider_configs()
    except Exception:
        return "", [], []

    base_url = ""
    api_keys: list[str] = []
    preferred_models: list[str] = []

    for provider in providers:
        provider_url = str(provider.get("url") or "").strip().rstrip("/")
        if provider_url and not base_url:
            base_url = provider_url

        for api_key in provider.get("keys", []):
            if not isinstance(api_key, str):
                continue
            normalized_key = api_key.strip()
            if normalized_key and normalized_key not in api_keys:
                api_keys.append(normalized_key)

        for model_name in provider.get("models", []):
            if not isinstance(model_name, str):
                continue
            normalized_model = model_name.strip()
            if normalized_model and normalized_model not in preferred_models:
                preferred_models.append(normalized_model)

    return base_url, api_keys, preferred_models


def load_config(config_path: Path) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)

    if config_path.exists():
        user_config = json.loads(read_text_file(config_path))
        config = deep_merge(config, user_config)

    env_keys_raw = (
        os.getenv("FREEQWEN_API_KEYS")
        or os.getenv("FREEQWEN_API_KEY")
        or os.getenv("IOI_API_KEYS")
        or os.getenv("IOI_API_KEY")
        or ""
    )
    env_keys = [item.strip() for item in env_keys_raw.split(",") if item.strip()]
    aiasist_base_url, aiasist_keys, aiasist_models = load_aiasist_provider_snapshot()

    api_keys = [
        item.strip()
        for item in config.get("api_keys", [])
        if isinstance(item, str) and item.strip() and "PASTE_" not in item
    ]
    if aiasist_keys:
        api_keys = aiasist_keys
    elif not api_keys and env_keys:
        api_keys = env_keys

    config["api_keys"] = api_keys
    config["base_url"] = (aiasist_base_url or str(config.get("base_url", DEFAULT_BASE_URL))).rstrip("/")
    preferred_models = [
        item.strip()
        for item in config.get("preferred_models", [])
        if isinstance(item, str) and item.strip()
    ]
    config["preferred_models"] = aiasist_models or preferred_models
    config["skip_models"] = {
        item.strip().lower()
        for item in config.get("skip_models", [])
        if isinstance(item, str) and item.strip()
    }
    return config


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[0-9A-Za-zА-Яа-яЁёЇїІіЄєҐґ'`-]+", text.lower())
    tokens: list[str] = []

    for word in words:
        cleaned = word.strip("-'`")
        if len(cleaned) < 2 or cleaned in STOPWORDS:
            continue
        tokens.append(cleaned)

    return tokens


def extract_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    current_lines: list[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if not body:
            return
        title = " / ".join(stack) if stack else "Загальна інформація"
        sections.append((title, body))

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            flush()
            level = len(match.group(1))
            heading = match.group(2).strip()
            stack[:] = stack[: level - 1] + [heading]
            current_lines.clear()
            continue
        current_lines.append(line)

    flush()
    return sections


def split_section(title: str, body: str, max_chars: int, overlap: int) -> list[str]:
    content = f"Розділ: {title}\n{body.strip()}"
    if len(content) <= max_chars:
        return [content]

    chunks: list[str] = []
    start = 0

    while start < len(content):
        end = min(len(content), start + max_chars)
        if end < len(content):
            candidate_points = [
                content.rfind("\n\n", start + max_chars // 2, end),
                content.rfind("\n", start + max_chars // 2, end),
                content.rfind(". ", start + max_chars // 2, end),
            ]
            best_point = max(candidate_points)
            if best_point > start:
                end = best_point

        piece = content[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= len(content):
            break

        next_start = end - overlap
        start = next_start if next_start > start else end

    return chunks


class LocalKnowledgeBase:
    def __init__(
        self,
        path: Path,
        chunk_size: int,
        chunk_overlap: int,
        *,
        text_override: str | None = None,
    ) -> None:
        self.path = path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text = normalize_newlines(text_override) if text_override is not None else read_text_file(path)
        self.chunks = self._build_chunks()
        self.token_document_frequency = self._build_document_frequency()

    def _build_chunks(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for title, body in extract_sections(self.text):
            for part in split_section(title, body, self.chunk_size, self.chunk_overlap):
                chunks.append(
                    Chunk(
                        title=title,
                        text=part,
                        normalized=part.lower(),
                        tokens=Counter(tokenize(part)),
                    )
                )
        return chunks

    def _build_document_frequency(self) -> Counter[str]:
        document_frequency: Counter[str] = Counter()
        for chunk in self.chunks:
            for token in chunk.tokens:
                document_frequency[token] += 1
        return document_frequency

    def _token_weight(self, token: str) -> int:
        frequency = self.token_document_frequency.get(token, 1)
        if frequency <= 1:
            return 7
        if frequency <= 3:
            return 5
        if frequency <= 10:
            return 3
        if frequency <= 20:
            return 2
        return 1

    def search(self, query: str, top_k: int, max_context_chars: int) -> list[Chunk]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        query_counter = Counter(query_tokens)
        scored: list[tuple[int, int, Chunk]] = []

        for chunk in self.chunks:
            score = 0

            for token, count in query_counter.items():
                hits = chunk.tokens.get(token, 0)
                if not hits:
                    continue
                score += min(hits, count) * self._token_weight(token)
                if token in chunk.title.lower():
                    score += 6

            for token in query_counter:
                if len(token) >= 4 and token in chunk.normalized:
                    score += 2

            if score > 0:
                scored.append((score, len(chunk.text), chunk))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

        selected: list[Chunk] = []
        total_chars = 0
        seen_titles: set[str] = set()

        for _, _, chunk in scored:
            if len(selected) >= top_k:
                break
            if chunk.title in seen_titles and len(selected) >= 2:
                continue
            if total_chars + len(chunk.text) > max_context_chars and selected:
                break
            selected.append(chunk)
            seen_titles.add(chunk.title)
            total_chars += len(chunk.text)

        return selected

    @staticmethod
    def format_context(chunks: Sequence[Chunk]) -> str:
        if not chunks:
            return "Релевантні фрагменти не знайдено."
        blocks = [f"[Фрагмент {index}]\n{chunk.text}" for index, chunk in enumerate(chunks, start=1)]
        return "\n\n".join(blocks)


class MechanicMemory:
    def __init__(self, entries: Sequence[MechanicMemoryEntry]) -> None:
        self.entries = list(entries)

    @classmethod
    def from_text_sources(cls, sources: Sequence[tuple[str, str]]) -> MechanicMemory:
        deduped: dict[str, MechanicMemoryEntry] = {}

        for source_name, text in sources:
            if not text.strip():
                continue
            for title, body in extract_sections(text):
                normalized_title = normalize_report_lookup_text(title)
                if not normalized_title:
                    continue

                lines = cls._clean_lines(body)
                if not lines:
                    continue

                summary = cls._extract_summary(lines)
                facts = cls._extract_facts(lines, summary=summary)
                normalized_summary = normalize_report_lookup_text(summary)
                normalized_facts = " ".join(normalize_report_lookup_text(item) for item in facts)
                normalized_text = normalize_space(
                    " ".join(item for item in (normalized_title, normalized_summary, normalized_facts) if item)
                )
                tokens = Counter(tokenize(normalized_text))
                if not tokens:
                    continue

                entry = MechanicMemoryEntry(
                    title=f"{source_name}: {title}",
                    summary=summary,
                    facts=facts,
                    normalized_title=normalized_title,
                    normalized_summary=normalized_summary,
                    normalized_text=normalized_text,
                    tokens=tokens,
                )

                existing = deduped.get(normalized_title)
                if existing is None or len(entry.normalized_text) > len(existing.normalized_text):
                    deduped[normalized_title] = entry

        return cls(list(deduped.values()))

    @staticmethod
    def _clean_lines(text: str) -> list[str]:
        result: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip().replace("`", "")
            if not line:
                continue
            if line in {"---", "___", "***"}:
                continue

            cleaned = re.sub(r"^[\-\*\u2022\d\)\.(\s)+]+", "", line).strip()
            cleaned = normalize_space(cleaned)
            if len(cleaned) < 4:
                continue

            result.append(cleaned)

        return result

    @staticmethod
    def _extract_summary(lines: Sequence[str]) -> str:
        for line in lines:
            if len(line) >= 12:
                return line[:220]
        return lines[0] if lines else ""

    @staticmethod
    def _extract_facts(lines: Sequence[str], *, summary: str, limit: int = 6) -> tuple[str, ...]:
        facts: list[str] = []
        seen: set[str] = set()

        for line in lines:
            if line == summary:
                continue
            if line in seen:
                continue
            seen.add(line)

            if len(line) > 220:
                line = line[:217].rstrip(" ,.;:") + "..."
            facts.append(line)
            if len(facts) >= limit:
                break

        if not facts and summary:
            facts.append(summary)

        return tuple(facts)

    def search(self, query: str, top_k: int = MECHANIC_MATCH_TOP_K) -> list[MechanicMemoryMatch]:
        query_tokens = Counter(tokenize(query))
        if not query_tokens:
            return []

        scored: list[MechanicMemoryMatch] = []
        for entry in self.entries:
            score = 0
            overlap = 0
            for token, count in query_tokens.items():
                hits = entry.tokens.get(token, 0)
                if not hits:
                    continue

                token_hits = min(hits, count)
                overlap += token_hits
                score += token_hits * 4

                if token in entry.normalized_title:
                    score += 7
                if token in entry.normalized_summary:
                    score += 4
                if len(token) >= 4 and token in entry.normalized_text:
                    score += 2

            if score > 0:
                scored.append(MechanicMemoryMatch(entry=entry, score=score, overlap=overlap))

        scored.sort(key=lambda item: (item.score, item.overlap, len(item.entry.title)), reverse=True)
        return scored[:top_k]

    @staticmethod
    def format_context(matches: Sequence[MechanicMemoryMatch]) -> str:
        if not matches:
            return "Релевантні механіки не знайдено."

        blocks: list[str] = []
        for index, match in enumerate(matches, start=1):
            facts = "\n".join(f"- {item}" for item in match.entry.facts[:5])
            block = (
                f"[Механіка {index}] {match.entry.title}\n"
                f"Коротко: {match.entry.summary}\n"
                f"Факти:\n{facts}"
            )
            blocks.append(block)

        return "\n\n".join(blocks)

    def best_quick_reply(self, query: str) -> tuple[str, MechanicMemoryMatch] | None:
        matches = self.search(query, top_k=1)
        if not matches:
            return None

        best = matches[0]
        if best.score < MECHANIC_FAST_REPLY_MIN_SCORE or best.overlap < 2:
            return None

        candidate = best.entry.summary or (best.entry.facts[0] if best.entry.facts else "")
        candidate = normalize_space(candidate)
        if len(candidate) < 8:
            return None
        if len(candidate) > 150:
            candidate = candidate[:147].rstrip(" ,.;:") + "..."

        return candidate, best


class LocalReportExampleMemory:
    LOW_SIGNAL_QUESTIONS = {
        "привіт",
        "привет",
        "ку",
        "дякую",
        "спасибо",
        "спасибі",
        "thank you",
        "good morning",
        "good evening",
    }

    def __init__(self, examples: Sequence[ReportExample]) -> None:
        self.examples = list(examples)
        self.exact_map: dict[str, ReportExample] = {}
        self.token_index: dict[str, set[int]] = {}

        for index, example in enumerate(self.examples):
            existing = self.exact_map.get(example.normalized_question)
            if existing is None or example.support > existing.support:
                self.exact_map[example.normalized_question] = example

            for token in example.tokens:
                self.token_index.setdefault(token, set()).add(index)

    @classmethod
    def from_json(cls, path: Path) -> LocalReportExampleMemory:
        payload = json.loads(read_text_file(path))
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise RuntimeError("report_examples.json має некоректний формат.")

        examples: list[ReportExample] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            question = normalize_space(str(item.get("question") or ""))
            answer = cls._sanitize_answer(str(item.get("answer") or ""))
            if not question or not answer:
                continue

            normalized_question = normalize_report_lookup_text(
                str(item.get("normalized") or question)
            )
            try:
                support = int(item.get("support", 1))
            except (TypeError, ValueError):
                support = 1
            support = max(1, support)

            tokens = Counter(tokenize(normalized_question))
            if not tokens:
                continue
            if cls._is_low_signal_question(normalized_question, tokens):
                continue

            examples.append(
                ReportExample(
                    question=question,
                    normalized_question=normalized_question,
                    answer=answer,
                    support=support,
                    tokens=tokens,
                )
            )

        return cls(examples)

    @classmethod
    def _is_low_signal_question(cls, normalized_question: str, tokens: Counter[str]) -> bool:
        if normalized_question in cls.LOW_SIGNAL_QUESTIONS:
            return True
        if len(tokens) == 1:
            token = next(iter(tokens))
            if token in cls.LOW_SIGNAL_QUESTIONS:
                return True
        return False

    @staticmethod
    def _sanitize_answer(raw_answer: str) -> str:
        answer = normalize_space(raw_answer.replace("\u200d", "").replace("\ufeff", ""))
        if not answer:
            return ""

        lower = answer.casefold().replace("’", "'")
        if "ку-кус" in lower:
            return ""

        if "на зв'язку" in lower and (
            "працюю по вашій заявці" in lower
            or "опрацьовую ваш запит" in lower
            or "лечу до вас" in lower
            or "вилітаю" in lower
            or "тримайтесь вже лечу" in lower
        ):
            return "Вітаю! На зв'язку адміністратор, опрацьовую ваш запит."

        if not lower.startswith(("вітаю", "дізнайтесь")):
            return ""
        if len(answer) > 160:
            return ""

        return answer

    def _score_candidates(self, text: str) -> list[tuple[float, int, ReportExample]]:
        normalized = normalize_report_lookup_text(text)
        if not normalized:
            return []

        query_tokens = Counter(tokenize(normalized))
        if not query_tokens:
            return []

        candidate_indexes: set[int] = set()
        for token in query_tokens:
            candidate_indexes.update(self.token_index.get(token, set()))

        if not candidate_indexes:
            return []

        query_size = sum(query_tokens.values())
        if query_size <= 1:
            return []

        min_overlap = REPORT_EXAMPLE_MIN_OVERLAP
        if query_size == 2:
            longest_token = max((len(token) for token in query_tokens), default=0)
            if longest_token >= 4:
                min_overlap = 1

        scored: list[tuple[float, int, ReportExample]] = []
        for index in candidate_indexes:
            example = self.examples[index]
            overlap = sum(
                min(query_tokens[token], example.tokens.get(token, 0))
                for token in query_tokens
            )
            if overlap < min_overlap:
                continue

            coverage = overlap / max(1, query_size)
            precision = overlap / max(1, sum(example.tokens.values()))
            support_bonus = min(example.support, 5) * 0.03
            score = (coverage * 0.72) + (precision * 0.28) + support_bonus

            if normalized in example.normalized_question or example.normalized_question in normalized:
                score += 0.08

            scored.append((score, overlap, example))

        scored.sort(key=lambda item: (item[0], item[1], item[2].support), reverse=True)
        return scored

    def search_many(
        self,
        text: str,
        *,
        top_k: int = 3,
        min_score: float = 0.55,
    ) -> list[ReportExampleMatch]:
        matches: list[ReportExampleMatch] = []
        for score, _overlap, example in self._score_candidates(text):
            if score < min_score:
                continue
            matches.append(
                ReportExampleMatch(
                    answer=example.answer,
                    source_question=example.question,
                    score=score,
                    support=example.support,
                )
            )
            if len(matches) >= top_k:
                break
        return matches

    def match(self, text: str) -> ReportExampleMatch | None:
        normalized = normalize_report_lookup_text(text)
        if not normalized:
            return None

        exact = self.exact_map.get(normalized)
        if exact is not None:
            return ReportExampleMatch(
                answer=exact.answer,
                source_question=exact.question,
                score=1.0,
                support=exact.support,
            )

        scored = self._score_candidates(text)

        if not scored:
            return None

        scored.sort(key=lambda item: (item[0], item[1], item[2].support), reverse=True)
        best_score, _best_overlap, best_example = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0

        if best_score < REPORT_EXAMPLE_MIN_SCORE:
            return None
        if best_score < REPORT_EXAMPLE_STRONG_SCORE and (best_score - second_score) < REPORT_EXAMPLE_MIN_MARGIN:
            return None

        return ReportExampleMatch(
            answer=best_example.answer,
            source_question=best_example.question,
            score=best_score,
            support=best_example.support,
        )


def extract_error_message(raw_body: str) -> str:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return normalize_space(raw_body) or "API повернуло помилку без тексту."

    def walk(node: Any) -> str | None:
        if isinstance(node, str):
            return normalize_space(node)
        if isinstance(node, dict):
            for key in ("message", "error", "detail", "details", "title"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    return normalize_space(value)
            for value in node.values():
                found = walk(value)
                if found:
                    return found
        if isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
        return None

    return walk(payload) or "API повернуло помилку без пояснення."


def extract_json_payload(raw_text: str) -> Any:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    for opener, closer in (("[", "]"), ("{", "}")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start == -1 or end == -1 or end < start:
            continue
        candidate = cleaned[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise RuntimeError("AI повернув некоректний JSON для класифікації VIP-повідомлень.")


class IOIntelligenceClient:
    def __init__(
        self,
        *,
        api_keys: Sequence[str],
        base_url: str,
        preferred_models: Sequence[str],
        skip_models: Sequence[str],
        request_settings: dict[str, Any],
    ) -> None:
        self.api_keys = list(api_keys)
        self.base_url = base_url.rstrip("/")
        self.preferred_rank = {item.lower(): index for index, item in enumerate(preferred_models)}
        self.skip_models = set(item.lower() for item in skip_models)
        self.temperature = float(request_settings.get("temperature", 0.2))
        self.max_completion_tokens = int(request_settings.get("max_completion_tokens", 320))
        self.timeout_seconds = int(request_settings.get("timeout_seconds", 90))
        self.pools: list[KeyPool] = []
        self.blocked_models: set[tuple[int, str]] = set()

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "RichCore-AI-Responder/1.0",
        }
        data: bytes | None = None

        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise APIRequestError(
                extract_error_message(body),
                status_code=exc.code,
                response_body=body,
            ) from exc
        except urllib.error.URLError as exc:
            raise APIRequestError(f"Помилка мережі: {exc.reason}") from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise APIRequestError(
                "API повернуло не-JSON відповідь.",
                response_body=raw[:1000],
            ) from exc

        if isinstance(parsed, list):
            return {"data": parsed}
        if isinstance(parsed, dict):
            return parsed
        raise APIRequestError("API повернуло неочікуваний формат відповіді.")

    def refresh_model_pools(self) -> None:
        self.pools = []
        self.blocked_models.clear()

        for key_index, api_key in enumerate(self.api_keys):
            try:
                models = self._fetch_models_for_key(api_key)
            except APIRequestError as exc:
                self.pools.append(
                    KeyPool(
                        key_index=key_index,
                        api_key=api_key,
                        models=[],
                        disabled=True,
                        disabled_reason=exc.short_text(),
                    )
                )
                continue

            self.pools.append(KeyPool(key_index=key_index, api_key=api_key, models=models))

    def _fetch_models_for_key(self, api_key: str) -> list[ModelInfo]:
        page = 1
        all_items: list[dict[str, Any]] = []

        while True:
            response = self._request_json(
                "GET",
                "/models",
                api_key=api_key,
                params={"page": page, "page_size": 100},
            )
            items = response.get("data", [])
            if not isinstance(items, list):
                break
            all_items.extend(item for item in items if isinstance(item, dict))

            pagination = response.get("pagination")
            if not isinstance(pagination, dict) or not pagination.get("has_next"):
                break

            page += 1
            if page > 50:
                break

        deduped: dict[str, ModelInfo] = {}
        for item in all_items:
            metadata = item.get("metadata") or {}
            model_id = str(item.get("id") or item.get("model_id") or "").strip()
            display_name = str(item.get("name") or model_id).strip()
            if not model_id:
                model_id = display_name
            if not model_id or model_id.lower() in self.skip_models:
                continue

            status = str(item.get("status") or "").strip().lower()
            if status and status != "active":
                continue

            allow_chat = metadata.get("enable_api_chat_completions")
            if allow_chat is False:
                continue

            context_window = (
                item.get("context_window")
                or metadata.get("context_window")
                or item.get("max_model_len")
                or 0
            )
            max_tokens = item.get("max_tokens") or metadata.get("max_tokens") or 0
            quota_hint = item.get("api_completions_daily_quota_tier_1") or 0
            developer = str(metadata.get("developer") or item.get("owned_by") or "")

            deduped.setdefault(
                model_id,
                ModelInfo(
                    model_id=model_id,
                    display_name=display_name,
                    context_window=int(context_window or 0),
                    max_tokens=int(max_tokens or 0) if max_tokens is not None else 0,
                    quota_hint=int(quota_hint or 0),
                    developer=developer,
                    raw=item,
                ),
            )

        models = list(deduped.values())
        models.sort(key=self._model_sort_key)
        return models

    def _model_sort_key(self, model: ModelInfo) -> tuple[int, int, int, int, str]:
        preferred_rank = min(
            self.preferred_rank.get(model.model_id.lower(), 9999),
            self.preferred_rank.get(model.display_name.lower(), 9999),
        )
        return (
            preferred_rank,
            -model.context_window,
            -model.max_tokens,
            -model.quota_hint,
            model.model_id.lower(),
        )

    def _classify_error(self, error: APIRequestError) -> tuple[bool, bool, str]:
        status = error.status_code
        text = error.combined_text.lower()

        if status in {401, 403}:
            return True, True, "ключ недоступний або заблокований"
        if status == 404:
            return True, False, "модель не знайдена"
        if status in {429, 500, 502, 503, 504}:
            return True, False, "квота або тимчасова помилка"
        if any(hint in text for hint in RETRYABLE_HINTS):
            return True, False, "ліміт, квота або недоступна модель"
        return False, False, "фатальна помилка"

    def complete(self, messages: Sequence[dict[str, str]]) -> ChatResult:
        if not self.pools:
            self.refresh_model_pools()

        attempts: list[str] = []
        for pool in self.pools:
            if pool.disabled:
                if pool.disabled_reason:
                    attempts.append(f"Ключ #{pool.key_index + 1}: {pool.disabled_reason}")
                continue
            if not pool.models:
                attempts.append(f"Ключ #{pool.key_index + 1}: немає chat-моделей")
                continue

            for model in pool.models:
                block_key = (pool.key_index, model.model_id)
                if block_key in self.blocked_models:
                    continue

                try:
                    return self._complete_once(pool, model, messages)
                except APIRequestError as exc:
                    retry_next, disable_key, reason = self._classify_error(exc)
                    attempts.append(
                        f"Ключ #{pool.key_index + 1} / {model.model_id}: {reason} ({exc.short_text()})"
                    )
                    if disable_key:
                        pool.disabled = True
                        pool.disabled_reason = reason
                        break
                    if retry_next:
                        self.blocked_models.add(block_key)
                        continue
                    raise

        joined_attempts = "\n".join(f"- {item}" for item in attempts[:12])
        raise RuntimeError(
            "Не вдалося отримати відповідь від жодної моделі."
            + (f"\n{joined_attempts}" if joined_attempts else "")
        )

    def _complete_once(
        self,
        pool: KeyPool,
        model: ModelInfo,
        messages: Sequence[dict[str, str]],
    ) -> ChatResult:
        response = self._request_json(
            "POST",
            "/chat/completions",
            api_key=pool.api_key,
            payload={
                "model": model.model_id,
                "messages": list(messages),
                "temperature": self.temperature,
                "stream": False,
                "max_completion_tokens": self.max_completion_tokens,
            },
        )

        choices = response.get("choices") or []
        if not choices:
            raise APIRequestError("API повернуло порожній список choices.")

        message = choices[0].get("message") or {}
        content = message.get("content")

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
                elif item:
                    parts.append(str(item))
            content = "\n".join(parts)

        if not isinstance(content, str) or not content.strip():
            raise APIRequestError("API повернуло порожній текст відповіді.")

        return ChatResult(
            content=content.strip(),
            model_name=model.model_id,
            key_index=pool.key_index,
            usage=response.get("usage") or {},
        )


class AIReportResponder:
    def __init__(
        self,
        *,
        config_path: Path | None = None,
        knowledge_path: Path | None = None,
        policy_path: Path | None = None,
    ) -> None:
        self.config_path = config_path or ai_config_path()
        self.knowledge_path = knowledge_path or ai_resource_path("base1.txt")
        self.policy_path = policy_path or ai_resource_path("base2.txt")
        self.vip_ad_policy_path = ai_resource_path("vip_ad_policy.txt")
        self.admin_manual_path = ai_resource_path("admin_manual.txt")
        self.rules_path = ai_resource_path("rules.txt")
        self.report_examples_path = ai_resource_path("report_examples.json")
        self.config = load_config(self.config_path)
        self.answer_policy = read_text_file(self.policy_path).strip()
        self.vip_ad_policy = (
            read_text_file(self.vip_ad_policy_path).strip()
            if self.vip_ad_policy_path.exists()
            else DEFAULT_VIP_AD_POLICY
        )
        retrieval = self.config["retrieval"]
        self.report_memory = self._load_report_memory()
        combined_knowledge = self._build_combined_knowledge()
        self.mechanics_memory = self._build_mechanics_memory(combined_knowledge)
        self.knowledge = LocalKnowledgeBase(
            self.knowledge_path,
            chunk_size=int(retrieval["chunk_size"]),
            chunk_overlap=int(retrieval["chunk_overlap"]),
            text_override=combined_knowledge,
        )
        self.client = IOIntelligenceClient(
            api_keys=self.config["api_keys"],
            base_url=self.config["base_url"],
            preferred_models=self.config["preferred_models"],
            skip_models=self.config["skip_models"],
            request_settings=self.config["request"],
        )

    def _build_combined_knowledge(self) -> str:
        sections: list[str] = []

        base_text = read_text_file(self.knowledge_path).strip()
        if base_text:
            sections.append(base_text)

        if self.admin_manual_path.exists():
            manual_text = read_text_file(self.admin_manual_path).strip()
            if manual_text:
                sections.append(f"# Посібник адміністратора (оновлено)\n\n{manual_text}")

        if self.rules_path.exists():
            rules_text = read_text_file(self.rules_path).strip()
            if rules_text:
                sections.append(f"# Правила проєкту (оновлено)\n\n{rules_text}")

        return "\n\n---\n\n".join(section for section in sections if section)

    def _load_report_memory(self) -> LocalReportExampleMemory | None:
        if not self.report_examples_path.exists():
            return None
        try:
            memory = LocalReportExampleMemory.from_json(self.report_examples_path)
        except Exception:
            return None
        return memory if memory.examples else None

    def _build_mechanics_memory(self, combined_knowledge: str) -> MechanicMemory | None:
        sources: list[tuple[str, str]] = []

        if self.admin_manual_path.exists():
            manual_text = read_text_file(self.admin_manual_path).strip()
            if manual_text:
                sources.append(("Посібник адміністратора", manual_text))

        if self.rules_path.exists():
            rules_text = read_text_file(self.rules_path).strip()
            if rules_text:
                sources.append(("Правила проєкту", rules_text))

        if not sources:
            sources.append(("База знань", combined_knowledge))

        memory = MechanicMemory.from_text_sources(sources)
        return memory if memory.entries else None

    def generate(self, report: Report, admin_nickname: str = "") -> GeneratedAIReply:
        fast_reply = self._try_fast_report_reply(report, admin_nickname=admin_nickname)
        if fast_reply is not None:
            return fast_reply

        self._ensure_ready()
        query = self._build_report_query(report)
        prompt = self._build_report_prompt(report)
        retrieval = self.config["retrieval"]
        chunks = self.knowledge.search(
            query,
            top_k=int(retrieval["top_k"]),
            max_context_chars=int(retrieval["max_context_chars"]),
        )
        knowledge_context = self.knowledge.format_context(chunks)
        mechanic_context = ""
        if self.mechanics_memory is not None:
            mechanic_matches = self.mechanics_memory.search(query, top_k=MECHANIC_MATCH_TOP_K)
            mechanic_context = self.mechanics_memory.format_context(mechanic_matches)
        report_examples_context = ""
        fallback_report_match: ReportExampleMatch | None = None
        if self.report_memory is not None:
            strong_report_match = self.report_memory.match(query)
            similar_report_matches = self.report_memory.search_many(
                query,
                top_k=REPORT_EXAMPLE_CONTEXT_TOP_K,
                min_score=REPORT_EXAMPLE_CONTEXT_MIN_SCORE,
            )
            fallback_report_match = strong_report_match
            if (
                fallback_report_match is None
                and similar_report_matches
                and similar_report_matches[0].score >= REPORT_EXAMPLE_STRONG_SCORE
                and similar_report_matches[0].support >= 2
            ):
                fallback_report_match = similar_report_matches[0]
            report_examples_context = self._format_report_examples_context(similar_report_matches)

        context = self._compose_context_blocks(
            knowledge_context,
            mechanic_context,
            report_examples_context,
        )
        result = self.client.complete(self._build_messages(prompt, context))
        normalized = self.normalize_answer(result.content, admin_nickname=admin_nickname)
        if (
            fallback_report_match is not None
            and self._is_generic_fallback_reply(normalized)
        ):
            memory_reply = self.normalize_answer(
                fallback_report_match.answer,
                admin_nickname=admin_nickname,
            )
            if not self._is_generic_fallback_reply(memory_reply):
                normalized = memory_reply
        return GeneratedAIReply(
            text=normalized,
            model_name=result.model_name,
            key_index=result.key_index + 1,
            context_preview=context,
        )

    @staticmethod
    def _compose_context_blocks(
        knowledge_context: str,
        mechanic_context: str,
        report_examples_context: str,
    ) -> str:
        blocks = [f"Релевантні фрагменти бази знань:\n\n{knowledge_context}"]
        if mechanic_context and mechanic_context.strip():
            blocks.append(f"Пам'ять механік:\n\n{mechanic_context}")
        if report_examples_context and report_examples_context.strip():
            blocks.append(f"Пам'ять репортів (останні схожі кейси):\n\n{report_examples_context}")
        return "\n\n".join(blocks)

    @staticmethod
    def _format_report_examples_context(matches: Sequence[ReportExampleMatch]) -> str:
        if not matches:
            return ""

        lines: list[str] = []
        for index, match in enumerate(matches, start=1):
            lines.append(
                f"{index}. Репорт: {match.source_question} "
                f"(score {match.score:.2f}, support {match.support})"
            )
            lines.append(f"Відповідь: {match.answer}")
        return "\n".join(lines)

    @staticmethod
    def _is_generic_fallback_reply(text: str) -> bool:
        normalized = normalize_report_lookup_text(text)
        fallback_normalized = normalize_report_lookup_text(REPORT_GENERIC_FALLBACK_TEXT)
        return normalized == fallback_normalized or fallback_normalized in normalized

    def _try_fast_report_reply(
        self,
        report: Report,
        *,
        admin_nickname: str = "",
    ) -> GeneratedAIReply | None:
        normalized_text = normalize_report_lookup_text(report.text.strip())
        if not normalized_text:
            return None

        reply: str | None = None
        context_label: str | None = None

        if is_vehicle_lookup_report(normalized_text):
            reply = "Вітаю, P (англ) -> Евакувація транспорту - Відмітити на мапі."
            context_label = "Швидкий шаблон: авто / евакуація"
        elif is_goods_restock_report(normalized_text):
            reply = "Вітаю! Очікуйте коли власник поповнить товари."
            context_label = "Швидкий шаблон: товари"
        elif is_cleanup_report(normalized_text):
            reply = "Вітаю! Очікуйте, як з'явиться вільний адміністратор, проведуть перевірку."
            context_label = "Швидкий шаблон: почистити ЦР"
        elif is_event_report(normalized_text):
            reply = "Вітаю! Очікуйте."
            context_label = "Швидкий шаблон: івент"
        elif is_promo_report(normalized_text):
            reply = REPORT_GENERIC_FALLBACK_TEXT
            context_label = "Швидкий шаблон: промокод"
        elif is_staff_punishment_report(normalized_text) or is_state_org_report(normalized_text):
            reply = "Вітаю! Якщо маєте докази, подайте скаргу на форум."
            context_label = "Швидкий шаблон: скарга на покарання / держорган"
        elif is_tp_request_report(normalized_text):
            reply = "Вітаю! Передам ваш запит."
            context_label = "Швидкий шаблон: ТП-запит"
        elif is_stuck_report(normalized_text) or is_help_ping_report(normalized_text):
            reply = "Вітаю! На зв'язку адміністратор, опрацьовую ваш запит."
            context_label = "Швидкий шаблон: допомога / застряг"
        elif self.report_memory is not None:
            report_match = self.report_memory.match(normalized_text)
            if report_match is not None:
                reply = report_match.answer
                context_label = (
                    "Швидка пам'ять репортів: "
                    f"{report_match.source_question} "
                    f"(score {report_match.score:.2f}, support {report_match.support})"
                )

        if reply is None:
            return None

        return GeneratedAIReply(
            text=self.normalize_answer(reply, admin_nickname=admin_nickname),
            model_name="local-template",
            key_index=0,
            context_preview=context_label or "Швидкий локальний шаблон",
        )

    def classify_vip_messages(self, messages: Sequence[VipChatMessage]) -> list[VipAdDecision]:
        if not messages:
            return []

        self._ensure_ready()
        decisions: list[VipAdDecision] = []

        for start in range(0, len(messages), VIP_CLASSIFICATION_BATCH_SIZE):
            batch = list(messages[start : start + VIP_CLASSIFICATION_BATCH_SIZE])
            result = self.client.complete(self._build_vip_messages(batch))
            decisions.extend(self._parse_vip_decisions(result.content, len(batch)))

        return decisions

    def _ensure_ready(self) -> None:
        if not self.config["api_keys"]:
            raise RuntimeError(
                "Не знайдено API-ключів для AI. Додайте їх у ai_config.json або через IOI_API_KEYS."
            )
        if not self.client.pools:
            self.client.refresh_model_pools()

    def _build_messages(self, prompt: str, context: str) -> list[dict[str, str]]:
        policy = (
            "Ти адміністратор ігрового сервера. Ти готуєш відповідь на репорт гравця.\n"
            "Відповідай СУВОРО 1 коротким реченням. Без води, без пояснень.\n"
            "Твоє єдине джерело знань - текст із блоків 'Релевантні фрагменти бази знань', "
            "'Пам'ять механік' та 'Пам'ять репортів (останні схожі кейси)'.\n"
            "Не вигадуй механіки, команди, ціни, локації чи правила. Якщо точної відповіді немає в контексті, "
            "дотримуйся fallback-правил зі стилю (пиши 'Дізнайтесь у гравців').\n"
            "Поверни тільки фінальний текст для /pm. Жодних лапок чи додаткових слів.\n\n"
            "Стиль відповіді:\n"
            f"{self.answer_policy}"
        )
        return [
            {"role": "system", "content": policy},
            {"role": "system", "content": f"Контекст бази знань і пам'яті:\n\n{context}"},
            {"role": "user", "content": prompt},
        ]

    def _build_vip_messages(self, messages: Sequence[VipChatMessage]) -> list[dict[str, str]]:
        items = [
            f'{index}. {message.player_name}[{message.player_id}]: "{message.text}"'
            for index, message in enumerate(messages, start=1)
        ]
        prompt = (
            "Проаналізуй повідомлення VIP-чату нижче і для кожного визнач, чи це заборонена реклама/торгівля.\n"
            "Також позначай як порушення явні образи, приниження або мат на адресу гравця; у tags додай 'образлива лексика'.\n"
            "Питальне повідомлення теж є порушенням, якщо його намір - купити, продати, знайти пропозицію або домовитися про угоду.\n"
            "Питальне повідомлення не є порушенням, якщо його намір - просто щось дізнатися без наміру угоди.\n"
            "Якщо текст двозначний, короткий або в ньому немає явного факту угоди, не вважай це порушенням.\n"
            "Безкоштовна допомога, службові прохання та запрошення на роботу не є рекламою.\n\n"
            "Поверни тільки JSON-масив без markdown. Формат кожного елемента:\n"
            '[{"index":1,"is_ad":true,"reason":"коротка причина","tags":["короткий тег 1","тег 2"]}]\n\n'
            "Повідомлення:\n"
            + "\n".join(items)
        )
        return [
            {
                "role": "system",
                "content": (
                    "Ти модеруєш VIP-чат і відділяєш рекламу та торгівлю від звичайних інформаційних питань.\n"
                    f"{self.vip_ad_policy}"
                ),
            },
            {"role": "user", "content": prompt},
        ]

    @staticmethod
    def _parse_vip_decisions(raw_text: str, expected_count: int) -> list[VipAdDecision]:
        payload = extract_json_payload(raw_text)
        if isinstance(payload, dict):
            payload = payload.get("items") or payload.get("results") or payload.get("messages") or []
        if not isinstance(payload, list):
            raise RuntimeError("AI повернув не список рішень для VIP-повідомлень.")

        indexed_items: dict[int, dict[str, Any]] = {}
        for offset, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            index_value = item.get("index", offset)
            try:
                normalized_index = int(index_value)
            except (TypeError, ValueError):
                normalized_index = offset
            indexed_items[normalized_index] = item

        decisions: list[VipAdDecision] = []
        for index in range(1, expected_count + 1):
            item = indexed_items.get(index, {})
            is_ad = bool(item.get("is_ad"))
            reason = normalize_space(str(item.get("reason") or ("Реклама або торгівля" if is_ad else "Інформаційне питання")))
            tags_raw = item.get("tags") if isinstance(item, dict) else []
            if isinstance(tags_raw, list):
                tags = tuple(
                    normalize_space(str(tag))
                    for tag in tags_raw
                    if normalize_space(str(tag))
                )[:3]
            else:
                tags = ()
            decisions.append(VipAdDecision(is_ad=is_ad, reason=reason, tags=tags))

        return decisions

    @staticmethod
    def _build_report_query(report: Report) -> str:
        report_text = report.text.strip() or "Без тексту"
        normalized_text = normalize_report_lookup_text(report_text)
        if normalized_text and normalized_text != normalize_space(report_text.casefold()):
            return f"{report_text}\n{normalized_text}"
        return report_text

    @staticmethod
    def _build_report_prompt(report: Report) -> str:
        player_name = report.player_name.strip() or "Гравець"
        report_text = report.text.strip() or "Без тексту"
        normalized_text = normalize_report_lookup_text(report_text)
        normalized_hint = ""
        if normalized_text and normalized_text != normalize_space(report_text.casefold()):
            normalized_hint = f"\nНормалізований варіант із виправленими помилками: {normalized_text}"
        return (
            f"Репорт від {player_name}[{report.player_id}]: {report_text}{normalized_hint}\n\n"
            "Гравці часто пишуть із орфографічними помилками, суржиком і змішаною українською/російською.\n"
            "Склади коротку готову відповідь адміністратору українською мовою. "
            "Відповідь має бути придатною для вставки в PM."
        )

    @staticmethod
    def normalize_answer(text: str, admin_nickname: str = "") -> str:
        answer = normalize_space(text.strip().strip('"').strip("'"))
        if not answer:
            return REPORT_GENERIC_FALLBACK_TEXT
        if not answer.startswith(("Вітаю!", "Вітаю,", "Дізнайтесь")):
            answer = f"Вітаю! {answer[0].upper()}{answer[1:]}" if answer else "Вітаю!"
        nickname = admin_nickname.strip()
        if nickname:
            answer = re.sub(r'["«“”]?Нік["»“”]?', nickname, answer, flags=re.IGNORECASE)
        return answer


class SharedAIService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._responder: AIReportResponder | None = None
        self._report_backend = AiAsistBridge()
        self._prepared = False
        self._warmup_started = False
        self._report_cache: dict[tuple[str, str], GeneratedAIReply] = {}
        self._report_text_cache: dict[tuple[str, str], GeneratedAIReply] = {}
        self._vip_cache: dict[str, VipAdDecision] = {}

    def prepare(self) -> None:
        with self._lock:
            if self._prepared:
                return
            try:
                self._report_backend.prepare()
            except Exception:
                pass
            self._prepared = True

    def prepare_async(self) -> None:
        with self._lock:
            if self._prepared or self._warmup_started:
                return
            self._warmup_started = True

        def worker() -> None:
            try:
                self.prepare()
            except Exception:
                pass
            finally:
                with self._lock:
                    self._warmup_started = False

        threading.Thread(
            target=worker,
            name="richcore-ai-warmup",
            daemon=True,
        ).start()

    def generate_report_reply(
        self,
        report_key: str,
        report: Report,
        *,
        admin_nickname: str = "",
    ) -> GeneratedAIReply:
        nickname_key = admin_nickname.strip()
        cache_key = (report_key, nickname_key)
        text_cache_key = (normalize_report_lookup_text(report.text.strip()), nickname_key)
        with self._lock:
            cached = self._report_cache.get(cache_key)
            if cached is not None:
                return cached
            if text_cache_key[0]:
                text_cached = self._report_text_cache.get(text_cache_key)
                if text_cached is not None:
                    self._report_cache[cache_key] = text_cached
                    return text_cached

            try:
                backend_reply = self._report_backend.generate_reply_details(report.text.strip())
            except Exception as exc:
                raise RuntimeError(f"AiAsist reply backend failed: {exc}") from exc

            generated = GeneratedAIReply(
                text=AIReportResponder.normalize_answer(backend_reply.text, admin_nickname=admin_nickname),
                model_name="AiAsist",
                key_index=1,
                context_preview="Внутрішній модуль відповіді",
            )

            self._report_cache[cache_key] = generated
            if text_cache_key[0]:
                self._report_text_cache[text_cache_key] = generated
            return generated

    def classify_vip_messages(self, messages: Sequence[VipChatMessage]) -> list[VipAdDecision]:
        if not messages:
            return []

        with self._lock:
            self.prepare()

            decisions_by_position: list[VipAdDecision | None] = [None] * len(messages)
            uncached_messages: list[VipChatMessage] = []
            uncached_positions: list[int] = []

            for index, message in enumerate(messages):
                cache_key = self._vip_cache_key(message)
                cached = self._vip_cache.get(cache_key)
                if cached is not None:
                    decisions_by_position[index] = cached
                    continue
                uncached_messages.append(message)
                uncached_positions.append(index)

            if uncached_messages:
                responder = self._vip_responder()
                fresh_decisions = responder.classify_vip_messages(uncached_messages)
                for position, message, decision in zip(uncached_positions, uncached_messages, fresh_decisions):
                    self._vip_cache[self._vip_cache_key(message)] = decision
                    decisions_by_position[position] = decision

            return [
                decision if decision is not None else VipAdDecision(False, "Інформаційне питання")
                for decision in decisions_by_position
            ]

    def _vip_responder(self) -> AIReportResponder:
        if self._responder is None:
            self._responder = AIReportResponder()
        return self._responder

    @staticmethod
    def _vip_cache_key(message: VipChatMessage) -> str:
        return normalize_space(message.text.casefold())

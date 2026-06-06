from __future__ import annotations

import re


_LOOKALIKE_TRANSLATION = str.maketrans(
    {
        "a": "а",
        "e": "е",
        "o": "о",
        "p": "р",
        "c": "с",
        "x": "х",
        "y": "у",
        "k": "к",
        "m": "м",
        "t": "т",
        "b": "в",
        "h": "н",
        "i": "і",
        "ё": "е",
        "ъ": "ь",
    }
)

_EXACT_TERMS = {
    "блядь",
    "блять",
    "блядина",
    "гандон",
    "гондон",
    "дебіл",
    "дебил",
    "довбойоб",
    "долбоеб",
    "долбойоб",
    "ідіот",
    "идиот",
    "кончений",
    "лох",
    "мразь",
    "падла",
    "підар",
    "підор",
    "пидар",
    "пидор",
    "педик",
    "сучка",
    "сука",
    "тварь",
    "уебан",
    "уебище",
    "уїбан",
    "уїбище",
    "урод",
    "хуйло",
    "хуесос",
    "хуєсос",
    "чмо",
    "шалава",
    "шлюха",
}

_ROOT_TRIGGERS = (
    "бляд",
    "блять",
    "гандон",
    "гондон",
    "долбоеб",
    "довбойоб",
    "йобан",
    "йобнут",
    "кончен",
    "пизд",
    "пізд",
    "пидор",
    "підор",
    "уеб",
    "уебан",
    "уебищ",
    "уєб",
    "уїб",
    "хуй",
    "хуя",
    "хуе",
    "хує",
    "херн",
    "шалав",
    "шлюх",
)

_TOKEN_RE = re.compile(r"[0-9a-zа-яіїєґёъ]+", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    return text.casefold().translate(_LOOKALIKE_TRANSLATION)


def find_offensive_triggers(text: str, *, limit: int = 3) -> tuple[str, ...]:
    normalized = _normalize_text(text)
    tokens = _TOKEN_RE.findall(normalized)
    compact = "".join(tokens)
    matches: list[str] = []

    def add(value: str) -> None:
        if value and value not in matches:
            matches.append(value)

    for token in tokens:
        if token in _EXACT_TERMS:
            add(token)
        for root in _ROOT_TRIGGERS:
            if root in token and len(token) <= max(16, len(root) + 8):
                add(root)

    spaced_letters = len(tokens) >= 3 and all(len(token) <= 2 for token in tokens)
    if spaced_letters or len(compact) <= 48:
        for root in _ROOT_TRIGGERS:
            if root in compact:
                add(root)

    return tuple(matches[:limit])

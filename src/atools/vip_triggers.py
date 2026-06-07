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
    "аутист",
    "блядь",
    "блять",
    "блядина",
    "виродок",
    "гандон",
    "гівно",
    "гнида",
    "говно",
    "гондон",
    "дебіл",
    "дебил",
    "дегенерат",
    "дірка",
    "довбойоб",
    "долбоеб",
    "долбойоб",
    "дурак",
    "дурень",
    "засранець",
    "ідіот",
    "идиот",
    "імбецил",
    "кончений",
    "кретин",
    "лох",
    "мразота",
    "мразь",
    "нікчема",
    "ничтожество",
    "падла",
    "падлюка",
    "підар",
    "підор",
    "пидар",
    "пидор",
    "покидьок",
    "педик",
    "сволота",
    "срака",
    "сраний",
    "сраный",
    "сучка",
    "сука",
    "тупа",
    "тупе",
    "тупий",
    "тупой",
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
    "гівн",
    "гнид",
    "говн",
    "гондон",
    "дебіл",
    "дебил",
    "дегенерат",
    "долбоеб",
    "довбойоб",
    "дурак",
    "дурн",
    "єба",
    "єбе",
    "єби",
    "єбу",
    "йобан",
    "йобнут",
    "ідіот",
    "идиот",
    "кончен",
    "кончен",
    "кретин",
    "мраз",
    "нікчем",
    "ничтож",
    "падл",
    "падлюк",
    "пизд",
    "пізд",
    "підар",
    "пидор",
    "підор",
    "покидь",
    "сволот",
    "срак",
    "сран",
    "суч",
    "тупа",
    "тупе",
    "тупи",
    "тупо",
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

_INSULT_ROOTS = (
    "аутист",
    "вирод",
    "гнид",
    "дебіл",
    "дебил",
    "дегенерат",
    "довбойоб",
    "долбоеб",
    "долбойоб",
    "дурак",
    "дурн",
    "ідіот",
    "идиот",
    "імбецил",
    "кончен",
    "кретин",
    "лох",
    "мраз",
    "нікчем",
    "ничтож",
    "падл",
    "падлюк",
    "покидь",
    "сволот",
    "твар",
    "тупа",
    "тупе",
    "тупи",
    "тупо",
    "урод",
    "чмо",
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


def offensive_reason_kind(text: str) -> str:
    matches = find_offensive_triggers(text, limit=8)
    if any(any(root in match for root in _INSULT_ROOTS) for match in matches):
        return "insult"
    return "profanity" if matches else ""

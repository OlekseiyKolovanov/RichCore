from __future__ import annotations

import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE_URL = "https://ukraine-gta.com.ua"
DONATE_PAGE_URL = f"{BASE_URL}/uk/donate/"
PAYMENT_METHODS_URL = f"{BASE_URL}/ajax/payment-methods"
DONATE_CHECK_URL = f"{BASE_URL}/ajax/donate-check"

SERVER_NAME = "Західна Україна"
DEFAULT_AMOUNT = "1"

PAYMENT_ALIASES = {
    "ukraine": "ukraine",
    "ua": "ukraine",
    "visa": "ukraine",
    "mastercard": "ukraine",
    "europe": "europe",
    "eu": "europe",
}


class PlayerLookupError(RuntimeError):
    def __init__(self, message: str, *, site_message: bool = False) -> None:
        super().__init__(message)
        self.site_message = site_message


@dataclass(frozen=True, slots=True)
class PlayerLookupResult:
    input_value: str
    input_type: str
    nickname: str
    player_id: int
    server: int
    payment_method: str
    amount: str


def build_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def request_json(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    data: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": DONATE_PAGE_URL,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }

    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if data else "GET")

    try:
        with opener.open(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise PlayerLookupError(f"HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise PlayerLookupError(f"Не вдалося підключитися до сайту: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PlayerLookupError(f"Сайт повернув не JSON-відповідь: {raw[:300]}") from exc


def format_site_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, ensure_ascii=False)


def warm_up_site(opener: urllib.request.OpenerDirector) -> None:
    request = urllib.request.Request(
        DONATE_PAGE_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            ),
        },
    )
    try:
        with opener.open(request, timeout=30) as response:
            response.read(1024)
    except urllib.error.URLError as exc:
        raise PlayerLookupError(f"Не вдалося відкрити сторінку донату: {exc.reason}") from exc


def normalize_payment_method(value: str) -> str:
    key = value.strip().lower()
    if key not in PAYMENT_ALIASES:
        supported = ", ".join(sorted(PAYMENT_ALIASES))
        raise PlayerLookupError(f"Невідомий спосіб оплати '{value}'. Доступно: {supported}")
    return PAYMENT_ALIASES[key]


def ensure_payment_method_available(opener: urllib.request.OpenerDirector, payment_method: str) -> None:
    response = request_json(opener, PAYMENT_METHODS_URL)
    if response.get("result") != "success":
        raise PlayerLookupError(format_site_detail(response.get("detail") or response), site_message=True)

    methods = response.get("detail", {}).get("payments_methods", [])
    if not any(method.get("id") == payment_method for method in methods):
        available = ", ".join(method.get("id", "?") for method in methods)
        raise PlayerLookupError(f"Спосіб оплати '{payment_method}' зараз недоступний. Доступно: {available}")


def lookup_player(
    identifier: str,
    *,
    payment_method: str = "ukraine",
    amount: str = DEFAULT_AMOUNT,
) -> PlayerLookupResult:
    clean_identifier = identifier.strip()
    if not clean_identifier:
        raise PlayerLookupError("Передай ID або нікнейм гравця.")

    normalized_payment_method = normalize_payment_method(payment_method)
    input_type = "id" if clean_identifier.isdigit() else "nickname"

    opener = build_opener()
    warm_up_site(opener)
    ensure_payment_method_available(opener, normalized_payment_method)

    payload = {
        "donate-form-payment-method": normalized_payment_method,
        "donate-form-login": clean_identifier,
        "donate-form-server": SERVER_NAME,
        "donate-form-terms": "1",
        "donate-form-amount": amount,
    }

    response = request_json(opener, DONATE_CHECK_URL, data=payload)
    if response.get("result") != "success":
        detail = response.get("detail") or response
        raise PlayerLookupError(format_site_detail(detail), site_message=True)

    detail = response.get("detail") or {}
    try:
        nickname = str(detail["nickname"])
        player_id = int(detail["player_id"])
        server = int(detail["server"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PlayerLookupError(
            f"Сайт повернув відповідь без ID/нікнейму: {format_site_detail(response)}",
            site_message=True,
        ) from exc

    return PlayerLookupResult(
        input_value=clean_identifier,
        input_type=input_type,
        nickname=nickname,
        player_id=player_id,
        server=server,
        payment_method=normalized_payment_method,
        amount=amount,
    )

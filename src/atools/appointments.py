from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .paths import config_dir


CONFIG_PATH = config_dir() / "appointments_config.json"

DEFAULT_OWNER = "UKRAINE-GTA-02"
DEFAULT_LEADERS_PROJECT = 17
DEFAULT_DEPUTIES_PROJECT = 9
DEFAULT_WATCHERS_PROJECT = 7
DEFAULT_APPS_SCRIPT_URL = (
    "https://script.google.com/macros/s/AKfycbwsD6Vkn8MEODhkt3awKnEOSV8AfENBav5nUIJAT64LuDJjF5YGHpeH8JmockkLTxLA/exec, "
    "https://script.google.com/macros/s/AKfycbw49OT54UCcV0ygan9fMoZKt7997EYcF1D-EM88e0hWybkuL9gMElfEqkCTfGWjuw9M/exec"
)
DEFAULT_GITHUB_TOKEN = ""

ROLE_LEADER = "leader"
ROLE_DEPUTY = "deputy"
ROLE_WATCHER = "watcher"

ACTION_APPOINT = "appoint"
ACTION_REMOVE = "remove"


@dataclass(slots=True)
class AppointmentConfig:
    apps_script_url: str = DEFAULT_APPS_SCRIPT_URL
    github_token: str = DEFAULT_GITHUB_TOKEN
    github_owner: str = DEFAULT_OWNER
    leaders_project: int = DEFAULT_LEADERS_PROJECT
    deputies_project: int = DEFAULT_DEPUTIES_PROJECT
    watchers_project: int = DEFAULT_WATCHERS_PROJECT
    approved_status_options: list[str] = field(
        default_factory=lambda: ["Призначений", "Призначено", "Активний", "Active", "Done", "Готово"]
    )
    removed_status_options: list[str] = field(
        default_factory=lambda: ["Знятий", "Знято", "Removed", "Inactive", "Done", "Готово"]
    )


@dataclass(slots=True)
class AppointmentRecord:
    uid: str
    source_key: str
    source_label: str
    sheet_id: str
    sheet_name: str
    row_number: int
    action: str
    role: str
    role_label: str
    nickname: str
    player_id: str
    position: str
    faction: str
    appoint_date: str
    telegram: str
    discord: str
    forum_url: str
    email: str
    two_fa_url: str
    row_color: str = ""
    script_url: str = ""
    github_item_id: str = ""
    status: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_removal(self) -> bool:
        return self.action == ACTION_REMOVE

    @property
    def rank_level(self) -> int | None:
        if self.role == ROLE_LEADER:
            return 12
        if self.role == ROLE_DEPUTY:
            return 11
        return None

    @property
    def position_title(self) -> str:
        parts = [self.role_label or self.position, self.faction]
        return " ".join(part for part in parts if part).strip()

    @property
    def telegram_tag(self) -> str:
        value = self.telegram.strip()
        if value and not value.startswith("@") and re.fullmatch(r"[A-Za-z0-9_]{3,64}", value):
            return f"@{value}"
        return value


@dataclass(slots=True)
class AppointmentActionResult:
    ok: bool
    message: str
    github_item_id: str = ""


class AppointmentError(RuntimeError):
    pass


def load_appointment_config() -> AppointmentConfig:
    if not CONFIG_PATH.exists():
        return AppointmentConfig()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return AppointmentConfig()
    config = AppointmentConfig()
    for key in asdict(config):
        if key in raw:
            setattr(config, key, raw[key])
    config.leaders_project = _to_int(config.leaders_project, DEFAULT_LEADERS_PROJECT)
    config.deputies_project = _to_int(config.deputies_project, DEFAULT_DEPUTIES_PROJECT)
    config.watchers_project = _to_int(config.watchers_project, DEFAULT_WATCHERS_PROJECT)
    return config


def save_appointment_config(config: AppointmentConfig) -> None:
    CONFIG_PATH.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_appointment_record(payload: dict[str, Any]) -> AppointmentRecord:
    role = _normalize_role(str(payload.get("role") or payload.get("position") or ""))
    if role == ROLE_DEPUTY:
        role_label = "Заступник"
    elif role == ROLE_LEADER:
        role_label = "Лідер"
    else:
        role_label = "Слідкуючий"

    row_number = _to_int(payload.get("rowNumber") or payload.get("row_number"), 0)
    source_key = str(payload.get("sourceKey") or payload.get("source_key") or "")
    uid = str(payload.get("uid") or f"{source_key}:{row_number}")
    action = str(payload.get("action") or ACTION_APPOINT).strip().casefold()
    if action not in {ACTION_APPOINT, ACTION_REMOVE}:
        action = ACTION_APPOINT

    return AppointmentRecord(
        uid=uid,
        source_key=source_key,
        source_label=str(payload.get("sourceLabel") or payload.get("source_label") or source_key),
        sheet_id=str(payload.get("sheetId") or payload.get("sheet_id") or ""),
        sheet_name=str(payload.get("sheetName") or payload.get("sheet_name") or ""),
        row_number=row_number,
        action=action,
        role=role,
        role_label=str(payload.get("roleLabel") or payload.get("role_label") or role_label),
        nickname=str(payload.get("nickname") or ""),
        player_id=str(payload.get("playerId") or payload.get("player_id") or ""),
        position=str(payload.get("position") or ""),
        faction=str(payload.get("faction") or payload.get("organization") or ""),
        appoint_date=str(payload.get("appointDate") or payload.get("appoint_date") or ""),
        telegram=str(payload.get("telegram") or ""),
        discord=str(payload.get("discord") or ""),
        forum_url=str(payload.get("forumUrl") or payload.get("forum_url") or ""),
        email=str(payload.get("email") or ""),
        two_fa_url=str(payload.get("twoFaUrl") or payload.get("two_fa_url") or ""),
        row_color=str(payload.get("rowColor") or payload.get("row_color") or ""),
        script_url=str(payload.get("scriptUrl") or payload.get("script_url") or ""),
        github_item_id=str(payload.get("githubItemId") or payload.get("github_item_id") or ""),
        status=str(payload.get("status") or ""),
        raw=payload,
    )


def project_number_for_record(config: AppointmentConfig, record: AppointmentRecord) -> int:
    if record.role == ROLE_LEADER:
        return int(config.leaders_project)
    if record.role == ROLE_DEPUTY:
        return int(config.deputies_project)
    return int(config.watchers_project)


class AppsScriptClient:
    def __init__(self, config: AppointmentConfig) -> None:
        self._config = config

    def fetch_pending(self) -> list[AppointmentRecord]:
        records: list[AppointmentRecord] = []
        for url in self._script_urls():
            payload = self._post({"action": "pending"}, url=url)
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise AppointmentError("Apps Script повернув некоректний список заявок")
            for item in items:
                if not isinstance(item, dict):
                    continue
                item["scriptUrl"] = url
                records.append(parse_appointment_record(item))
        return records

    def mark_row(
        self,
        record: AppointmentRecord,
        status: str,
        *,
        note: str = "",
        github_item_id: str = "",
    ) -> None:
        self._post(
            {
                "action": "mark",
                "sourceKey": record.source_key,
                "sheetId": record.sheet_id,
                "sheetName": record.sheet_name,
                "rowNumber": record.row_number,
                "status": status,
                "note": note,
                "githubItemId": github_item_id,
            },
            url=record.script_url or None,
        )

    def _script_urls(self) -> list[str]:
        raw = self._config.apps_script_url.strip()
        urls = [part.strip() for part in re.split(r"[\n,;]+", raw) if part.strip()]
        return urls

    def _post(self, body: dict[str, Any], *, url: str | None = None) -> dict[str, Any]:
        target_url = (url or (self._script_urls()[0] if self._script_urls() else "")).strip()
        if not target_url:
            raise AppointmentError("Вкажіть URL Google Apps Script")
        payload = dict(body)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            target_url,
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "RichCore-Appointments",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise AppointmentError(f"Apps Script HTTP {exc.code}: {details or exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001
            raise AppointmentError(f"Не вдалося звернутися до Apps Script: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppointmentError(f"Apps Script повернув не JSON: {raw[:200]}") from exc
        if not payload.get("ok"):
            raise AppointmentError(str(payload.get("error") or "Apps Script повернув помилку"))
        return payload


class GitHubProjectsClient:
    GRAPHQL_URL = "https://api.github.com/graphql"

    def __init__(self, config: AppointmentConfig) -> None:
        self._config = config
        self._projects: dict[int, dict[str, Any]] = {}

    def apply_status(self, record: AppointmentRecord, status: str) -> str:
        project_number = project_number_for_record(self._config, record)
        project = self._project(project_number)
        item_id = record.github_item_id or self._find_existing_item(project, record)
        if not item_id:
            item_id = self._create_draft_item(project["id"], record, status)
        self._update_known_fields(project, item_id, record, status)
        return item_id

    def _project(self, number: int) -> dict[str, Any]:
        if number in self._projects:
            return self._projects[number]

        query = """
        query($owner: String!, $number: Int!) {
          organization(login: $owner) {
            projectV2(number: $number) {
              id
              title
              fields(first: 100) {
                nodes {
                  __typename
                  ... on ProjectV2Field {
                    id
                    name
                    dataType
                  }
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    dataType
                    options {
                      id
                      name
                    }
                  }
                  ... on ProjectV2IterationField {
                    id
                    name
                    dataType
                  }
                }
              }
            }
          }
        }
        """
        payload = self._graphql(query, {"owner": self._config.github_owner, "number": number})
        project = (((payload.get("data") or {}).get("organization") or {}).get("projectV2") or None)
        if not project:
            raise AppointmentError(f"GitHub Project #{number} не знайдено або немає доступу")
        fields = project.get("fields", {}).get("nodes", []) or []
        project["field_map"] = {str(field.get("name", "")).casefold(): field for field in fields if field}
        self._projects[number] = project
        return project

    def _create_draft_item(self, project_id: str, record: AppointmentRecord, status: str) -> str:
        query = """
        mutation($projectId: ID!, $title: String!, $body: String!) {
          addProjectV2DraftIssue(input: {projectId: $projectId, title: $title, body: $body}) {
            projectItem {
              id
            }
          }
        }
        """
        payload = self._graphql(
            query,
            {
                "projectId": project_id,
                "title": _github_title(record, status),
                "body": _github_body(record, status),
            },
        )
        item = (((payload.get("data") or {}).get("addProjectV2DraftIssue") or {}).get("projectItem") or {})
        item_id = str(item.get("id") or "")
        if not item_id:
            raise AppointmentError("GitHub не повернув ID створеної картки")
        return item_id

    def _find_existing_item(self, project: dict[str, Any], record: AppointmentRecord) -> str:
        needle_id = record.player_id.strip()
        needle_name = record.nickname.strip().casefold()
        if not needle_id and not needle_name:
            return ""

        query = """
        query($projectId: ID!, $cursor: String) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: 100, after: $cursor) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  content {
                    __typename
                    ... on DraftIssue {
                      title
                      body
                    }
                    ... on Issue {
                      title
                      body
                      url
                    }
                    ... on PullRequest {
                      title
                      body
                      url
                    }
                  }
                  fieldValues(first: 50) {
                    nodes {
                      __typename
                      ... on ProjectV2ItemFieldTextValue {
                        text
                        field {
                          ... on ProjectV2FieldCommon {
                            name
                          }
                        }
                      }
                      ... on ProjectV2ItemFieldNumberValue {
                        number
                        field {
                          ... on ProjectV2FieldCommon {
                            name
                          }
                        }
                      }
                      ... on ProjectV2ItemFieldDateValue {
                        date
                        field {
                          ... on ProjectV2FieldCommon {
                            name
                          }
                        }
                      }
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field {
                          ... on ProjectV2FieldCommon {
                            name
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        cursor = None
        checked = 0
        while checked < 500:
            payload = self._graphql(query, {"projectId": project["id"], "cursor": cursor})
            items = ((((payload.get("data") or {}).get("node") or {}).get("items") or {}))
            nodes = items.get("nodes", []) or []
            for node in nodes:
                checked += 1
                haystack = _item_haystack(node)
                if needle_id and re.search(rf"(?<!\d){re.escape(needle_id)}(?!\d)", haystack):
                    return str(node.get("id") or "")
                if needle_name and needle_name in haystack.casefold():
                    return str(node.get("id") or "")
            page_info = items.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
        return ""

    def _update_known_fields(self, project: dict[str, Any], item_id: str, record: AppointmentRecord, status: str) -> None:
        for field in project.get("fields", {}).get("nodes", []) or []:
            if not field:
                continue
            field_name = str(field.get("name") or "")
            value = _value_for_project_field(field_name, record)
            if _is_status_field(field_name):
                option_id = _select_status_option(field, self._status_candidates(status))
                if option_id:
                    self._update_item_field(project["id"], item_id, field["id"], {"singleSelectOptionId": option_id})
                continue
            if not value:
                continue
            data_type = str(field.get("dataType") or "").upper()
            if data_type == "DATE":
                date_value = _date_to_iso(value)
                if date_value:
                    self._update_item_field(project["id"], item_id, field["id"], {"date": date_value})
            elif data_type in {"TEXT", "TITLE"}:
                self._update_item_field(project["id"], item_id, field["id"], {"text": value[:1024]})
            elif data_type == "NUMBER" and value.strip().isdigit():
                self._update_item_field(project["id"], item_id, field["id"], {"number": float(value.strip())})

    def _status_candidates(self, status: str) -> list[str]:
        if status == "removed":
            return self._config.removed_status_options
        return self._config.approved_status_options

    def _update_item_field(self, project_id: str, item_id: str, field_id: str, value: dict[str, Any]) -> None:
        query = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $value: ProjectV2FieldValue!) {
          updateProjectV2ItemFieldValue(
            input: {projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: $value}
          ) {
            projectV2Item {
              id
            }
          }
        }
        """
        self._graphql(query, {"projectId": project_id, "itemId": item_id, "fieldId": field_id, "value": value})

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        token = self._config.github_token.strip()
        if not token:
            raise AppointmentError("Вкажіть GitHub token")
        request = urllib.request.Request(
            self.GRAPHQL_URL,
            data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "RichCore-Appointments",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise AppointmentError(f"GitHub HTTP {exc.code}: {details or exc.reason}") from exc
        except Exception as exc:  # noqa: BLE001
            raise AppointmentError(f"Не вдалося звернутися до GitHub: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppointmentError(f"GitHub повернув не JSON: {raw[:200]}") from exc
        if payload.get("errors"):
            first = payload["errors"][0]
            raise AppointmentError(str(first.get("message") or first))
        return payload


class AppointmentService:
    def __init__(self, config: AppointmentConfig) -> None:
        self._config = config
        self._apps = AppsScriptClient(config)
        self._github = GitHubProjectsClient(config)

    def fetch_pending(self) -> list[AppointmentRecord]:
        return self._apps.fetch_pending()

    def approve(self, record: AppointmentRecord, note: str = "") -> AppointmentActionResult:
        item_id = self._github.apply_status(record, "appointed")
        self._apps.mark_row(record, "appointed", note=note, github_item_id=item_id)
        return AppointmentActionResult(True, "Призначення записано в GitHub і Google Sheets", item_id)

    def reject(self, record: AppointmentRecord, note: str = "") -> AppointmentActionResult:
        self._apps.mark_row(record, "rejected", note=note, github_item_id=record.github_item_id)
        return AppointmentActionResult(True, "Заявку позначено як відхилену", record.github_item_id)

    def remove(self, record: AppointmentRecord, note: str = "") -> AppointmentActionResult:
        item_id = self._github.apply_status(record, "removed")
        self._apps.mark_row(record, "removed", note=note, github_item_id=item_id)
        return AppointmentActionResult(True, "Зняття записано в GitHub і Google Sheets", item_id)


def _normalize_role(value: str) -> str:
    normalized = value.strip().casefold()
    if "заст" in normalized or "зам" in normalized or "deput" in normalized:
        return ROLE_DEPUTY
    if "лід" in normalized or "лид" in normalized or "leader" in normalized:
        return ROLE_LEADER
    return ROLE_WATCHER


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _github_title(record: AppointmentRecord, status: str) -> str:
    if status == "removed":
        return f"{record.nickname} [{record.player_id}] - знятий з посади {record.position_title}".strip()
    return f"{record.nickname} [{record.player_id}] - {record.position_title}".strip()


def _github_body(record: AppointmentRecord, status: str) -> str:
    status_label = "Знятий" if status == "removed" else "Призначений"
    lines = [
        f"Статус: {status_label}",
        "",
        f"NickName: {record.nickname}",
        f"ID: {record.player_id}",
        f"Посада: {record.position_title}",
        f"Дата призначення: {record.appoint_date}",
        f"Telegram: {record.telegram_tag}",
        f"Discord: {record.discord}",
        f"Форум: {record.forum_url}",
        f"Email: {record.email}",
        f"2FA: {record.two_fa_url}",
        "",
        f"Джерело: {record.source_label}, рядок {record.row_number}",
    ]
    return "\n".join(lines)


def _item_haystack(node: dict[str, Any]) -> str:
    parts: list[str] = []
    content = node.get("content") or {}
    parts.append(str(content.get("title") or ""))
    parts.append(str(content.get("body") or ""))
    for field_value in ((node.get("fieldValues") or {}).get("nodes") or []):
        for key in ("text", "number", "date", "name"):
            if key in field_value and field_value[key] is not None:
                parts.append(str(field_value[key]))
    return "\n".join(parts)


def _field_key(value: str) -> str:
    return re.sub(r"[^a-zа-яіїєґ0-9]+", "", value.casefold())


def _is_status_field(field_name: str) -> bool:
    key = _field_key(field_name)
    return key in {"status", "статус"} or "status" in key or "статус" in key


def _value_for_project_field(field_name: str, record: AppointmentRecord) -> str:
    key = _field_key(field_name)
    if "nick" in key or "нік" in key:
        return record.nickname
    if key == "id" or "playerid" in key or "айді" in key:
        return record.player_id
    if "посад" in key or "position" in key:
        return record.position_title
    if "фрак" in key or "орган" in key or "org" in key:
        return record.faction
    if "telegram" in key or "телег" in key:
        return record.telegram_tag
    if "discord" in key:
        return record.discord
    if "forum" in key or "форум" in key:
        return record.forum_url
    if "email" in key or "mail" in key or "пошт" in key:
        return record.email
    if "2fa" in key or "двохфактор" in key:
        return record.two_fa_url
    if "дат" in key or "date" in key:
        return record.appoint_date
    return ""


def _select_status_option(field: dict[str, Any], candidates: list[str]) -> str:
    options = field.get("options") or []
    normalized_candidates = [_field_key(candidate) for candidate in candidates]
    for option in options:
        option_name = str(option.get("name") or "")
        option_key = _field_key(option_name)
        if option_key in normalized_candidates:
            return str(option.get("id") or "")
    for option in options:
        option_key = _field_key(str(option.get("name") or ""))
        if any(candidate in option_key or option_key in candidate for candidate in normalized_candidates):
            return str(option.get("id") or "")
    return ""


def _date_to_iso(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    for fmt in ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if not match:
        return ""
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day)).date().isoformat()
    except ValueError:
        return ""

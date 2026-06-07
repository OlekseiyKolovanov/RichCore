from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .paths import app_root_dir, config_dir, legacy_appdata_dir


CONFIG_PATH = config_dir() / "appointments_config.json"
GITHUB_TOKEN_ENV = "RICHCORE_GITHUB_TOKEN"

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


def _initial_field_key(value: str) -> str:
    return re.sub(r"[^a-zа-яіїєґ0-9]+", "", value.casefold())


@dataclass(frozen=True, slots=True)
class FactionInfo:
    code: str
    faction_id: int
    full_name: str
    ministry: str


FACTIONS: dict[str, FactionInfo] = {
    "ЗСУ": FactionInfo("ЗСУ", 1, "Збройні сили України", "Міністерство оборони"),
    "СБУ": FactionInfo("СБУ", 2, "Служба Безпеки України", "Міністерство внутрішніх справ"),
    "НПУ": FactionInfo("НПУ", 3, "Національна Поліція України", "Міністерство внутрішніх справ"),
    "МОЗ": FactionInfo("МОЗ", 4, "Міністерство Охорони Здоров'я", "Міністерство цивільних організацій"),
    "ВРУ": FactionInfo("ВРУ", 7, "Верховна Рада України", "Міністерство цивільних організацій"),
    "ДКВС": FactionInfo("ДКВС", 9, "Державна кримінально-виконавча служба", "Міністерство юстиції"),
    "ДСНС": FactionInfo("ДСНС", 10, "Державна Служба з Надзвичайних Ситуацій", "Міністерство внутрішніх справ"),
    "ЗМІ": FactionInfo("ЗМІ", 11, "Засоби Масової Інформації", "Міністерство цивільних організацій"),
    "УЗ": FactionInfo("УЗ", 12, "Укрзалізниця", "Міністерство цивільних організацій"),
}

FULL_NAME_TO_CODE = {_initial_field_key(info.full_name): code for code, info in FACTIONS.items()}


@dataclass(slots=True)
class AppointmentConfig:
    apps_script_url: str = DEFAULT_APPS_SCRIPT_URL
    github_token: str = DEFAULT_GITHUB_TOKEN
    github_owner: str = DEFAULT_OWNER
    leaders_project: int = DEFAULT_LEADERS_PROJECT
    deputies_project: int = DEFAULT_DEPUTIES_PROJECT
    watchers_project: int = DEFAULT_WATCHERS_PROJECT
    approved_status_options: list[str] = field(default_factory=lambda: ["Дійсний", "Призначений", "Done"])
    removed_status_options: list[str] = field(default_factory=lambda: ["Недійсний", "Знятий з посади", "Знятий", "Done"])


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
    def faction_info(self) -> FactionInfo | None:
        return faction_info_from_value(self.faction)

    @property
    def organization_name(self) -> str:
        info = self.faction_info
        return info.full_name if info else self.faction.strip()

    @property
    def organization_tag(self) -> str:
        value = self.faction.strip()
        info = self.faction_info
        if info is None:
            return value

        value_key = _field_key(value)
        if not value_key:
            return info.code

        full_key = _field_key(info.full_name)
        ministry_key = _field_key(info.ministry)
        if value_key in {full_key, ministry_key}:
            return info.code
        return value or info.code

    @property
    def position_title(self) -> str:
        organization = self.organization_tag
        return f"{self.role_label} {organization}".strip()

    @property
    def telegram_tag(self) -> str:
        value = self.telegram.strip()
        if not value:
            return ""
        match = re.search(r"(?:t\.me/|telegram\.me/)([A-Za-z0-9_]{3,64})", value)
        if match:
            return f"@{match.group(1)}"
        if value.startswith("@"):
            return value
        if re.fullmatch(r"[A-Za-z0-9_]{3,64}", value):
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
    config = AppointmentConfig()
    raw = _read_config_payload(CONFIG_PATH)
    if raw:
        _merge_config_payload(config, raw)
    else:
        _merge_first_existing_config(config)
    _apply_github_token_fallback(config)
    config.leaders_project = _to_int(config.leaders_project, DEFAULT_LEADERS_PROJECT)
    config.deputies_project = _to_int(config.deputies_project, DEFAULT_DEPUTIES_PROJECT)
    config.watchers_project = _to_int(config.watchers_project, DEFAULT_WATCHERS_PROJECT)
    return config


def save_appointment_config(config: AppointmentConfig) -> None:
    CONFIG_PATH.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")


def _read_config_payload(path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _merge_config_payload(config: AppointmentConfig, raw: dict[str, Any], *, only_missing: bool = False) -> None:
    for key in asdict(config):
        if key not in raw:
            continue
        if only_missing and getattr(config, key):
            continue
        setattr(config, key, raw[key])


def _legacy_config_paths() -> tuple:
    app_root = app_root_dir()
    return (
        app_root.parent / "config" / "appointments_config.json",
        legacy_appdata_dir("RichCore") / "appointments_config.json",
        legacy_appdata_dir("Atools") / "appointments_config.json",
    )


def _merge_first_existing_config(config: AppointmentConfig) -> None:
    for path in _legacy_config_paths():
        raw = _read_config_payload(path)
        if raw:
            _merge_config_payload(config, raw, only_missing=True)
            return


def _apply_github_token_fallback(config: AppointmentConfig) -> None:
    env_token = os.environ.get(GITHUB_TOKEN_ENV, "").strip()
    if env_token:
        config.github_token = env_token
        return
    if config.github_token.strip():
        return
    for path in _legacy_config_paths():
        raw = _read_config_payload(path)
        token = str(raw.get("github_token") or "").strip()
        if token:
            config.github_token = token
            return


def parse_appointment_record(payload: dict[str, Any]) -> AppointmentRecord:
    role = _normalize_role(str(payload.get("role") or payload.get("position") or ""))
    role_label = _role_label(role)
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
        nickname=str(payload.get("nickname") or "").strip(),
        player_id=str(payload.get("playerId") or payload.get("player_id") or "").strip(),
        position=str(payload.get("position") or "").strip(),
        faction=str(payload.get("faction") or payload.get("organization") or "").strip(),
        appoint_date=str(payload.get("appointDate") or payload.get("appoint_date") or "").strip(),
        telegram=str(payload.get("telegram") or "").strip(),
        discord=str(payload.get("discord") or "").strip(),
        forum_url=str(payload.get("forumUrl") or payload.get("forum_url") or "").strip(),
        email=str(payload.get("email") or "").strip(),
        two_fa_url=str(payload.get("twoFaUrl") or payload.get("two_fa_url") or "").strip(),
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


def faction_info_from_value(value: str) -> FactionInfo | None:
    normalized = _field_key(value)
    for code, info in FACTIONS.items():
        if _field_key(code) == normalized or _field_key(code) in normalized:
            return info
    if normalized in FULL_NAME_TO_CODE:
        return FACTIONS[FULL_NAME_TO_CODE[normalized]]
    for key, code in FULL_NAME_TO_CODE.items():
        if key in normalized or normalized in key:
            return FACTIONS[code]
    return None


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
                if isinstance(item, dict):
                    item["scriptUrl"] = url
                    records.append(parse_appointment_record(item))
        return records

    def mark_row(self, record: AppointmentRecord, status: str, *, note: str = "", github_item_id: str = "") -> None:
        if not record.script_url or record.row_number <= 0:
            return
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
            url=record.script_url,
        )

    def _script_urls(self) -> list[str]:
        raw = self._config.apps_script_url.strip()
        return [part.strip() for part in re.split(r"[\n,;]+", raw) if part.strip()]

    def _post(self, body: dict[str, Any], *, url: str | None = None) -> dict[str, Any]:
        target_url = (url or (self._script_urls()[0] if self._script_urls() else "")).strip()
        if not target_url:
            raise AppointmentError("Apps Script URL не налаштовано")
        request = urllib.request.Request(
            target_url,
            data=json.dumps(dict(body), ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "RichCore-Appointments"},
            method="POST",
        )
        raw = ""
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=25) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                raise AppointmentError(f"Apps Script HTTP {exc.code}: {details or exc.reason}") from exc
            except Exception as exc:  # noqa: BLE001
                if attempt == 2:
                    raise AppointmentError(f"Не вдалося звернутися до Apps Script: {exc}") from exc
                time.sleep(0.6 * (attempt + 1))

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
        self._items_cache: dict[str, list[dict[str, Any]]] = {}

    def apply_status(self, record: AppointmentRecord, status: str, note: str = "") -> str:
        project_number = project_number_for_record(self._config, record)
        project = self._project(project_number)
        item_id = record.github_item_id or self._find_existing_item(project, record, status=status)
        if not item_id:
            item_id = self._create_draft_item(project["id"], record, status, note)
            self._items_cache.pop(project["id"], None)
        term_option = self._term_option(project, record, item_id)
        self._update_known_fields(project, item_id, record, status, note=note, term_option=term_option)
        return item_id

    def fetch_removal_candidates(self) -> list[AppointmentRecord]:
        records: list[AppointmentRecord] = []
        targets = (
            (self._config.leaders_project, ROLE_LEADER),
            (self._config.deputies_project, ROLE_DEPUTY),
            (self._config.watchers_project, ROLE_WATCHER),
        )
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(self._fetch_removal_candidates_for_project, int(number), role) for number, role in targets]
            for future in as_completed(futures):
                records.extend(future.result())
        records.sort(key=lambda item: (item.role_label, item.organization_name, item.nickname))
        return records

    def _fetch_removal_candidates_for_project(self, number: int, role: str) -> list[AppointmentRecord]:
        project = self._project(number)
        records: list[AppointmentRecord] = []
        for item in self._project_items(project):
            values = _field_values_from_item(item)
            if _item_is_removed(values):
                continue
            record = _record_from_project_item(project, item, role, number, values)
            if record is not None:
                records.append(record)
        return records

    def sync_active_terms(self) -> int:
        updated = 0
        for number, role in ((self._config.leaders_project, ROLE_LEADER), (self._config.deputies_project, ROLE_DEPUTY)):
            project = self._project(int(number))
            fields = _fields_by_key(project)
            term_field = _find_field(fields, ("кількістьтермінів",))
            if not term_field:
                continue
            for item in self._project_items(project):
                values = _field_values_from_item(item)
                if _item_is_removed(values):
                    continue
                record = _record_from_project_item(project, item, role, int(number), values)
                if record is None:
                    continue
                option = self._term_option(project, record, str(item.get("id") or ""))
                current = _value_by_field_key(values, "кількістьтермінів")
                if option and current != option:
                    option_id = _select_option(term_field, [option])
                    if option_id:
                        self._update_item_field(project["id"], item["id"], term_field["id"], {"singleSelectOptionId": option_id})
                        updated += 1
        return updated

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
        self._projects[number] = project
        return project

    def _project_items(self, project: dict[str, Any]) -> list[dict[str, Any]]:
        project_id = project["id"]
        if project_id in self._items_cache:
            return self._items_cache[project_id]

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
                  fieldValues(first: 100) {
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
        items: list[dict[str, Any]] = []
        cursor = None
        while True:
            payload = self._graphql(query, {"projectId": project_id, "cursor": cursor})
            page = ((((payload.get("data") or {}).get("node") or {}).get("items") or {}))
            items.extend(page.get("nodes", []) or [])
            page_info = page.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
        self._items_cache[project_id] = items
        return items

    def _create_draft_item(self, project_id: str, record: AppointmentRecord, status: str, note: str) -> str:
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
            {"projectId": project_id, "title": _github_title(record), "body": _github_body(record, status, note)},
        )
        item = (((payload.get("data") or {}).get("addProjectV2DraftIssue") or {}).get("projectItem") or {})
        item_id = str(item.get("id") or "")
        if not item_id:
            raise AppointmentError("GitHub не повернув ID створеної картки")
        return item_id

    def _find_existing_item(self, project: dict[str, Any], record: AppointmentRecord, *, status: str) -> str:
        needle_id = record.player_id.strip()
        needle_name = record.nickname.strip().casefold()
        if not needle_id and not needle_name:
            return ""
        for item in self._project_items(project):
            values = _field_values_from_item(item)
            if _item_is_removed(values):
                continue
            haystack = _item_haystack(item, values)
            if needle_id and re.search(rf"(?<!\d){re.escape(needle_id)}(?!\d)", haystack):
                return str(item.get("id") or "")
            if needle_name and needle_name in haystack.casefold():
                return str(item.get("id") or "")
        return ""

    def _term_option(self, project: dict[str, Any], record: AppointmentRecord, current_item_id: str = "") -> str:
        if record.role == ROLE_WATCHER:
            return ""
        count = 0
        for item in self._project_items(project):
            if current_item_id and str(item.get("id") or "") == current_item_id:
                continue
            values = _field_values_from_item(item)
            if _item_matches_player(item, values, record.player_id, record.nickname):
                count += 1
        return f"{max(1, min(count + 1, 3))}/3"

    def _update_known_fields(
        self,
        project: dict[str, Any],
        item_id: str,
        record: AppointmentRecord,
        status: str,
        *,
        note: str,
        term_option: str,
    ) -> None:
        for field in project.get("fields", {}).get("nodes", []) or []:
            if not field:
                continue
            update_value = _project_update_value(field, record, status, note=note, term_option=term_option)
            if update_value is None:
                continue
            self._update_item_field(project["id"], item_id, field["id"], update_value)

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
            raise AppointmentError("GitHub token не налаштований у runtime-конфігу")
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
        raw = ""
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=24) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                raise AppointmentError(f"GitHub HTTP {exc.code}: {details or exc.reason}") from exc
            except Exception as exc:  # noqa: BLE001
                if attempt == 1:
                    raise AppointmentError(f"Не вдалося звернутися до GitHub: {exc}") from exc
                time.sleep(0.8 * (attempt + 1))

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

    def fetch_form_queue(self) -> list[AppointmentRecord]:
        return _dedupe_records(self._apps.fetch_pending())

    def fetch_active_records(self) -> list[AppointmentRecord]:
        if not self._config.github_token.strip():
            return []
        return _dedupe_records(self._github.fetch_removal_candidates())

    def fetch_pending(self) -> list[AppointmentRecord]:
        records = self.fetch_form_queue()
        if self._config.github_token.strip():
            try:
                records.extend(self.fetch_active_records())
            except Exception:
                pass
        return _dedupe_records(records)

    def sync_terms(self) -> int:
        if not self._config.github_token.strip():
            return 0
        return self._github.sync_active_terms()

    def approve(self, record: AppointmentRecord, note: str = "") -> AppointmentActionResult:
        item_id = self._github.apply_status(record, "appointed", note)
        self._apps.mark_row(record, "appointed", note=note, github_item_id=item_id)
        return AppointmentActionResult(True, "Призначення записано в GitHub і Google Sheets", item_id)

    def reject(self, record: AppointmentRecord, note: str = "") -> AppointmentActionResult:
        self._apps.mark_row(record, "rejected", note=note, github_item_id=record.github_item_id)
        return AppointmentActionResult(True, "Заявку позначено як відхилену", record.github_item_id)

    def remove(self, record: AppointmentRecord, note: str = "") -> AppointmentActionResult:
        if not note.strip():
            raise AppointmentError("Вкажіть причину зняття")
        item_id = self._github.apply_status(record, "removed", note)
        self._apps.mark_row(record, "removed", note=note, github_item_id=item_id)
        return AppointmentActionResult(True, "Зняття записано в GitHub", item_id)

    def update_active(self, record: AppointmentRecord, note: str = "") -> AppointmentActionResult:
        item_id = self._github.apply_status(record, "appointed", note)
        return AppointmentActionResult(True, "Картку оновлено в GitHub", item_id)


def _project_update_value(
    field: dict[str, Any],
    record: AppointmentRecord,
    status: str,
    *,
    note: str,
    term_option: str,
) -> dict[str, Any] | None:
    name = str(field.get("name") or "")
    key = _field_key(name)
    data_type = str(field.get("dataType") or "").upper()
    if data_type in {"TITLE", "ASSIGNEES", "LABELS", "LINKED_PULL_REQUESTS", "MILESTONE", "REPOSITORY", "REVIEWERS", "PARENT_ISSUE", "SUB_ISSUES_PROGRESS", "CREATED", "UPDATED", "CLOSED"}:
        return None

    value = _raw_project_value(key, record, status, note=note, term_option=term_option)
    if value == "":
        return None
    if data_type == "SINGLE_SELECT":
        option_id = _select_option(field, [value])
        return {"singleSelectOptionId": option_id} if option_id else None
    if data_type == "NUMBER":
        number = _number_value(value)
        return {"number": number} if number is not None else None
    if data_type == "DATE":
        date_value = _date_to_iso(value)
        return {"date": date_value} if date_value else None
    if data_type == "TEXT":
        return {"text": str(value)[:1024]}
    return None


def _raw_project_value(key: str, record: AppointmentRecord, status: str, *, note: str, term_option: str) -> str:
    info = record.faction_info
    removed = status == "removed"
    if key == "status":
        return "Done"
    if key == "статус":
        return "Недійсний" if removed else "Дійсний"
    if key == "міністерство":
        if removed:
            return "Знятий з посади"
        if record.role == ROLE_DEPUTY:
            return info.ministry if info else ""
        if record.role == ROLE_WATCHER:
            return info.full_name if info else record.faction
        return ""
    if key == "посада":
        return "Слідкуючий" if record.role == ROLE_WATCHER else record.role_label
    if key == "idорганізації":
        return str(info.faction_id) if info else ""
    if key == "назваорганізації":
        return info.full_name if info else record.faction
    if key in {"idлідера", "idзастлідера", "idслідкуючого"} or key.startswith("idзаст"):
        return record.player_id
    if key == "датапризначення":
        return _normalize_date_text(record.appoint_date)
    if key == "мінтермін":
        days = 30 if record.role == ROLE_LEADER else 14 if record.role == ROLE_DEPUTY else 0
        return _date_plus_days(record.appoint_date, days) if days else ""
    if key == "кількістьтермінів":
        return term_option
    if key in {"попередження", "попередження"}:
        return "0/2"
    if key in {"суворихдоган", "догани"}:
        return "0/3"
    if key in {"збори", "присутність"}:
        return "Присутній"
    if key == "бали":
        return "0"
    if key == "telegram":
        return record.telegram_tag
    if key == "email":
        return record.email
    if key in {"фа", "форум"}:
        return record.forum_url
    if key in {"тегдіскорду", "discord"}:
        return record.discord
    if key == "знятий":
        return datetime.now().strftime("%d.%m.%Y") if removed else ""
    if key == "причиназняття":
        return note if removed else ""
    if key == "примітка":
        return note if note and not removed else ""
    return ""


def _record_from_project_item(
    project: dict[str, Any],
    item: dict[str, Any],
    role: str,
    project_number: int,
    values: dict[str, str],
) -> AppointmentRecord | None:
    content = item.get("content") or {}
    title = str(content.get("title") or _value_by_field_key(values, "title") or "").strip()
    player_id = (
        _value_by_field_key(values, "idлідера")
        or _value_by_field_key(values, "idзастлідера")
        or _value_by_field_key(values, "idслідкуючого")
    )
    faction_value = _value_by_field_key(values, "назваорганізації") or _value_by_field_key(values, "міністерство")
    info = faction_info_from_value(faction_value)
    faction = info.code if info else faction_value
    if not title and not player_id:
        return None
    role_label = _role_label(role)
    item_id = str(item.get("id") or "")
    return AppointmentRecord(
        uid=f"github:{project_number}:{item_id}",
        source_key=f"github:{project_number}",
        source_label=f"GitHub #{project_number}",
        sheet_id="",
        sheet_name=str(project.get("title") or ""),
        row_number=0,
        action=ACTION_REMOVE,
        role=role,
        role_label=role_label,
        nickname=title,
        player_id=_clean_number_text(player_id),
        position=role_label,
        faction=faction,
        appoint_date=_value_by_field_key(values, "датапризначення"),
        telegram=_value_by_field_key(values, "telegram"),
        discord=_value_by_field_key(values, "тегдіскорду"),
        forum_url=_value_by_field_key(values, "фа"),
        email=_value_by_field_key(values, "email"),
        two_fa_url="",
        github_item_id=item_id,
        status=_value_by_field_key(values, "статус") or _value_by_field_key(values, "міністерство"),
        raw={"project": project_number, "values": values},
    )


def _dedupe_records(records: list[AppointmentRecord]) -> list[AppointmentRecord]:
    result: list[AppointmentRecord] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        key = (record.action, record.role, record.player_id or record.nickname.casefold())
        if key in seen and record.source_key.startswith("github:"):
            continue
        seen.add(key)
        result.append(record)
    result.sort(key=lambda item: (0 if item.action == ACTION_APPOINT else 1, item.role_label, item.organization_name, item.nickname))
    return result


def _normalize_role(value: str) -> str:
    normalized = value.strip().casefold()
    if "заст" in normalized or "зам" in normalized or "deput" in normalized:
        return ROLE_DEPUTY
    if "лід" in normalized or "лид" in normalized or "leader" in normalized:
        return ROLE_LEADER
    return ROLE_WATCHER


def _role_label(role: str) -> str:
    if role == ROLE_LEADER:
        return "Лідер"
    if role == ROLE_DEPUTY:
        return "Заступник"
    return "Слідкуючий"


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number_value(value: str) -> float | None:
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_number_text(value: str) -> str:
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def _github_title(record: AppointmentRecord) -> str:
    return record.nickname.strip() or f"{record.role_label} {record.player_id}".strip()


def _github_body(record: AppointmentRecord, status: str, note: str) -> str:
    status_label = "Знятий" if status == "removed" else "Призначений"
    lines = [
        f"Статус: {status_label}",
        "",
        f"NickName: {record.nickname}",
        f"ID: {record.player_id}",
        f"Посада: {record.position_title}",
        f"ID організації: {record.faction_info.faction_id if record.faction_info else ''}",
        f"Назва організації: {record.organization_name}",
        f"Дата призначення: {_normalize_date_text(record.appoint_date)}",
        f"Мін. термін: {_date_plus_days(record.appoint_date, 30 if record.role == ROLE_LEADER else 14 if record.role == ROLE_DEPUTY else 0)}",
        f"Telegram: {record.telegram_tag}",
        f"Discord: {record.discord}",
        f"Ф.А.: {record.forum_url}",
        f"Email: {record.email}",
        f"2FA: {record.two_fa_url}",
    ]
    if note:
        lines.extend(("", f"Примітка: {note}"))
    if record.row_number:
        lines.extend(("", f"Джерело: {record.source_label}, рядок {record.row_number}"))
    return "\n".join(lines)


def _item_haystack(item: dict[str, Any], values: dict[str, str]) -> str:
    content = item.get("content") or {}
    parts = [str(content.get("title") or ""), str(content.get("body") or "")]
    parts.extend(values.values())
    return "\n".join(parts)


def _item_matches_player(item: dict[str, Any], values: dict[str, str], player_id: str, nickname: str) -> bool:
    haystack = _item_haystack(item, values)
    if player_id and re.search(rf"(?<!\d){re.escape(player_id)}(?!\d)", haystack):
        return True
    return bool(nickname and nickname.casefold() in haystack.casefold())


def _item_is_removed(values: dict[str, str]) -> bool:
    ministry = _field_key(_value_by_field_key(values, "міністерство"))
    status = _field_key(_value_by_field_key(values, "статус"))
    removed_date = _value_by_field_key(values, "знятий").strip()
    if "знятийзпосади" in ministry:
        return True
    if status == "недійсний":
        return True
    return bool(removed_date)


def _field_values_from_item(item: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    content = item.get("content") or {}
    if content.get("title"):
        values["title"] = str(content.get("title") or "")
    for field_value in ((item.get("fieldValues") or {}).get("nodes") or []):
        field_name = str(((field_value.get("field") or {}).get("name") or ""))
        if not field_name:
            continue
        value = field_value.get("text", field_value.get("number", field_value.get("name", field_value.get("date", ""))))
        values[_field_key(field_name)] = _clean_number_text(str(value or ""))
    return values


def _value_by_field_key(values: dict[str, str], target: str) -> str:
    target_key = _field_key(target)
    if target_key in values:
        return values[target_key]
    for key, value in values.items():
        if target_key in key or key in target_key:
            return value
    return ""


def _fields_by_key(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_field_key(str(field.get("name") or "")): field for field in project.get("fields", {}).get("nodes", []) or [] if field}


def _find_field(fields: dict[str, dict[str, Any]], candidates: tuple[str, ...]) -> dict[str, Any] | None:
    for candidate in candidates:
        key = _field_key(candidate)
        if key in fields:
            return fields[key]
    for candidate in candidates:
        key = _field_key(candidate)
        for field_key, field in fields.items():
            if key in field_key or field_key in key:
                return field
    return None


def _field_key(value: str) -> str:
    return re.sub(r"[^a-zа-яіїєґ0-9]+", "", value.casefold())


def _select_option(field: dict[str, Any], candidates: list[str]) -> str:
    options = field.get("options") or []
    normalized_candidates = [_field_key(candidate) for candidate in candidates if candidate]
    for option in options:
        option_name = str(option.get("name") or "")
        if _field_key(option_name) in normalized_candidates:
            return str(option.get("id") or "")
    for option in options:
        option_key = _field_key(str(option.get("name") or ""))
        if any(candidate in option_key or option_key in candidate for candidate in normalized_candidates):
            return str(option.get("id") or "")
    return ""


def _normalize_date_text(value: str) -> str:
    parsed = _parse_date(value)
    return parsed.strftime("%d.%m.%Y") if parsed else value.strip()


def _date_plus_days(value: str, days: int) -> str:
    if days <= 0:
        return ""
    parsed = _parse_date(value)
    if parsed is None:
        return ""
    return (parsed + timedelta(days=days)).strftime("%d.%m.%Y")


def _date_to_iso(value: str) -> str:
    parsed = _parse_date(value)
    return parsed.date().isoformat() if parsed else ""


def _parse_date(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    match = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day))
    except ValueError:
        return None

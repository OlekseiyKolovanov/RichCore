from __future__ import annotations

import json

from .paths import config_dir, legacy_appdata_dir


STATE_PATH = config_dir() / "state.json"
LEGACY_STATE_PATH = legacy_appdata_dir("Atools") / "state.json"


def _load_state_payload() -> dict:
    if not STATE_PATH.exists() and LEGACY_STATE_PATH.exists():
        STATE_PATH.write_text(LEGACY_STATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def load_dismissed_signatures() -> set[str]:
    raw = _load_state_payload()
    return set(raw.get("dismissed_report_signatures", []))


def load_dismissed_vip_signatures() -> set[str]:
    raw = _load_state_payload()
    return set(raw.get("dismissed_vip_ad_signatures", []))


def save_dismissed_signatures(
    report_signatures: set[str],
    vip_signatures: set[str] | None = None,
) -> None:
    payload = {
        "dismissed_report_signatures": sorted(report_signatures),
        "dismissed_vip_ad_signatures": sorted(vip_signatures or set()),
    }
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

from __future__ import annotations

import ast
import importlib.util
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from .paths import bundle_root_dir, source_root_dir


@dataclass(slots=True)
class AiAsistReply:
    text: str
    provider_name: str
    provider_index: int
    key_index: int
    model_name: str
    model_index: int
    script_path: Path


class AiAsistBridge:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._module: ModuleType | None = None
        self._bot = None

    def prepare(self):
        with self._lock:
            if self._bot is not None:
                return self._bot

            module = self._load_module()
            rules_text = module.load_text_file(module.RULES_FILE)
            guide_text = module.load_text_file(module.GUIDE_FILE)
            qa_pairs = self._load_qa_pairs(module)
            self._module = module
            self._bot = module.AIBot(rules_text, guide_text, qa_pairs)
            self._install_tracking(module, self._bot)
            return self._bot

    def generate_reply(self, question: str) -> str:
        return self.generate_reply_details(question).text

    def generate_reply_details(self, question: str) -> AiAsistReply:
        bot = self.prepare()
        prompt = question.strip() or "Без тексту"
        setattr(bot, "_richcore_last_success", None)
        text = bot.ask(prompt)
        return self._build_reply(bot, text)

    def script_path(self) -> Path:
        return self._resolve_script_path()

    def provider_configs(self) -> tuple[dict[str, object], ...]:
        return tuple(self._parse_provider_configs(self._resolve_script_path()))

    def _load_module(self) -> ModuleType:
        if self._module is not None:
            return self._module

        script_path = self._resolve_script_path()
        spec = importlib.util.spec_from_file_location("atools._aiasist_runtime", script_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Не вдалося створити spec для {script_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _load_qa_pairs(module: ModuleType):
        cache_path = Path(module.CACHE_FILE)
        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        return module.get_qa_pairs()

    @staticmethod
    def _install_tracking(module: ModuleType, bot) -> None:
        if getattr(bot, "_richcore_tracking_installed", False):
            return

        original_call_api = bot._call_api

        def tracked_call_api(user_message, provider_url, key, model, system_prompt):
            text, code = original_call_api(user_message, provider_url, key, model, system_prompt)
            if text:
                provider_index = 0
                key_index = 0
                model_index = 0
                provider_name = "AiAsist"
                for p_idx, provider in enumerate(getattr(module, "PROVIDERS", [])):
                    if provider.get("url") != provider_url:
                        continue
                    provider_index = p_idx
                    provider_name = provider.get("name", "AiAsist")
                    try:
                        key_index = provider.get("keys", []).index(key)
                    except ValueError:
                        key_index = 0
                    try:
                        model_index = provider.get("models", []).index(model)
                    except ValueError:
                        model_index = 0
                    break
                bot._richcore_last_success = {
                    "provider_name": provider_name,
                    "provider_index": provider_index,
                    "key_index": key_index,
                    "model_name": model,
                    "model_index": model_index,
                }
            return text, code

        bot._call_api = tracked_call_api
        bot._richcore_tracking_installed = True

    def _build_reply(self, bot, text: str) -> AiAsistReply:
        success = getattr(bot, "_richcore_last_success", None) or {}
        return AiAsistReply(
            text=text,
            provider_name=str(success.get("provider_name", "AiAsist")),
            provider_index=int(success.get("provider_index", 0)),
            key_index=int(success.get("key_index", 0)),
            model_name=str(success.get("model_name", "AiAsist")),
            model_index=int(success.get("model_index", 0)),
            script_path=self.script_path(),
        )

    @staticmethod
    def _parse_provider_configs(script_path: Path) -> list[dict[str, object]]:
        tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PROVIDERS":
                    return AiAsistBridge._normalize_provider_configs(ast.literal_eval(node.value))
        raise RuntimeError(f"Не знайдено PROVIDERS у {script_path}")

    @staticmethod
    def _normalize_provider_configs(raw_providers: object) -> list[dict[str, object]]:
        providers: list[dict[str, object]] = []
        if not isinstance(raw_providers, list):
            return providers

        for raw_provider in raw_providers:
            if not isinstance(raw_provider, dict):
                continue
            url = str(raw_provider.get("url") or "").strip()
            name = str(raw_provider.get("name") or "AiAsist").strip() or "AiAsist"
            keys = [
                str(item).strip()
                for item in raw_provider.get("keys", [])
                if isinstance(item, str) and str(item).strip()
            ]
            models = [
                str(item).strip()
                for item in raw_provider.get("models", [])
                if isinstance(item, str) and str(item).strip()
            ]
            providers.append(
                {
                    "name": name,
                    "url": url,
                    "keys": keys,
                    "models": models,
                }
            )
        return providers

    @staticmethod
    def _resolve_script_path() -> Path:
        candidates = [
            bundle_root_dir() / "internal_ai" / "ai_asist" / "ukrainegta_bot.py",
            source_root_dir().parent / "Скрипти" / "AiAsist" / "ukrainegta_bot.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError("Не знайдено ukrainegta_bot.py для нового AiAsist backend.")

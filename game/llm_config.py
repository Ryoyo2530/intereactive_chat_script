import os
from dataclasses import dataclass
from typing import Any

PROVIDERS: dict[str, dict[str, str]] = {
    "doubao": {
        "name": "豆包 / 火山引擎",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    },
    "openai": {
        "name": "OpenAI",
        "api_base": "https://api.openai.com/v1",
    },
    "custom": {
        "name": "自定义",
        "api_base": "",
    },
}


@dataclass
class LLMConfig:
    provider: str
    api_base: str
    api_key: str
    model: str

    def as_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "api_base": self.api_base,
            "api_key": self.api_key,
            "model": self.model,
        }

    def public_dict(self) -> dict[str, str]:
        """Safe for debug export — omits api_key."""
        return {
            "provider": self.provider,
            "api_base": self.api_base,
            "model": self.model,
        }


def _env_config() -> LLMConfig | None:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    api_base = os.getenv("LLM_API_BASE", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    provider = os.getenv("LLM_PROVIDER", "doubao").strip() or "doubao"
    if not api_key or not api_base or not model:
        return None
    return LLMConfig(provider=provider, api_base=api_base, api_key=api_key, model=model)


def resolve_config(override: dict[str, Any] | None) -> LLMConfig:
    env_cfg = _env_config()
    if not override:
        if env_cfg:
            return env_cfg
        raise ValueError("LLM 未配置，请先在设置中填写 Provider、API Key 和 Model")

    provider = (override.get("provider") or "custom").strip()
    api_base = (override.get("api_base") or "").strip()
    api_key = (override.get("api_key") or "").strip()
    model = (override.get("model") or "").strip()

    if not api_base and provider in PROVIDERS:
        api_base = PROVIDERS[provider]["api_base"]

    if not api_key and env_cfg:
        api_key = env_cfg.api_key
    if not api_base and env_cfg:
        api_base = env_cfg.api_base
    if not model and env_cfg:
        model = env_cfg.model

    if not api_base or not api_key or not model:
        raise ValueError("请完整填写 API Base、API Key 和 Model")

    return LLMConfig(provider=provider, api_base=api_base, api_key=api_key, model=model)


def resolve_dev_agent_configs(
    override: dict[str, Any] | None,
) -> tuple[LLMConfig, LLMConfig]:
    """Resolve director and roleplay configs; falls back to shared model if not split."""
    if not override:
        cfg = resolve_config(None)
        return cfg, cfg

    if override.get("director") or override.get("roleplay"):
        director_raw = override.get("director") or override
        roleplay_raw = override.get("roleplay") or override
        return resolve_config(director_raw), resolve_config(roleplay_raw)

    shared = {
        "provider": override.get("provider"),
        "api_base": override.get("api_base"),
        "api_key": override.get("api_key"),
    }
    director_model = (override.get("director_model") or override.get("model") or "").strip()
    roleplay_model = (override.get("roleplay_model") or override.get("model") or "").strip()

    director_cfg = resolve_config({**shared, "model": director_model})
    if roleplay_model and roleplay_model != director_model:
        roleplay_cfg = resolve_config({**shared, "model": roleplay_model})
    else:
        roleplay_cfg = director_cfg
    return director_cfg, roleplay_cfg


def get_status(override: dict[str, Any] | None = None) -> dict[str, Any]:
    env_cfg = _env_config()
    try:
        cfg = resolve_config(override)
        configured = True
    except ValueError:
        configured = bool(env_cfg)
        cfg = env_cfg

    return {
        "configured": configured,
        "source": "env" if env_cfg and not override else ("client" if configured else "none"),
        "provider": cfg.provider if cfg else "",
        "api_base": cfg.api_base if cfg else "",
        "model": cfg.model if cfg else "",
        "api_key_masked": mask_api_key(cfg.api_key) if cfg else "",
        "providers": [
            {"id": pid, "name": pdata["name"], "api_base": pdata["api_base"]}
            for pid, pdata in PROVIDERS.items()
        ],
    }


def mask_api_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_template(template_name: str, overrides: dict[str, str] | None = None) -> str:
    if overrides and template_name in overrides:
        return overrides[template_name]
    path = PROMPTS_DIR / template_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_name}")
    return path.read_text(encoding="utf-8")


def render(template_name: str, overrides: dict[str, str] | None = None, **kwargs: str) -> str:
    text = load_template(template_name, overrides=overrides)
    for key, value in kwargs.items():
        text = text.replace(f"{{{{{key}}}}}", str(value))
    return text


def format_stats(stats: dict[str, int]) -> str:
    if not stats:
        return "（无）"
    return "\n".join(f"- {name}: {value}" for name, value in stats.items())


def format_history(history: list[dict]) -> str:
    if not history:
        return "（暂无历史对话）"
    lines = []
    for entry in history:
        character = entry.get("character") or ("AI" if entry["role"] == "assistant" else "玩家")
        lines.append(f"{character}：{entry['content']}")
    return "\n".join(lines)


def format_emotion_vocabulary(script: dict) -> str:
    vocab = script.get("ai_character", {}).get("emotion_vocabulary") or []
    if not vocab:
        return "（未配置，可从：戒备、软化、追问、爆发、冷静、释然 中选择）"
    return "、".join(vocab)


def format_stat_change_ranges(hit_stat_changes: dict) -> str:
    if not hit_stat_changes:
        return "无"
    parts = []
    for stat, spec in hit_stat_changes.items():
        lo, hi = parse_stat_range(spec)
        if lo == hi:
            parts.append(f"{stat} {lo:+d}")
        else:
            parts.append(f"{stat} [{lo}, {hi}]")
    return "；".join(parts)


def parse_stat_range(spec) -> tuple[int, int]:
    if isinstance(spec, (int, float)):
        value = int(spec)
        return value, value
    if isinstance(spec, list) and len(spec) >= 2:
        lo, hi = int(spec[0]), int(spec[1])
        return (lo, hi) if lo <= hi else (hi, lo)
    if isinstance(spec, dict):
        lo, hi = int(spec["min"]), int(spec["max"])
        return (lo, hi) if lo <= hi else (hi, lo)
    return 0, 0


def _format_point_line(item: dict) -> str:
    title = item.get("title") or "未命名"
    description = item.get("description") or ""
    ranges = format_stat_change_ranges(item.get("hit_stat_changes", {}))
    return f"- [{item['id']}] {title}：{description}（数值变化区间：{ranges}）"


def format_pending_key_points(script: dict, hit_ids: set | list) -> str:
    hit = set(str(i) for i in hit_ids)
    pending = [kp for kp in script.get("key_points", []) if str(kp.get("id", "")) not in hit]
    if not pending:
        return "（无，已全部命中或剧本未配置）"
    return "\n".join(_format_point_line(item) for item in pending)


def format_pending_pitfalls(script: dict, hit_ids: set | list) -> str:
    hit = set(str(i) for i in hit_ids)
    pending = [pf for pf in script.get("pitfalls", []) if str(pf.get("id", "")) not in hit]
    if not pending:
        return "（无，已全部命中或剧本未配置）"
    return "\n".join(_format_point_line(item) for item in pending)

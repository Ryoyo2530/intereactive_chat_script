"""Static schema validation for script JSON files."""

from typing import Any
from game.core import condition_parser

REQUIRED_FIELDS = [
    "title", "origin_tag", "theme_tags", "background",
    "ai_character", "player_character", "stats", "key_points",
    "win_condition", "lose_condition", "max_turns", "opening_line",
]

VALID_ORIGIN_TAGS = {"影视同人", "你也一定遇到过"}


def validate(script: dict[str, Any]) -> dict[str, list[str]]:
    """Validate a script dict.

    Returns {"errors": [...], "warnings": [...]}
    Errors block saving; warnings are advisory only.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in script or script[field] is None:
            errors.append(f"缺少必填字段：{field}")

    # origin_tag enum
    origin_tag = script.get("origin_tag", "")
    if origin_tag and origin_tag not in VALID_ORIGIN_TAGS:
        errors.append(f'origin_tag 值无效："{origin_tag}"，必须是 {sorted(VALID_ORIGIN_TAGS)} 之一')

    # theme_tags is a list
    if "theme_tags" in script and not isinstance(script["theme_tags"], list):
        errors.append("theme_tags 必须是数组")

    # stats: initial within min/max
    stats_cfg = script.get("stats") or {}
    if isinstance(stats_cfg, dict):
        for stat_name, cfg in stats_cfg.items():
            if not isinstance(cfg, dict):
                continue
            lo = cfg.get("min", 0)
            hi = cfg.get("max", 100)
            initial = cfg.get("initial")
            if initial is not None and not (lo <= initial <= hi):
                errors.append(
                    f"stats.{stat_name}.initial={initial} 超出范围 [{lo}, {hi}]"
                )

    # key_points and pitfalls: unique IDs within each section, hit_stat_changes refs valid stats
    stat_names = set(stats_cfg.keys()) if isinstance(stats_cfg, dict) else set()

    for section, label in [("key_points", "key_points"), ("pitfalls", "pitfalls")]:
        items = script.get(section) or []
        if not isinstance(items, list):
            continue
        seen_in_section: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if item_id is not None:
                sid = str(item_id)
                if sid in seen_in_section:
                    errors.append(f"{label} 存在重复 id：{sid}")
                seen_in_section.add(sid)
            changes = item.get("hit_stat_changes") or {}
            if isinstance(changes, dict):
                for ref_stat in changes:
                    if stat_names and ref_stat not in stat_names:
                        errors.append(
                            f"{label}[id={item_id}].hit_stat_changes 引用了不存在的数值：{ref_stat}"
                        )

    # win/lose conditions parseable
    for field in ("win_condition", "lose_condition"):
        cond = script.get(field, "")
        if cond and not condition_parser.is_parseable(str(cond)):
            errors.append(f"{field} 无法解析，请检查格式（示例：好感度 >= 70 且 愤怒值 <= 20）")

    # emotion_vocabulary non-empty list (top-level or ai_character)
    vocab = script.get("emotion_vocabulary")
    if vocab is None:
        vocab = (script.get("ai_character") or {}).get("emotion_vocabulary")
    if vocab is None:
        warnings.append("缺少 emotion_vocabulary，情绪标签功能将无法正常工作")
    elif not isinstance(vocab, list) or len(vocab) == 0:
        errors.append("emotion_vocabulary 必须是非空数组")

    # Warnings
    key_points = script.get("key_points") or []
    if isinstance(key_points, list) and len(key_points) < 3:
        warnings.append(f"key_points 数量较少（当前 {len(key_points)} 个），可能影响可玩性")

    if not script.get("teaser"):
        warnings.append("缺少 teaser 字段，剧本列表页将没有简介文字")

    if not script.get("briefing"):
        warnings.append("缺少 briefing 字段，入场须知将显示为空")

    return {"errors": errors, "warnings": warnings}

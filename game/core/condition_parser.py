import re
from typing import Any


_FLAG_EXISTS = re.compile(r"^flag:([A-Za-z0-9_\-]+)$")
_FLAG_COMPARE = re.compile(
    r"^flag:([A-Za-z0-9_\-]+)\s*(==|!=)\s*(.+)$"
)
_STAT_COMPARE = re.compile(r"^(.+?)\s*(<=|>=|<|>|==)\s*(-?\d+)$")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "none", "null")
    return bool(value)


def _eval_flag_clause(clause: str, flags: dict[str, Any]) -> bool | None:
    """Return bool if clause is a flag expression, else None (not a flag clause)."""
    text = clause.strip()
    compare = _FLAG_COMPARE.match(text)
    if compare:
        name, op, raw = compare.groups()
        raw = raw.strip().strip("\"'")
        current = flags.get(name)
        if raw.lower() in ("true", "false"):
            expected: Any = raw.lower() == "true"
        else:
            try:
                expected = int(raw)
            except ValueError:
                expected = raw
        if op == "==":
            return current == expected
        return current != expected

    exists = _FLAG_EXISTS.match(text)
    if exists:
        return _truthy(flags.get(exists.group(1)))
    return None


def _eval_stat_clause(clause: str, stats: dict[str, int]) -> bool | None:
    match = _STAT_COMPARE.match(clause.strip())
    if not match:
        return None
    stat_name, op, raw_value = match.groups()
    value = stats.get(stat_name.strip(), 0)
    threshold = int(raw_value)
    if op == "<=":
        return value <= threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == ">":
        return value > threshold
    if op == "==":
        return value == threshold
    return False


def evaluate(
    condition: str,
    stats: dict[str, int],
    flags: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a condition string against stats and optional flags.

    Conditions are '且'-separated clauses. Each clause is either:
      - <stat_name> <op> <integer>   (op: <= >= < > ==)
      - flag:<name>                  (truthy if set)
      - flag:<name> == <value>       (exact compare; true/false/int/string)

    Returns True if all recognized clauses pass. Unrecognized clauses are skipped.
    Empty/whitespace conditions return True.
    """
    if not condition or not str(condition).strip():
        return True

    flag_map = flags or {}
    parts = re.split(r"\s*且\s*", str(condition).strip())
    saw_valid = False
    for part in parts:
        if not part.strip():
            continue
        flag_result = _eval_flag_clause(part, flag_map)
        if flag_result is not None:
            saw_valid = True
            if not flag_result:
                return False
            continue
        stat_result = _eval_stat_clause(part, stats)
        if stat_result is not None:
            saw_valid = True
            if not stat_result:
                return False
            continue
        # Unrecognized clause — ignore (same spirit as legacy parser).
    return True if saw_valid else True


def is_parseable(condition: str) -> bool:
    """Return True if the condition string contains at least one valid clause."""
    if not condition or not str(condition).strip():
        return False
    parts = re.split(r"\s*且\s*", str(condition).strip())
    for part in parts:
        if _FLAG_EXISTS.match(part.strip()) or _FLAG_COMPARE.match(part.strip()):
            return True
        if _STAT_COMPARE.match(part.strip()):
            return True
    return False

import re


def evaluate(condition: str, stats: dict[str, int]) -> bool:
    """Evaluate a win/lose condition string against current stats.

    Conditions are '且'-separated clauses, each of the form:
        <stat_name> <op> <integer>
    where op is one of: <= >= < > ==

    Returns True if all clauses pass (or if no valid clause is found).
    """
    parts = re.split(r"\s*且\s*", condition.strip())
    for part in parts:
        match = re.match(r"(.+?)\s*(<=|>=|<|>|==)\s*(-?\d+)", part.strip())
        if not match:
            continue
        stat_name, op, raw_value = match.groups()
        stat_name = stat_name.strip()
        value = stats.get(stat_name, 0)
        threshold = int(raw_value)
        if op == "<=" and not (value <= threshold):
            return False
        if op == ">=" and not (value >= threshold):
            return False
        if op == "<" and not (value < threshold):
            return False
        if op == ">" and not (value > threshold):
            return False
        if op == "==" and not (value == threshold):
            return False
    return True


def is_parseable(condition: str) -> bool:
    """Return True if the condition string contains at least one valid clause."""
    parts = re.split(r"\s*且\s*", condition.strip())
    for part in parts:
        if re.match(r"(.+?)\s*(<=|>=|<|>|==)\s*(-?\d+)", part.strip()):
            return True
    return False

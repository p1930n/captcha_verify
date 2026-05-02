from __future__ import annotations

from .models import MAX_VERIFY_WINDOW_SECONDS, MIN_VERIFY_WINDOW_SECONDS


MIN_QQ_GROUP_ID_LENGTH = 5
MAX_QQ_GROUP_ID_LENGTH = 20


def is_valid_group_id(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.isdigit()
        and MIN_QQ_GROUP_ID_LENGTH <= len(normalized) <= MAX_QQ_GROUP_ID_LENGTH
    )


def parse_verify_window_seconds(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = int(normalized, 10)
    except ValueError:
        return None
    if not MIN_VERIFY_WINDOW_SECONDS <= parsed <= MAX_VERIFY_WINDOW_SECONDS:
        return None
    return parsed

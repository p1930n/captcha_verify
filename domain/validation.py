from __future__ import annotations


MIN_QQ_GROUP_ID_LENGTH = 5
MAX_QQ_GROUP_ID_LENGTH = 20


def is_valid_group_id(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.isdigit()
        and MIN_QQ_GROUP_ID_LENGTH <= len(normalized) <= MAX_QQ_GROUP_ID_LENGTH
    )

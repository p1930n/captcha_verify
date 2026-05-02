from __future__ import annotations


SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * SECONDS_PER_MINUTE
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR


def format_duration_text(seconds: int) -> str:
    normalized = max(0, int(seconds))
    if normalized % SECONDS_PER_DAY == 0 and normalized >= SECONDS_PER_DAY:
        return f"{normalized // SECONDS_PER_DAY}天"
    if normalized % SECONDS_PER_HOUR == 0 and normalized >= SECONDS_PER_HOUR:
        return f"{normalized // SECONDS_PER_HOUR}小时"
    if normalized % SECONDS_PER_MINUTE == 0 and normalized >= SECONDS_PER_MINUTE:
        return f"{normalized // SECONDS_PER_MINUTE}分钟"
    return f"{normalized}秒"

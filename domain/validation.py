from __future__ import annotations

from .models import (
    MAX_VERIFY_WINDOW_SECONDS,
    MIN_VERIFY_WINDOW_SECONDS,
    TIMEOUT_ACTION_KICK,
    TIMEOUT_ACTION_MUTE,
)


MIN_QQ_GROUP_ID_LENGTH = 5
MAX_QQ_GROUP_ID_LENGTH = 20
MIN_QQ_USER_ID_LENGTH = 5
MAX_QQ_USER_ID_LENGTH = 20
TIMEOUT_ACTION_ALIASES = {
    "kick": TIMEOUT_ACTION_KICK,
    "踢": TIMEOUT_ACTION_KICK,
    "踢出": TIMEOUT_ACTION_KICK,
    "mute": TIMEOUT_ACTION_MUTE,
    "ban": TIMEOUT_ACTION_MUTE,
    "禁言": TIMEOUT_ACTION_MUTE,
    "长时禁言": TIMEOUT_ACTION_MUTE,
}
BOOL_ALIASES = {
    "1": True,
    "true": True,
    "yes": True,
    "y": True,
    "on": True,
    "enable": True,
    "enabled": True,
    "开启": True,
    "启用": True,
    "开": True,
    "0": False,
    "false": False,
    "no": False,
    "n": False,
    "off": False,
    "disable": False,
    "disabled": False,
    "关闭": False,
    "停用": False,
    "关": False,
}


def is_valid_group_id(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.isdigit()
        and MIN_QQ_GROUP_ID_LENGTH <= len(normalized) <= MAX_QQ_GROUP_ID_LENGTH
    )


def is_valid_user_id(value: str) -> bool:
    normalized = value.strip()
    return (
        normalized.isdigit()
        and MIN_QQ_USER_ID_LENGTH <= len(normalized) <= MAX_QQ_USER_ID_LENGTH
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


def parse_timeout_action(value: str) -> str | None:
    normalized = value.strip().casefold().replace("-", "_")
    if not normalized:
        return None
    return TIMEOUT_ACTION_ALIASES.get(normalized)


def parse_bool_switch(value: str) -> bool | None:
    normalized = value.strip().casefold()
    if not normalized:
        return None
    return BOOL_ALIASES.get(normalized)

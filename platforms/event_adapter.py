from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain.models import PlatformEventSnapshot


MESSAGE_OBJ_RAW_FIELDS = ("raw_message", "raw_event", "raw")
PLATFORM_FIELD_CANDIDATES = ("get_platform_name", "platform_name")
GROUP_ID_FIELD_CANDIDATES = ("get_group_id", "group_id")
SENDER_ID_FIELD_CANDIDATES = ("get_sender_id", "sender_id", "user_id")
SENDER_DISPLAY_FIELD_CANDIDATES = (
    "get_sender_name",
    "sender_name",
    "sender_display_name",
    "nickname",
)
SENDER_ROLE_FIELD_CANDIDATES = (
    "get_sender_role",
    "sender_role",
    "group_role",
    "member_role",
    "role",
)
SENDER_OWNER_BOOL_FIELD_CANDIDATES = (
    "is_group_owner",
    "sender_is_group_owner",
    "is_owner",
)
SENDER_ADMIN_BOOL_FIELD_CANDIDATES = (
    "is_group_admin",
    "sender_is_group_admin",
    "is_admin",
)


def dehydrate_event_snapshot(event: Any) -> PlatformEventSnapshot:
    return PlatformEventSnapshot(
        platform=_event_value(event, *PLATFORM_FIELD_CANDIDATES),
        group_id=_event_value(event, *GROUP_ID_FIELD_CANDIDATES),
        sender_id=_event_value(event, *SENDER_ID_FIELD_CANDIDATES),
        sender_role=_sender_role_from_event(event),
        sender_display_name=_event_value(event, *SENDER_DISPLAY_FIELD_CANDIDATES),
    )


def extract_raw_notice_payload(event: Any) -> dict[str, Any] | None:
    message_obj = _message_obj_from_event(event)
    if message_obj is None:
        return None
    for raw_field in MESSAGE_OBJ_RAW_FIELDS:
        raw = _source_value(message_obj, raw_field)
        if isinstance(raw, dict):
            return raw
    return None


def extract_onebot_action_client(event: Any) -> object | None:
    bot = _source_value(event, "bot")
    if bot is None:
        return None
    action_client = _source_value(bot, "api")
    if action_client is None:
        return None
    return action_client


def _sender_role_from_event(event: Any) -> str:
    for source in _event_sources(event):
        for name in SENDER_ROLE_FIELD_CANDIDATES:
            value = _source_value(source, name)
            if value:
                return _normalize_sender_role(str(value))
    for source in _event_sources(event):
        if _source_bool(source, *SENDER_OWNER_BOOL_FIELD_CANDIDATES):
            return "owner"
        if _source_bool(source, *SENDER_ADMIN_BOOL_FIELD_CANDIDATES):
            return "admin"
    return ""


def _normalize_sender_role(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized in {"owner", "群主"}:
        return "owner"
    if normalized in {"admin", "administrator", "群管理员", "管理员"}:
        return "admin"
    if normalized in {"member", "成员", "normal"}:
        return "member"
    return normalized


def _event_value(event: Any, *names: str) -> str:
    for source in _event_sources(event):
        for name in names:
            value = _source_value(source, name)
            if value:
                return str(value).strip()
    return ""


def _event_sources(event: Any) -> tuple[object, ...]:
    sources: list[object] = [event]
    message_obj = _message_obj_from_event(event)
    if message_obj is None:
        return tuple(sources)
    sources.append(message_obj)
    for raw_field in MESSAGE_OBJ_RAW_FIELDS:
        raw = _source_value(message_obj, raw_field)
        if raw is None:
            continue
        sources.append(raw)
        sender = _source_value(raw, "sender")
        if sender is not None:
            sources.append(sender)
    sender = _source_value(message_obj, "sender")
    if sender is not None:
        sources.append(sender)
    return tuple(sources)


def _message_obj_from_event(event: Any) -> object | None:
    try:
        return getattr(event, "message_obj", None)
    except Exception:
        return None


def _source_value(source: object, name: str) -> object:
    if isinstance(source, Mapping):
        value = source.get(name)
    else:
        try:
            value = getattr(source, name, None)
        except Exception:
            return None
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _source_bool(source: object, *names: str) -> bool:
    for name in names:
        value = _source_value(source, name)
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
    return False

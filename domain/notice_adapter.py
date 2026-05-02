from __future__ import annotations

from typing import Any

from .models import NewMemberNotice


GROUP_INCREASE_NOTICE_TYPE = "group_increase"
NOTICE_POST_TYPE = "notice"


def parse_new_member_notice(
    payload: dict[str, Any] | None,
    *,
    platform: str,
) -> NewMemberNotice | None:
    if not isinstance(payload, dict):
        return None
    if _to_text(payload.get("post_type")) != NOTICE_POST_TYPE:
        return None
    if _to_text(payload.get("notice_type")) != GROUP_INCREASE_NOTICE_TYPE:
        return None

    group_id = _to_text(payload.get("group_id"))
    user_id = _to_text(payload.get("user_id"))
    if not group_id or not user_id:
        return None

    return NewMemberNotice(
        platform=platform,
        group_id=group_id,
        user_id=user_id,
        operator_id=_to_text(payload.get("operator_id")),
        sub_type=_to_text(payload.get("sub_type")),
        time_raw=_to_text(payload.get("time")),
    )


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

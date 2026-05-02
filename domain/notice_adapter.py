from __future__ import annotations

from typing import Any

from .models import GroupEmojiReactionNotice, NewMemberNotice


GROUP_INCREASE_NOTICE_TYPE = "group_increase"
GROUP_MSG_EMOJI_LIKE_NOTICE_TYPE = "group_msg_emoji_like"
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


def parse_group_emoji_reaction_notice(
    payload: dict[str, Any] | None,
    *,
    platform: str,
) -> GroupEmojiReactionNotice | None:
    if not isinstance(payload, dict):
        return None
    if _to_text(payload.get("post_type")) != NOTICE_POST_TYPE:
        return None
    if _to_text(payload.get("notice_type")) != GROUP_MSG_EMOJI_LIKE_NOTICE_TYPE:
        return None

    group_id = _to_text(payload.get("group_id"))
    user_id = _first_text(payload, "user_id", "operator_id")
    message_id = _to_text(payload.get("message_id"))
    if not group_id or not user_id or not message_id:
        return None

    emoji_ids = _extract_emoji_ids(payload)
    if not emoji_ids:
        return None

    return GroupEmojiReactionNotice(
        platform=platform,
        group_id=group_id,
        user_id=user_id,
        self_id=_to_text(payload.get("self_id")),
        message_id=message_id,
        emoji_ids=emoji_ids,
        time_raw=_to_text(payload.get("time")),
    )


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _to_text(payload.get(key))
        if value:
            return value
    return ""


def _extract_emoji_ids(payload: dict[str, Any]) -> tuple[str, ...]:
    direct = _first_text(payload, "emoji_id", "emojiId", "code")
    emoji_ids: list[str] = []
    if direct:
        emoji_ids.append(direct)

    likes = payload.get("likes")
    if isinstance(likes, list):
        for like in likes:
            if not isinstance(like, dict):
                continue
            if _count_is_zero(like.get("count")):
                continue
            emoji_id = _first_text(like, "emoji_id", "emojiId", "code")
            if emoji_id:
                emoji_ids.append(emoji_id)

    return tuple(dict.fromkeys(emoji_ids))


def _count_is_zero(value: Any) -> bool:
    if value is None:
        return False
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

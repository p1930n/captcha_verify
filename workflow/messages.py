from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..domain.duration import format_duration_text
from ..domain.models import GroupEmojiReactionNotice, NewMemberNotice, VerificationSession


DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
NOTICE_TIME_FORMAT = "%Y-%m-%d %H-%M"


def format_source_verification_prompt(*, verification_window_seconds: int) -> str:
    return "\n".join(
        [
            "本人或群管在"
            f"{format_duration_text(verification_window_seconds)}"
            "内点击下方OK手势即可完成认证",
            "如遇QQ兼容问题，私信机器人任意一条信息即可通过",
            "群主或管理员点击下方问号表情将踢出并加入黑名单",
        ]
    )


def format_push_verification_log(
    notice: NewMemberNotice,
    *,
    source_prompt_message_id: str = "",
) -> str:
    lines = [
        "验证码入群审核：检测到新人入群",
        f"来源群={notice.group_id}",
        f"新人={notice.user_id}",
    ]
    if notice.operator_id:
        lines.append(f"操作人={notice.operator_id}")
    if notice.sub_type:
        lines.append(f"入群方式={_format_join_type(notice.sub_type)}")
    if notice.time_raw:
        lines.append(f"时间={format_notice_time(notice.time_raw)}")
    if source_prompt_message_id:
        lines.append(f"源群验证消息={source_prompt_message_id}")
    lines.append("点击本消息下方机器人预回应的 👌 表情可通过审核。")
    lines.append("点击本消息下方机器人预回应的 ❓ 表情可踢出并加入黑名单。")
    return "\n".join(lines)


def format_push_verification_log_en(
    notice: NewMemberNotice,
    *,
    source_prompt_message_id: str = "",
) -> str:
    lines = [
        "CAPTCHA VERIFICATION EVENT: NEW MEMBER DETECTED",
        f"source_group={notice.group_id}",
        f"new_member={notice.user_id}",
    ]
    if notice.operator_id:
        lines.append(f"operator={notice.operator_id}")
    if notice.sub_type:
        lines.append(f"join_type={notice.sub_type}")
    if notice.time_raw:
        lines.append(f"time={format_notice_time(notice.time_raw)}")
    if source_prompt_message_id:
        lines.append(f"source_prompt_message={source_prompt_message_id}")
    lines.append("action_ok=React with the bot's pre-added OK emoji to approve.")
    lines.append("action_question=React with the bot's pre-added question emoji to reject and blacklist.")
    return "\n".join(lines)


def format_approval_log(
    session: VerificationSession,
    reaction: GroupEmojiReactionNotice,
) -> str:
    lines = [
        "验证码入群审核：已通过",
        f"来源群={session.group_id}",
        f"新人={session.user_id}",
    ]
    if session.approval_source == "private_message":
        lines.append("验证方式=新人私信机器人")
    elif reaction.user_id == session.user_id:
        lines.append("验证方式=新人本人 👌 回应")
    else:
        lines.append(f"审批人={reaction.user_id}")
    if session.approval_source:
        lines.append(f"审批来源={_format_approval_source(session.approval_source)}")
    if reaction.time_raw:
        lines.append(f"时间={format_notice_time(reaction.time_raw)}")
    return "\n".join(lines)


def format_approval_log_en(
    session: VerificationSession,
    reaction: GroupEmojiReactionNotice,
) -> str:
    lines = [
        "CAPTCHA VERIFICATION EVENT: APPROVED",
        f"source_group={session.group_id}",
        f"new_member={session.user_id}",
    ]
    if session.approval_source == "private_message":
        lines.append("method=private_message")
    elif reaction.user_id == session.user_id:
        lines.append("method=self_reaction")
    else:
        lines.append(f"approver={reaction.user_id}")
    if session.approval_source:
        lines.append(f"approval_source={session.approval_source}")
    if reaction.time_raw:
        lines.append(f"time={format_notice_time(reaction.time_raw)}")
    return "\n".join(lines)


def format_rejection_log(
    session: VerificationSession,
    reaction: GroupEmojiReactionNotice,
) -> str:
    lines = [
        "验证码入群审核：已拒绝并加入黑名单",
        f"来源群={session.group_id}",
        f"新人={session.user_id}",
        f"操作人={reaction.user_id}",
    ]
    if reaction.time_raw:
        lines.append(f"时间={format_notice_time(reaction.time_raw)}")
    return "\n".join(lines)


def format_rejection_log_en(
    session: VerificationSession,
    reaction: GroupEmojiReactionNotice,
) -> str:
    lines = [
        "CAPTCHA VERIFICATION EVENT: REJECTED_AND_BLACKLISTED",
        f"source_group={session.group_id}",
        f"new_member={session.user_id}",
        f"operator={reaction.user_id}",
        "action=kick_and_blacklist",
    ]
    if reaction.time_raw:
        lines.append(f"time={format_notice_time(reaction.time_raw)}")
    return "\n".join(lines)


def format_notice_time(time_raw: str) -> str:
    normalized = time_raw.strip()
    if not normalized:
        return ""
    try:
        timestamp = int(float(normalized))
    except ValueError:
        return normalized
    return datetime.fromtimestamp(timestamp, tz=DISPLAY_TIMEZONE).strftime(
        NOTICE_TIME_FORMAT
    )


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_after_seconds_text(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _format_join_type(sub_type: str) -> str:
    normalized = sub_type.strip().casefold()
    if normalized == "approve":
        return "管理员同意"
    if normalized == "invite":
        return "邀请入群"
    return sub_type


def _format_approval_source(source: str) -> str:
    if source == "group_prompt":
        return "源群验证消息"
    if source == "push_prompt":
        return "推送群审核消息"
    if source == "private_message":
        return "新人私信机器人"
    return source

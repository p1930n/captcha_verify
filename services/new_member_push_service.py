from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

from ..domain.models import NewMemberNotice
from ..persistence.repository import VerifyRepository
from ..platforms.bot_actions import SendGroupTextResult


DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
NOTICE_TIME_FORMAT = "%Y-%m-%d %H-%M"


class BotActions(Protocol):
    async def send_group_text(
        self,
        event: Any,
        *,
        target_group_id: str,
        message: str,
    ) -> SendGroupTextResult:
        ...


@dataclass(frozen=True, slots=True)
class NewMemberPushResult:
    skipped_reason: str = ""
    attempted_targets: tuple[str, ...] = ()
    delivered_targets: tuple[str, ...] = ()


class NewMemberPushService:
    def __init__(self, repository: VerifyRepository, bot_actions: BotActions) -> None:
        self._repository = repository
        self._bot_actions = bot_actions

    async def handle_new_member_notice(
        self,
        event: Any,
        notice: NewMemberNotice,
    ) -> NewMemberPushResult:
        config = await self._repository.get_group_config(
            platform=notice.platform,
            group_id=notice.group_id,
        )
        if not config.enabled:
            return NewMemberPushResult(skipped_reason="group_disabled")
        if not config.push_group_ids:
            return NewMemberPushResult(skipped_reason="no_push_group")

        message = format_new_member_push_message(notice)
        delivered: list[str] = []
        for push_group_id in config.push_group_ids:
            result = await self._bot_actions.send_group_text(
                event,
                target_group_id=push_group_id,
                message=message,
            )
            if result.ok:
                delivered.append(push_group_id)
            else:
                logger.error(
                    "[CaptchaVerify] new member push failed source=%s target=%s reason=%s",
                    notice.group_id,
                    push_group_id,
                    result.reason,
                )

        return NewMemberPushResult(
            attempted_targets=config.push_group_ids,
            delivered_targets=tuple(delivered),
        )


def format_new_member_push_message(notice: NewMemberNotice) -> str:
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
        lines.append(f"时间={_format_notice_time(notice.time_raw)}")
    return "\n".join(lines)


def _format_join_type(sub_type: str) -> str:
    normalized = sub_type.strip().casefold()
    if normalized == "approve":
        return "管理员同意"
    if normalized == "invite":
        return "邀请入群"
    return sub_type


def _format_notice_time(time_raw: str) -> str:
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

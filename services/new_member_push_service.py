from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

from ..domain.models import NewMemberNotice
from ..persistence.repository import VerifyRepository
from ..platforms.bot_actions import SendGroupTextResult


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
        "Captcha Verify new member:",
        f"source_group={notice.group_id}",
        f"user_id={notice.user_id}",
    ]
    if notice.operator_id:
        lines.append(f"operator_id={notice.operator_id}")
    if notice.sub_type:
        lines.append(f"join_type={notice.sub_type}")
    if notice.time_raw:
        lines.append(f"time={notice.time_raw}")
    return "\n".join(lines)

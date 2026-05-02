from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

from ..domain.validation import is_valid_group_id


ONEBOT_ACTION_TIMEOUT_SECONDS = 10.0
FAILED_REASON_NO_ACTION_CLIENT = "onebot_action_client_missing"
FAILED_REASON_INVALID_GROUP_ID = "invalid_group_id"
FAILED_REASON_ACTION_TIMEOUT = "onebot_action_timeout"
FAILED_REASON_ACTION_FAILED = "onebot_action_failed"


class PermissionProvider(Protocol):
    def get_bot_from_event(self, event: Any) -> Any:
        ...

    async def get_bot_instance(self, platform: str = "aiocqhttp") -> Any:
        ...


@dataclass(frozen=True, slots=True)
class SendGroupTextResult:
    ok: bool
    target_group_id: str
    reason: str = ""


class BotActionService:
    def __init__(
        self,
        permissions: PermissionProvider,
        *,
        action_timeout_seconds: float = ONEBOT_ACTION_TIMEOUT_SECONDS,
    ) -> None:
        self._permissions = permissions
        self._action_timeout_seconds = action_timeout_seconds

    async def send_group_text(
        self,
        event: Any,
        *,
        target_group_id: str,
        message: str,
    ) -> SendGroupTextResult:
        group_id = target_group_id.strip()
        text = message.strip()
        if not is_valid_group_id(group_id) or not text:
            return SendGroupTextResult(
                ok=False,
                target_group_id=group_id,
                reason=FAILED_REASON_INVALID_GROUP_ID,
            )

        bot = self._permissions.get_bot_from_event(event)
        if not bot:
            bot = await self._permissions.get_bot_instance()
        if not bot or not hasattr(bot, "api"):
            return SendGroupTextResult(
                ok=False,
                target_group_id=group_id,
                reason=FAILED_REASON_NO_ACTION_CLIENT,
            )

        try:
            await asyncio.wait_for(
                bot.api.call_action(
                    "send_group_msg",
                    group_id=int(group_id),
                    message=text,
                    auto_escape=True,
                ),
                timeout=self._action_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error("[CaptchaVerify] send_group_msg timed out target=%s", group_id)
            return SendGroupTextResult(
                ok=False,
                target_group_id=group_id,
                reason=FAILED_REASON_ACTION_TIMEOUT,
            )
        except Exception as exc:
            logger.error(
                "[CaptchaVerify] send_group_msg failed target=%s error_type=%s",
                group_id,
                type(exc).__name__,
            )
            return SendGroupTextResult(
                ok=False,
                target_group_id=group_id,
                reason=FAILED_REASON_ACTION_FAILED,
            )
        return SendGroupTextResult(ok=True, target_group_id=group_id)

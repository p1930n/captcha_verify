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
FAILED_REASON_INVALID_USER_ID = "invalid_user_id"
FAILED_REASON_INVALID_MESSAGE_ID = "invalid_message_id"
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
    message_id: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class BotActionResult:
    ok: bool
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
            response = await asyncio.wait_for(
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
        return SendGroupTextResult(
            ok=True,
            target_group_id=group_id,
            message_id=_extract_message_id(response),
        )

    async def set_group_mute(
        self,
        event: Any,
        *,
        group_id: str,
        user_id: str,
        duration_seconds: int,
    ) -> BotActionResult:
        normalized_group_id = group_id.strip()
        normalized_user_id = user_id.strip()
        if not is_valid_group_id(normalized_group_id):
            return BotActionResult(ok=False, reason=FAILED_REASON_INVALID_GROUP_ID)
        if not _is_positive_int_text(normalized_user_id):
            return BotActionResult(ok=False, reason=FAILED_REASON_INVALID_USER_ID)

        return await self._call_action(
            event,
            "set_group_ban",
            group_id=int(normalized_group_id),
            user_id=int(normalized_user_id),
            duration=max(0, int(duration_seconds)),
        )

    async def add_message_reaction(
        self,
        event: Any,
        *,
        message_id: str,
        emoji_id: str,
    ) -> BotActionResult:
        normalized_message_id = message_id.strip()
        normalized_emoji_id = emoji_id.strip()
        if not _is_positive_int_text(normalized_message_id):
            return BotActionResult(ok=False, reason=FAILED_REASON_INVALID_MESSAGE_ID)
        if not normalized_emoji_id:
            return BotActionResult(ok=False, reason=FAILED_REASON_ACTION_FAILED)

        return await self._call_action(
            event,
            "set_msg_emoji_like",
            message_id=int(normalized_message_id),
            emoji_id=normalized_emoji_id,
        )

    async def _call_action(self, event: Any, action: str, **params: Any) -> BotActionResult:
        bot = self._permissions.get_bot_from_event(event)
        if not bot:
            bot = await self._permissions.get_bot_instance()
        if not bot or not hasattr(bot, "api"):
            return BotActionResult(ok=False, reason=FAILED_REASON_NO_ACTION_CLIENT)

        try:
            await asyncio.wait_for(
                bot.api.call_action(action, **params),
                timeout=self._action_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error("[CaptchaVerify] OneBot action timed out action=%s", action)
            return BotActionResult(ok=False, reason=FAILED_REASON_ACTION_TIMEOUT)
        except Exception as exc:
            logger.error(
                "[CaptchaVerify] OneBot action failed action=%s error_type=%s",
                action,
                type(exc).__name__,
            )
            return BotActionResult(ok=False, reason=FAILED_REASON_ACTION_FAILED)
        return BotActionResult(ok=True)


def _extract_message_id(response: Any) -> str:
    candidates: list[Any] = [response]
    data = _value(response, "data")
    if data is not None:
        candidates.append(data)
    for candidate in candidates:
        message_id = _value(candidate, "message_id")
        if message_id is not None:
            return str(message_id).strip()
    return ""


def _value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    try:
        return getattr(source, key, None)
    except Exception:
        return None


def _is_positive_int_text(value: str) -> bool:
    try:
        parsed = int(value, 10)
    except ValueError:
        return False
    return parsed > 0

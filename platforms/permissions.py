from __future__ import annotations

from typing import Any

import astrbot.api.event.filter as filter
import astrbot.api.star as star
from astrbot.api import logger


class PermissionService:
    def __init__(self, context: star.Context) -> None:
        self._context = context

    async def get_bot_instance(self, platform: str = "aiocqhttp") -> Any:
        try:
            if platform != "aiocqhttp":
                return None
            adapter = self._context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
            if adapter and hasattr(adapter, "get_client"):
                return adapter.get_client()
            return adapter
        except Exception as exc:
            logger.error("[CaptchaVerify] get bot instance failed: %s", exc)
            return None

    def get_bot_from_event(self, event: Any) -> Any:
        try:
            if event.get_platform_name() != "aiocqhttp":
                return None

            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )

            if isinstance(event, AiocqhttpMessageEvent):
                return event.bot
            return None
        except Exception as exc:
            logger.error("[CaptchaVerify] get bot from event failed: %s", exc)
            return None

    def is_global_admin(self, event: Any) -> bool:
        try:
            user_id = str(event.get_sender_id())
            if not hasattr(self._context, "get_config"):
                return False

            config = self._context.get_config()
            admins = _config_value(config, "admins_id")
            if admins is None:
                admins = _config_value(config, "admin_ids")
            return user_id in _normalized_id_set(admins)
        except Exception:
            return False

    async def is_group_admin_or_owner(
        self,
        event: Any,
        user_id: str,
        group_id: str,
    ) -> bool:
        try:
            bot = self.get_bot_from_event(event)
            if not bot:
                bot = await self.get_bot_instance()
            if not bot or not hasattr(bot, "api"):
                return False

            member_info = await bot.api.call_action(
                "get_group_member_info",
                group_id=int(group_id),
                user_id=int(user_id),
            )
            role = str(member_info.get("role", "member"))
            return role in {"admin", "owner"}
        except Exception as exc:
            logger.error("[CaptchaVerify] group admin check failed: %s", exc)
            return False


def _config_value(config: object, key: str) -> object:
    if hasattr(config, "get"):
        try:
            value = config.get(key)
        except Exception:
            value = None
        if value is not None:
            return value
    try:
        return getattr(config, key, None)
    except Exception:
        return None


def _normalized_id_set(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {
            item
            for item in (part.strip() for part in value.replace(",", " ").split())
            if item
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return {item for item in (str(raw).strip() for raw in value) if item}
    normalized = str(value).strip()
    if not normalized:
        return set()
    return {normalized}

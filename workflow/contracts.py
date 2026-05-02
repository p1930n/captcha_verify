from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..platforms.bot_actions import BotActionResult, SendGroupTextResult


class BotActions(Protocol):
    async def send_group_text(
        self,
        event: Any,
        *,
        target_group_id: str,
        message: str,
    ) -> SendGroupTextResult:
        ...

    async def set_group_mute(
        self,
        event: Any,
        *,
        group_id: str,
        user_id: str,
        duration_seconds: int,
    ) -> BotActionResult:
        ...

    async def add_message_reaction(
        self,
        event: Any,
        *,
        message_id: str,
        emoji_id: str,
    ) -> BotActionResult:
        ...

    async def kick_group_member(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        reject_add_request: bool = False,
    ) -> BotActionResult:
        ...


class PermissionProvider(Protocol):
    def is_global_admin_id(self, user_id: str) -> bool:
        ...

    async def is_group_admin_or_owner(
        self,
        event: Any,
        user_id: str,
        group_id: str,
    ) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    handled: bool
    reason: str = ""

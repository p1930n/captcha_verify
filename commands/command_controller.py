from __future__ import annotations

from typing import Any, Protocol

from ..domain.models import PlatformEventSnapshot
from ..domain.validation import is_valid_group_id, parse_timeout_seconds
from .command_service import VerifyCommandService


COMMAND_PERMISSION_DENIED = (
    "权限不足：需要 AstrBot 管理员权限，或当前 QQ 群的群主/管理员权限。"
)
GLOBAL_PERMISSION_DENIED = "权限不足：该操作需要 AstrBot 管理员权限。"
GROUP_SCOPE_REQUIRED = "缺少群上下文：请在群内执行，或显式传入群号。"
ENABLE_USAGE = "用法：.verify enable [group_id]"
DISABLE_USAGE = "用法：.verify disable [group_id]"
STATUS_USAGE = "用法：.verify status [group_id]"
BIND_USAGE = (
    "用法：.verify bind <push_group_id>\n"
    "用法：.verify bind <group_id> <push_group_id>"
)
OVERVIEW_USAGE = "用法：.verify overview [csv]"
SET_USAGE = (
    "用法：.verify set timeout [seconds]\n"
    "用法：.verify set timeout <group_id> <seconds>"
)


class PermissionProvider(Protocol):
    def is_global_admin(self, event: Any) -> bool:
        ...

    async def is_group_admin_or_owner(
        self,
        event: Any,
        user_id: str,
        group_id: str,
    ) -> bool:
        ...


class VerifyCommandController:
    def __init__(
        self,
        command_service: VerifyCommandService,
        permissions: PermissionProvider,
    ) -> None:
        self._command_service = command_service
        self._permissions = permissions

    async def enable(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = _target_group_id(snapshot, group_id)
        if target_group_id is None:
            return ENABLE_USAGE
        denial = await self._manage_denial(event, snapshot, target_group_id)
        if denial:
            return denial
        return await self._command_service.set_enabled(
            platform=snapshot.platform,
            group_id=target_group_id,
            enabled=True,
            updated_by=snapshot.sender_id,
        )

    async def disable(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = _target_group_id(snapshot, group_id)
        if target_group_id is None:
            return DISABLE_USAGE
        denial = await self._manage_denial(event, snapshot, target_group_id)
        if denial:
            return denial
        return await self._command_service.set_enabled(
            platform=snapshot.platform,
            group_id=target_group_id,
            enabled=False,
            updated_by=snapshot.sender_id,
        )

    async def status(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
        group_id: str = "",
    ) -> str:
        target_group_id = _target_group_id(snapshot, group_id)
        if target_group_id is None:
            return STATUS_USAGE
        denial = await self._manage_denial(event, snapshot, target_group_id)
        if denial:
            return denial
        return await self._command_service.format_status(
            platform=snapshot.platform,
            group_id=target_group_id,
        )

    async def bind(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
        first: str = "",
        second: str = "",
    ) -> str:
        resolved = _resolve_bind_args(snapshot, first, second)
        if resolved is None:
            return BIND_USAGE
        group_id, push_group_id = resolved
        denial = await self._manage_denial(event, snapshot, group_id)
        if denial:
            return denial
        return await self._command_service.bind_push_group(
            platform=snapshot.platform,
            group_id=group_id,
            push_group_id=push_group_id,
            created_by=snapshot.sender_id,
        )

    async def overview(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
        output_format: str = "",
    ) -> str:
        if not snapshot.platform:
            return OVERVIEW_USAGE
        if not self._permissions.is_global_admin(event):
            return GLOBAL_PERMISSION_DENIED
        return await self._command_service.format_overview(
            platform=snapshot.platform,
            output_format=output_format,
        )

    async def set(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
        key: str = "",
        first: str = "",
        second: str = "",
    ) -> str:
        if key.strip().casefold() != "timeout":
            return SET_USAGE
        resolved = _resolve_timeout_args(snapshot, first, second)
        if resolved is None:
            return SET_USAGE
        group_id, timeout_seconds = resolved
        denial = await self._manage_denial(event, snapshot, group_id)
        if denial:
            return denial
        return await self._command_service.set_timeout_seconds(
            platform=snapshot.platform,
            group_id=group_id,
            timeout_seconds=timeout_seconds,
            updated_by=snapshot.sender_id,
        )

    async def help(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
    ) -> str:
        if not await self._can_manage_current_group(event, snapshot):
            return COMMAND_PERMISSION_DENIED
        return self._command_service.format_help()

    async def _manage_denial(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
        target_group_id: str,
    ) -> str | None:
        if not snapshot.platform:
            return GROUP_SCOPE_REQUIRED
        if self._permissions.is_global_admin(event):
            return None
        if snapshot.group_id != target_group_id:
            return GLOBAL_PERMISSION_DENIED
        if not await self._can_manage_current_group(event, snapshot):
            return COMMAND_PERMISSION_DENIED
        return None

    async def _can_manage_current_group(
        self,
        event: Any,
        snapshot: PlatformEventSnapshot,
    ) -> bool:
        if self._permissions.is_global_admin(event):
            return True
        if not snapshot.group_id or not snapshot.sender_id:
            return False
        if snapshot.sender_is_group_manager:
            return True
        return await self._permissions.is_group_admin_or_owner(
            event,
            snapshot.sender_id,
            snapshot.group_id,
        )


def _target_group_id(snapshot: PlatformEventSnapshot, group_id: str = "") -> str | None:
    target_group_id = group_id.strip()
    if not target_group_id:
        target_group_id = snapshot.group_id
    if not target_group_id or not is_valid_group_id(target_group_id):
        return None
    return target_group_id


def _resolve_bind_args(
    snapshot: PlatformEventSnapshot,
    first: str,
    second: str,
) -> tuple[str, str] | None:
    first = first.strip()
    second = second.strip()
    if first and not second:
        if not snapshot.group_id or not is_valid_group_id(first):
            return None
        return snapshot.group_id, first
    if first and second and is_valid_group_id(first) and is_valid_group_id(second):
        return first, second
    return None


def _resolve_timeout_args(
    snapshot: PlatformEventSnapshot,
    first: str,
    second: str,
) -> tuple[str, int] | None:
    first = first.strip()
    second = second.strip()
    if first and not second:
        timeout_seconds = parse_timeout_seconds(first)
        if timeout_seconds is None or not snapshot.group_id:
            return None
        return snapshot.group_id, timeout_seconds
    if first and second and is_valid_group_id(first):
        timeout_seconds = parse_timeout_seconds(second)
        if timeout_seconds is None:
            return None
        return first, timeout_seconds
    return None

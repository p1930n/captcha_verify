from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.star import Context, Star, register

from .commands.command_controller import VerifyCommandController
from .commands.command_service import VerifyCommandService
from .domain.notice_adapter import parse_new_member_notice
from .persistence.repository import VerifyRepository, default_data_root
from .platforms.bot_actions import BotActionService
from .platforms.event_adapter import (
    dehydrate_event_snapshot,
    extract_raw_notice_payload,
)
from .platforms.permissions import PermissionService
from .services.new_member_push_service import NewMemberPushService


PLUGIN_NAME = "astrbot_plugin_captcha_verify"
PLUGIN_AUTHOR = "p1930n"
PLUGIN_DESCRIPTION = "QQ 群新人入群审核与推送通知插件。"
PLUGIN_VERSION = "0.1.0"
PLUGIN_REPO = ""
PLUGIN_LOADING_MESSAGE = "验证码入群审核插件仍在加载中。"


@register(
    PLUGIN_NAME,
    PLUGIN_AUTHOR,
    PLUGIN_DESCRIPTION,
    PLUGIN_VERSION,
    PLUGIN_REPO,
)
class CaptchaVerifyPlugin(Star):
    def __init__(self, context: Context, config: Any | None = None) -> None:
        super().__init__(context)
        _ = config
        self._data_root = Path(default_data_root())
        self._repository = VerifyRepository(self._data_root)
        self._permissions = PermissionService(context)
        self._bot_actions = BotActionService(self._permissions)
        self._command_service = VerifyCommandService(self._repository)
        self._command_controller = VerifyCommandController(
            self._command_service,
            self._permissions,
        )
        self._new_member_push_service = NewMemberPushService(
            self._repository,
            self._bot_actions,
        )
        self._ready = False
        self._init_task: asyncio.Task | None = asyncio.create_task(self._initialize())

    async def _initialize(self) -> None:
        try:
            await self._repository.initialize()
            self._ready = True
            logger.info("[CaptchaVerify] ready data_root=%s", self._data_root)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[CaptchaVerify] init failed: %s", exc, exc_info=True)

    async def terminate(self) -> None:
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
            result = await asyncio.gather(self._init_task, return_exceptions=True)
            if result and isinstance(result[0], BaseException) and not isinstance(
                result[0],
                asyncio.CancelledError,
            ):
                logger.error(
                    "[CaptchaVerify] init task shutdown failed: %s",
                    result[0],
                    exc_info=result[0],
                )
        self._init_task = None

    @filter.command_group("verify")
    def verify():
        pass

    @verify.command("enable")
    async def verify_enable(self, event: AstrMessageEvent, group_id: str = ""):
        yield event.plain_result(
            await self._handle_command(event, self._command_controller.enable, group_id)
        )

    @verify.command("disable")
    async def verify_disable(self, event: AstrMessageEvent, group_id: str = ""):
        yield event.plain_result(
            await self._handle_command(event, self._command_controller.disable, group_id)
        )

    @verify.command("status")
    async def verify_status(self, event: AstrMessageEvent, group_id: str = ""):
        yield event.plain_result(
            await self._handle_command(event, self._command_controller.status, group_id)
        )

    @verify.command("bind")
    async def verify_bind(
        self,
        event: AstrMessageEvent,
        group_id_or_push_group_id: str = "",
        push_group_id: str = "",
    ):
        yield event.plain_result(
            await self._handle_command(
                event,
                self._command_controller.bind,
                group_id_or_push_group_id,
                push_group_id,
            )
        )

    @verify.command("overview")
    async def verify_overview(
        self,
        event: AstrMessageEvent,
        output_format: str = "",
    ):
        yield event.plain_result(
            await self._handle_command(
                event,
                self._command_controller.overview,
                output_format,
            )
        )

    @verify.command("help")
    async def verify_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            await self._handle_command(event, self._command_controller.help)
        )

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_raw_notice(self, event: AstrMessageEvent):
        if not self._ready:
            return MessageEventResult()

        payload = extract_raw_notice_payload(event)
        if not payload:
            return MessageEventResult()

        snapshot = dehydrate_event_snapshot(event)
        if not snapshot.platform:
            return MessageEventResult()

        notice = parse_new_member_notice(payload, platform=snapshot.platform)
        if notice is None:
            return MessageEventResult()

        try:
            await self._new_member_push_service.handle_new_member_notice(event, notice)
        except Exception as exc:
            logger.error(
                "[CaptchaVerify] new member notice handling failed group=%s err=%s",
                notice.group_id,
                exc,
                exc_info=True,
            )
        return MessageEventResult()

    async def _handle_command(
        self,
        event: AstrMessageEvent,
        handler: Any,
        *args: str,
    ) -> str:
        if not self._ready:
            return PLUGIN_LOADING_MESSAGE

        snapshot = dehydrate_event_snapshot(event)
        try:
            return await handler(event, snapshot, *args)
        except Exception as exc:
            logger.error("[CaptchaVerify] command failed: %s", exc, exc_info=True)
            return "验证码入群审核命令执行失败。"

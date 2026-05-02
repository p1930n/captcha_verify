from __future__ import annotations

from typing import Any

from ..domain.models import (
    APPROVAL_SOURCE_PRIVATE_MESSAGE,
    GroupEmojiReactionNotice,
    PrivateMessageNotice,
    VerificationSession,
)
from ..persistence.repository import VerifyRepository
from ._logging import logger
from .contracts import BotActions, WorkflowResult
from .messages import format_approval_log, format_approval_log_en, utc_now_text


class VerificationPrivateMessageHandler:
    def __init__(
        self,
        repository: VerifyRepository,
        bot_actions: BotActions,
    ) -> None:
        self._repository = repository
        self._bot_actions = bot_actions

    async def handle(
        self,
        event: Any,
        notice: PrivateMessageNotice,
    ) -> WorkflowResult:
        sessions = await self._repository.list_pending_sessions_by_user(
            platform=notice.platform,
            user_id=notice.user_id,
        )
        if not sessions:
            return WorkflowResult(handled=False, reason="session_not_found")

        handled = False
        for session in sessions:
            result = await self._approve(event, notice, session)
            handled = handled or result.handled
        return WorkflowResult(handled=handled, reason="" if handled else "already_resolved")

    async def _approve(
        self,
        event: Any,
        notice: PrivateMessageNotice,
        session: VerificationSession,
    ) -> WorkflowResult:
        approved = await self._repository.approve_verification_session(
            session_id=session.id,
            approver_id=notice.user_id,
            approval_source=APPROVAL_SOURCE_PRIVATE_MESSAGE,
            approval_group_id="",
            approval_message_id=notice.message_id,
            approved_at=utc_now_text(),
        )
        if approved is None:
            return WorkflowResult(handled=False, reason="already_resolved")

        unmute_result = await self._bot_actions.set_group_mute(
            event,
            group_id=approved.group_id,
            user_id=approved.user_id,
            duration_seconds=0,
        )
        if not unmute_result.ok:
            logger.error(
                "[CaptchaVerify] unmute private verified member failed group=%s user=%s reason=%s",
                approved.group_id,
                approved.user_id,
                unmute_result.reason,
            )

        await self._send_approval_logs(event, approved, notice)
        return WorkflowResult(handled=True)

    async def _send_approval_logs(
        self,
        event: Any,
        session: VerificationSession,
        notice: PrivateMessageNotice,
    ) -> None:
        push_messages = await self._repository.list_verification_push_messages(
            session_id=session.id,
        )
        push_group_ids = tuple(
            dict.fromkeys(push_message.push_group_id for push_message in push_messages)
        )
        if not push_group_ids:
            push_group_ids = await self._repository.list_enabled_push_group_ids(
                platform=session.platform,
                group_id=session.group_id,
            )

        reaction = GroupEmojiReactionNotice(
            platform=notice.platform,
            group_id="",
            user_id=notice.user_id,
            self_id="",
            message_id=notice.message_id,
            emoji_ids=(),
            time_raw=notice.time_raw,
        )
        message = format_approval_log(session, reaction)
        english_message = format_approval_log_en(session, reaction)
        for push_group_id in push_group_ids:
            result = await self._bot_actions.send_group_text(
                event,
                target_group_id=push_group_id,
                message=message,
            )
            if not result.ok:
                logger.error(
                    "[CaptchaVerify] private approval log send failed group=%s push=%s reason=%s",
                    session.group_id,
                    push_group_id,
                    result.reason,
                )
            english_result = await self._bot_actions.send_group_text(
                event,
                target_group_id=push_group_id,
                message=english_message,
            )
            if not english_result.ok:
                logger.error(
                    "[CaptchaVerify] private english approval log send failed group=%s push=%s reason=%s",
                    session.group_id,
                    push_group_id,
                    english_result.reason,
                )

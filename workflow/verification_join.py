from __future__ import annotations

from typing import Any

from ..domain.models import NewMemberNotice, VerificationSession
from ..persistence.blacklist_repository import BlacklistRepository
from ..persistence.repository import VerifyRepository
from ..platforms.bot_actions import SendGroupTextResult
from ._logging import logger
from .contracts import BotActions, WorkflowResult
from .messages import (
    format_push_verification_log_en,
    format_push_verification_log,
    format_source_verification_prompt,
    utc_after_seconds_text,
)


class VerificationJoinHandler:
    def __init__(
        self,
        repository: VerifyRepository,
        blacklist_repository: BlacklistRepository,
        bot_actions: BotActions,
        *,
        ok_emoji_id: str,
        question_emoji_id: str,
    ) -> None:
        self._repository = repository
        self._blacklist_repository = blacklist_repository
        self._bot_actions = bot_actions
        self._ok_emoji_id = ok_emoji_id
        self._question_emoji_id = question_emoji_id

    async def handle(
        self,
        event: Any,
        notice: NewMemberNotice,
    ) -> WorkflowResult:
        config = await self._repository.get_group_config(
            platform=notice.platform,
            group_id=notice.group_id,
        )
        if not config.enabled:
            return WorkflowResult(handled=False, reason="group_disabled")
        if config.blacklist_kick_enabled and await self._blacklist_repository.is_group_blacklisted(
            platform=notice.platform,
            group_id=notice.group_id,
            user_id=notice.user_id,
        ):
            await self._kick_blacklisted_member(notice)
            return WorkflowResult(handled=True, reason="blacklisted_member_kicked")

        window_seconds = config.verify_window_seconds
        expires_at = utc_after_seconds_text(window_seconds)
        session = await self._repository.create_pending_verification_session(
            platform=notice.platform,
            group_id=notice.group_id,
            user_id=notice.user_id,
            muted_until=expires_at,
            verify_window_seconds=window_seconds,
            expires_at=expires_at,
        )

        await self._mute_new_member(event, notice, session)
        prompt_result = await self._send_source_prompt(event, notice, session)
        source_prompt_message_id = prompt_result.message_id if prompt_result.ok else ""

        for push_group_id in config.push_group_ids:
            await self._send_push_prompt(
                event,
                notice,
                session,
                push_group_id,
                source_prompt_message_id,
            )

        return WorkflowResult(handled=True)

    async def _mute_new_member(
        self,
        event: Any,
        notice: NewMemberNotice,
        session: VerificationSession,
    ) -> None:
        result = await self._bot_actions.set_group_mute(
            event,
            group_id=session.group_id,
            user_id=session.user_id,
            duration_seconds=session.verify_window_seconds,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] mute new member failed group=%s user=%s reason=%s",
                notice.group_id,
                notice.user_id,
                result.reason,
            )

    async def _send_source_prompt(
        self,
        event: Any,
        notice: NewMemberNotice,
        session: VerificationSession,
    ) -> SendGroupTextResult:
        result = await self._bot_actions.send_group_text(
            event,
            target_group_id=notice.group_id,
            message=format_source_verification_prompt(
                verification_window_seconds=session.verify_window_seconds,
            ),
        )
        if result.ok and result.message_id:
            await self._repository.set_verification_prompt_message(
                session_id=session.id,
                prompt_message_id=result.message_id,
            )
            if await self._react(event, result.message_id, self._ok_emoji_id):
                await self._repository.mark_verification_prompt_approval_ready(
                    session_id=session.id,
                    prompt_message_id=result.message_id,
                )
            if await self._react(event, result.message_id, self._question_emoji_id):
                await self._repository.mark_verification_prompt_rejection_ready(
                    session_id=session.id,
                    prompt_message_id=result.message_id,
                )
        else:
            logger.error(
                "[CaptchaVerify] source prompt send failed group=%s user=%s reason=%s",
                notice.group_id,
                notice.user_id,
                result.reason,
            )
        return result

    async def _send_push_prompt(
        self,
        event: Any,
        notice: NewMemberNotice,
        session: VerificationSession,
        push_group_id: str,
        source_prompt_message_id: str,
    ) -> None:
        result = await self._bot_actions.send_group_text(
            event,
            target_group_id=push_group_id,
            message=format_push_verification_log(
                notice,
                source_prompt_message_id=source_prompt_message_id,
            ),
        )
        if result.ok and result.message_id:
            await self._bot_actions.send_group_text(
                event,
                target_group_id=push_group_id,
                message=format_push_verification_log_en(
                    notice,
                    source_prompt_message_id=source_prompt_message_id,
                ),
            )
            await self._repository.add_verification_push_message(
                session_id=session.id,
                push_group_id=push_group_id,
                message_id=result.message_id,
            )
            if await self._react(event, result.message_id, self._ok_emoji_id):
                await self._repository.mark_verification_push_message_approval_ready(
                    session_id=session.id,
                    push_group_id=push_group_id,
                    message_id=result.message_id,
                )
            if await self._react(event, result.message_id, self._question_emoji_id):
                await self._repository.mark_verification_push_message_rejection_ready(
                    session_id=session.id,
                    push_group_id=push_group_id,
                    message_id=result.message_id,
                )
            return

        logger.error(
            "[CaptchaVerify] push prompt send failed source=%s push=%s reason=%s",
            notice.group_id,
            push_group_id,
            result.reason,
        )

    async def _kick_blacklisted_member(self, notice: NewMemberNotice) -> None:
        result = await self._bot_actions.kick_group_member(
            platform=notice.platform,
            group_id=notice.group_id,
            user_id=notice.user_id,
            reject_add_request=False,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] kick blacklisted member failed group=%s user=%s reason=%s",
                notice.group_id,
                notice.user_id,
                result.reason,
            )

    async def _react(self, event: Any, message_id: str, emoji_id: str) -> bool:
        result = await self._bot_actions.add_message_reaction(
            event,
            message_id=message_id,
            emoji_id=emoji_id,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] prompt reaction failed message=%s emoji=%s reason=%s",
                message_id,
                emoji_id,
                result.reason,
            )
            return False
        return True

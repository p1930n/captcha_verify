from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

from ..domain.models import (
    APPROVAL_SOURCE_GROUP_PROMPT,
    APPROVAL_SOURCE_PUSH_PROMPT,
    GroupEmojiReactionNotice,
    NewMemberNotice,
    VerificationSession,
)
from ..persistence.repository import VerifyRepository
from ..platforms.bot_actions import BotActionResult, SendGroupTextResult
from .messages import (
    format_approval_log,
    format_push_verification_log,
    format_source_verification_prompt,
    utc_after_seconds_text,
    utc_now_text,
)


OK_EMOJI_ID = "128076"
OK_EMOJI_SYMBOL = "👌"


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


class VerificationWorkflow:
    def __init__(
        self,
        repository: VerifyRepository,
        bot_actions: BotActions,
        permissions: PermissionProvider,
        *,
        ok_emoji_id: str = OK_EMOJI_ID,
    ) -> None:
        self._repository = repository
        self._bot_actions = bot_actions
        self._permissions = permissions
        self._ok_emoji_id = ok_emoji_id
        self._ok_emoji_ids = _accepted_ok_emoji_ids(ok_emoji_id)

    async def handle_new_member_joined(
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

        window_seconds = config.verify_window_seconds
        session = await self._repository.create_pending_verification_session(
            platform=notice.platform,
            group_id=notice.group_id,
            user_id=notice.user_id,
            muted_until=utc_after_seconds_text(window_seconds),
            verify_window_seconds=window_seconds,
            expires_at=utc_after_seconds_text(window_seconds),
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

    async def handle_emoji_reaction(
        self,
        event: Any,
        reaction: GroupEmojiReactionNotice,
    ) -> WorkflowResult:
        if reaction.self_id and reaction.user_id == reaction.self_id:
            return WorkflowResult(handled=False, reason="self_reaction_ignored")
        if not self._ok_emoji_ids.intersection(reaction.emoji_ids):
            return WorkflowResult(handled=False, reason="emoji_mismatch")

        source_session = await self._repository.find_pending_session_by_group_prompt(
            platform=reaction.platform,
            group_id=reaction.group_id,
            message_id=reaction.message_id,
        )
        if source_session is not None:
            if not await self._can_approve_from_source_group(event, reaction, source_session):
                return WorkflowResult(handled=False, reason="source_reaction_denied")
            return await self._approve(
                event,
                reaction,
                source_session,
                approval_source=APPROVAL_SOURCE_GROUP_PROMPT,
            )

        push_session = await self._repository.find_pending_session_by_push_prompt(
            platform=reaction.platform,
            push_group_id=reaction.group_id,
            message_id=reaction.message_id,
        )
        if push_session is None:
            return WorkflowResult(handled=False, reason="session_not_found")

        return await self._approve(
            event,
            reaction,
            push_session,
            approval_source=APPROVAL_SOURCE_PUSH_PROMPT,
        )

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
            if await self._react_ok(event, result.message_id):
                await self._repository.mark_verification_prompt_approval_ready(
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
            await self._repository.add_verification_push_message(
                session_id=session.id,
                push_group_id=push_group_id,
                message_id=result.message_id,
            )
            if await self._react_ok(event, result.message_id):
                await self._repository.mark_verification_push_message_approval_ready(
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

    async def _can_approve_from_source_group(
        self,
        event: Any,
        reaction: GroupEmojiReactionNotice,
        session: VerificationSession,
    ) -> bool:
        if reaction.user_id == session.user_id:
            return True
        if self._permissions.is_global_admin_id(reaction.user_id):
            return True
        return await self._permissions.is_group_admin_or_owner(
            event,
            reaction.user_id,
            session.group_id,
        )

    async def _approve(
        self,
        event: Any,
        reaction: GroupEmojiReactionNotice,
        session: VerificationSession,
        *,
        approval_source: str,
    ) -> WorkflowResult:
        approved = await self._repository.approve_verification_session(
            session_id=session.id,
            approver_id=reaction.user_id,
            approval_source=approval_source,
            approval_group_id=reaction.group_id,
            approval_message_id=reaction.message_id,
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
                "[CaptchaVerify] unmute approved member failed group=%s user=%s reason=%s",
                approved.group_id,
                approved.user_id,
                unmute_result.reason,
            )

        await self._send_approval_logs(event, approved, reaction)
        return WorkflowResult(handled=True)

    async def _send_approval_logs(
        self,
        event: Any,
        session: VerificationSession,
        reaction: GroupEmojiReactionNotice,
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

        message = format_approval_log(session, reaction)
        for push_group_id in push_group_ids:
            result = await self._bot_actions.send_group_text(
                event,
                target_group_id=push_group_id,
                message=message,
            )
            if not result.ok:
                logger.error(
                    "[CaptchaVerify] approval log send failed group=%s push=%s reason=%s",
                    session.group_id,
                    push_group_id,
                    result.reason,
                )

    async def _react_ok(self, event: Any, message_id: str) -> bool:
        result = await self._bot_actions.add_message_reaction(
            event,
            message_id=message_id,
            emoji_id=self._ok_emoji_id,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] ok hand reaction failed message=%s reason=%s",
                message_id,
                result.reason,
            )
            return False
        return True


def _accepted_ok_emoji_ids(ok_emoji_id: str) -> frozenset[str]:
    if ok_emoji_id == OK_EMOJI_ID:
        return frozenset((OK_EMOJI_ID, OK_EMOJI_SYMBOL))
    return frozenset((ok_emoji_id,))

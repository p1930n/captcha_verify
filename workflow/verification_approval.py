from __future__ import annotations

from typing import Any

from ..domain.models import (
    APPROVAL_SOURCE_GROUP_PROMPT,
    APPROVAL_SOURCE_PUSH_PROMPT,
    GroupEmojiReactionNotice,
    VerificationSession,
)
from ..persistence.blacklist_repository import BlacklistRepository
from ..persistence.repository import VerifyRepository
from ._logging import logger
from .contracts import BotActions, PermissionProvider, WorkflowResult
from .messages import (
    format_approval_log,
    format_approval_log_en,
    format_rejection_log,
    format_rejection_log_en,
    utc_now_text,
)


class VerificationApprovalHandler:
    def __init__(
        self,
        repository: VerifyRepository,
        blacklist_repository: BlacklistRepository,
        bot_actions: BotActions,
        permissions: PermissionProvider,
        *,
        ok_emoji_ids: frozenset[str],
        question_emoji_ids: frozenset[str],
    ) -> None:
        self._repository = repository
        self._blacklist_repository = blacklist_repository
        self._bot_actions = bot_actions
        self._permissions = permissions
        self._ok_emoji_ids = ok_emoji_ids
        self._question_emoji_ids = question_emoji_ids

    async def handle(
        self,
        event: Any,
        reaction: GroupEmojiReactionNotice,
    ) -> WorkflowResult:
        if reaction.self_id and reaction.user_id == reaction.self_id:
            return WorkflowResult(handled=False, reason="self_reaction_ignored")
        if self._question_emoji_ids.intersection(reaction.emoji_ids):
            return await self._handle_rejection(event, reaction)
        if not self._ok_emoji_ids.intersection(reaction.emoji_ids):
            return WorkflowResult(handled=False, reason="emoji_mismatch")

        source_session = await self._repository.find_pending_session_by_group_prompt(
            platform=reaction.platform,
            group_id=reaction.group_id,
            message_id=reaction.message_id,
        )
        if source_session is not None:
            allowed = await self._can_approve_from_source_group(
                event,
                reaction,
                source_session,
            )
            if not allowed:
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

    async def _handle_rejection(
        self,
        event: Any,
        reaction: GroupEmojiReactionNotice,
    ) -> WorkflowResult:
        source_session = (
            await self._repository.find_pending_session_by_group_prompt_for_rejection(
                platform=reaction.platform,
                group_id=reaction.group_id,
                message_id=reaction.message_id,
            )
        )
        if source_session is not None:
            allowed = await self._permissions.is_group_admin_or_owner(
                event,
                reaction.user_id,
                source_session.group_id,
            )
            if not allowed:
                return WorkflowResult(handled=False, reason="source_rejection_denied")
            return await self._reject(event, reaction, source_session)

        push_session = (
            await self._repository.find_pending_session_by_push_prompt_for_rejection(
                platform=reaction.platform,
                push_group_id=reaction.group_id,
                message_id=reaction.message_id,
            )
        )
        if push_session is None:
            return WorkflowResult(handled=False, reason="session_not_found")
        return await self._reject(event, reaction, push_session)

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

        await self._delete_source_prompt_if_enabled(approved)
        await self._send_approval_logs(event, approved, reaction)
        return WorkflowResult(handled=True)

    async def _reject(
        self,
        event: Any,
        reaction: GroupEmojiReactionNotice,
        session: VerificationSession,
    ) -> WorkflowResult:
        rejected = await self._repository.expire_verification_session(
            session_id=session.id,
            expired_at=utc_now_text(),
        )
        if rejected is None:
            return WorkflowResult(handled=False, reason="already_resolved")

        await self._blacklist_repository.add_group_blacklist_entry(
            platform=rejected.platform,
            group_id=rejected.group_id,
            user_id=rejected.user_id,
            operator_id=reaction.user_id,
            reason="question_reaction",
        )

        kick_result = await self._bot_actions.kick_group_member(
            platform=rejected.platform,
            group_id=rejected.group_id,
            user_id=rejected.user_id,
            reject_add_request=False,
        )
        if not kick_result.ok:
            logger.error(
                "[CaptchaVerify] kick rejected member failed group=%s user=%s reason=%s",
                rejected.group_id,
                rejected.user_id,
                kick_result.reason,
            )

        await self._delete_source_prompt_if_enabled(rejected)
        await self._send_rejection_logs(event, rejected, reaction)
        return WorkflowResult(handled=True)

    async def _delete_source_prompt_if_enabled(
        self,
        session: VerificationSession,
    ) -> None:
        if not session.prompt_message_id:
            return
        config = await self._repository.get_group_config(
            platform=session.platform,
            group_id=session.group_id,
        )
        if not config.revoke_prompt_enabled:
            return
        result = await self._bot_actions.delete_message(
            platform=session.platform,
            message_id=session.prompt_message_id,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] delete source prompt failed group=%s message=%s reason=%s",
                session.group_id,
                session.prompt_message_id,
                result.reason,
            )

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
        english_message = format_approval_log_en(session, reaction)
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
            await self._send_english_log(
                event,
                push_group_id=push_group_id,
                source_group_id=session.group_id,
                message=english_message,
                log_type="approval",
            )

    async def _send_rejection_logs(
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

        message = format_rejection_log(session, reaction)
        english_message = format_rejection_log_en(session, reaction)
        for push_group_id in push_group_ids:
            result = await self._bot_actions.send_group_text(
                event,
                target_group_id=push_group_id,
                message=message,
            )
            if not result.ok:
                logger.error(
                    "[CaptchaVerify] rejection log send failed group=%s push=%s reason=%s",
                    session.group_id,
                    push_group_id,
                    result.reason,
                )
            await self._send_english_log(
                event,
                push_group_id=push_group_id,
                source_group_id=session.group_id,
                message=english_message,
                log_type="rejection",
            )

    async def _send_english_log(
        self,
        event: Any,
        *,
        push_group_id: str,
        source_group_id: str,
        message: str,
        log_type: str,
    ) -> None:
        result = await self._bot_actions.send_group_text(
            event,
            target_group_id=push_group_id,
            message=message,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] english %s log send failed group=%s push=%s reason=%s",
                log_type,
                source_group_id,
                push_group_id,
                result.reason,
            )

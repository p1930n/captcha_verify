from __future__ import annotations

from typing import Any

from ..domain.models import GroupEmojiReactionNotice, NewMemberNotice, PrivateMessageNotice
from ..persistence.blacklist_repository import BlacklistRepository
from ..persistence.repository import VerifyRepository
from .contracts import BotActions, PermissionProvider, WorkflowResult
from .emoji import (
    OK_EMOJI_ID,
    OK_EMOJI_SYMBOL,
    QUESTION_EMOJI_ID,
    QUESTION_EMOJI_LEGACY_ID,
    QUESTION_EMOJI_SYMBOL,
    accepted_ok_emoji_ids,
    accepted_question_emoji_ids,
)
from .verification_approval import VerificationApprovalHandler
from .verification_join import VerificationJoinHandler
from .verification_private import VerificationPrivateMessageHandler


class VerificationWorkflow:
    def __init__(
        self,
        repository: VerifyRepository,
        blacklist_repository: BlacklistRepository,
        bot_actions: BotActions,
        permissions: PermissionProvider,
        *,
        ok_emoji_id: str = OK_EMOJI_ID,
        question_emoji_id: str = QUESTION_EMOJI_ID,
    ) -> None:
        ok_emoji_ids = accepted_ok_emoji_ids(ok_emoji_id)
        question_emoji_ids = accepted_question_emoji_ids(question_emoji_id)
        self._join_handler = VerificationJoinHandler(
            repository,
            blacklist_repository,
            bot_actions,
            ok_emoji_id=ok_emoji_id,
            question_emoji_id=question_emoji_id,
        )
        self._approval_handler = VerificationApprovalHandler(
            repository,
            blacklist_repository,
            bot_actions,
            permissions,
            ok_emoji_ids=ok_emoji_ids,
            question_emoji_ids=question_emoji_ids,
        )
        self._private_message_handler = VerificationPrivateMessageHandler(
            repository,
            bot_actions,
        )

    async def handle_new_member_joined(
        self,
        event: Any,
        notice: NewMemberNotice,
    ) -> WorkflowResult:
        return await self._join_handler.handle(event, notice)

    async def handle_emoji_reaction(
        self,
        event: Any,
        reaction: GroupEmojiReactionNotice,
    ) -> WorkflowResult:
        return await self._approval_handler.handle(event, reaction)

    async def handle_private_message(
        self,
        event: Any,
        notice: PrivateMessageNotice,
    ) -> WorkflowResult:
        return await self._private_message_handler.handle(event, notice)


__all__ = (
    "BotActions",
    "OK_EMOJI_ID",
    "OK_EMOJI_SYMBOL",
    "PermissionProvider",
    "QUESTION_EMOJI_ID",
    "QUESTION_EMOJI_LEGACY_ID",
    "QUESTION_EMOJI_SYMBOL",
    "VerificationWorkflow",
    "WorkflowResult",
)

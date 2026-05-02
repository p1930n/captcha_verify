from __future__ import annotations

import asyncio
import logging
from typing import Protocol

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(__name__)

from ..domain.models import TIMEOUT_ACTION_MUTE, VerificationSession
from ..persistence.repository import VerifyRepository
from ..platforms.bot_actions import BotActionResult
from .messages import utc_now_text


TIMEOUT_POLL_INTERVAL_SECONDS = 30.0
TIMEOUT_EXPIRE_BATCH_LIMIT = 50
TIMEOUT_LONG_MUTE_SECONDS = 30 * 24 * 60 * 60


class BotActions(Protocol):
    async def kick_group_member(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        reject_add_request: bool = False,
    ) -> BotActionResult:
        ...

    async def set_group_mute(
        self,
        event: object | None,
        *,
        group_id: str,
        user_id: str,
        duration_seconds: int,
    ) -> BotActionResult:
        ...


class VerificationTimeoutService:
    def __init__(
        self,
        repository: VerifyRepository,
        bot_actions: BotActions,
        *,
        poll_interval_seconds: float = TIMEOUT_POLL_INTERVAL_SECONDS,
        batch_limit: int = TIMEOUT_EXPIRE_BATCH_LIMIT,
    ) -> None:
        self._repository = repository
        self._bot_actions = bot_actions
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_limit = batch_limit
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if not self._task:
            return
        if not self._task.done():
            self._task.cancel()
            result = await asyncio.gather(self._task, return_exceptions=True)
            if result and isinstance(result[0], BaseException) and not isinstance(
                result[0],
                asyncio.CancelledError,
            ):
                logger.error(
                    "[CaptchaVerify] timeout task shutdown failed: %s",
                    result[0],
                    exc_info=result[0],
                )
        self._task = None

    async def process_expired_once(self) -> int:
        sessions = await self._repository.expire_due_verification_sessions(
            expired_at=utc_now_text(),
            limit=self._batch_limit,
        )
        for session in sessions:
            config = await self._repository.get_group_config(
                platform=session.platform,
                group_id=session.group_id,
            )
            if config.timeout_action == TIMEOUT_ACTION_MUTE:
                await self._mute_expired_member(session)
            else:
                await self._kick_expired_member(session)
        return len(sessions)

    async def _run(self) -> None:
        try:
            while True:
                try:
                    await self.process_expired_once()
                except Exception as exc:
                    logger.error(
                        "[CaptchaVerify] timeout scan failed: %s",
                        exc,
                        exc_info=True,
                    )
                await asyncio.sleep(self._poll_interval_seconds)
        except asyncio.CancelledError:
            raise

    async def _kick_expired_member(self, session: VerificationSession) -> None:
        result = await self._bot_actions.kick_group_member(
            platform=session.platform,
            group_id=session.group_id,
            user_id=session.user_id,
            reject_add_request=False,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] kick expired member failed group=%s user=%s reason=%s",
                session.group_id,
                session.user_id,
                result.reason,
            )

    async def _mute_expired_member(self, session: VerificationSession) -> None:
        result = await self._bot_actions.set_group_mute(
            None,
            group_id=session.group_id,
            user_id=session.user_id,
            duration_seconds=TIMEOUT_LONG_MUTE_SECONDS,
        )
        if not result.ok:
            logger.error(
                "[CaptchaVerify] mute expired member failed group=%s user=%s reason=%s",
                session.group_id,
                session.user_id,
                result.reason,
            )

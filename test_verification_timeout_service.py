from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_verify.persistence.repository import VerifyRepository  # noqa: E402
from captcha_verify.platforms.bot_actions import BotActionResult  # noqa: E402
from captcha_verify.workflow.messages import utc_now_text  # noqa: E402
from captcha_verify.workflow.verification_timeout import (  # noqa: E402
    TIMEOUT_LONG_MUTE_SECONDS,
    VerificationTimeoutService,
)


PAST_EXPIRES_AT = "2000-01-01T00:00:00+00:00"
FUTURE_MUTED_UNTIL = "2099-01-01T00:00:00+00:00"


class VerificationTimeoutServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_pending_session_is_kicked_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            await repository.create_pending_verification_session(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
                muted_until=FUTURE_MUTED_UNTIL,
                verify_window_seconds=1,
                expires_at=PAST_EXPIRES_AT,
            )
            bot_actions = FakeBotActions()
            service = VerificationTimeoutService(repository, bot_actions)

            first_count = await service.process_expired_once()
            second_count = await service.process_expired_once()

            self.assertEqual(first_count, 1)
            self.assertEqual(second_count, 0)
            self.assertEqual(
                bot_actions.kicks,
                [("aiocqhttp", "10001", "30001", False)],
            )

    async def test_approved_expired_session_is_not_kicked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            session = await repository.create_pending_verification_session(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
                muted_until=FUTURE_MUTED_UNTIL,
                verify_window_seconds=1,
                expires_at=PAST_EXPIRES_AT,
            )
            await repository.approve_verification_session(
                session_id=session.id,
                approver_id="30001",
                approval_source="group_prompt",
                approval_group_id="10001",
                approval_message_id="1001",
                approved_at=utc_now_text(),
            )
            bot_actions = FakeBotActions()
            service = VerificationTimeoutService(repository, bot_actions)

            expired_count = await service.process_expired_once()

            self.assertEqual(expired_count, 0)
            self.assertEqual(bot_actions.kicks, [])

    async def test_expired_pending_session_can_be_long_muted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            await repository.set_group_timeout_action(
                platform="aiocqhttp",
                group_id="10001",
                timeout_action="mute",
                updated_by="90001",
            )
            await repository.create_pending_verification_session(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
                muted_until=FUTURE_MUTED_UNTIL,
                verify_window_seconds=1,
                expires_at=PAST_EXPIRES_AT,
            )
            bot_actions = FakeBotActions()
            service = VerificationTimeoutService(repository, bot_actions)

            expired_count = await service.process_expired_once()

            self.assertEqual(expired_count, 1)
            self.assertEqual(bot_actions.kicks, [])
            self.assertEqual(
                bot_actions.mutes,
                [("10001", "30001", TIMEOUT_LONG_MUTE_SECONDS)],
            )

    async def test_expired_pending_session_deletes_prompt_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            await repository.set_group_revoke_prompt_enabled(
                platform="aiocqhttp",
                group_id="10001",
                enabled=True,
                updated_by="90001",
            )
            session = await repository.create_pending_verification_session(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
                muted_until=FUTURE_MUTED_UNTIL,
                verify_window_seconds=1,
                expires_at=PAST_EXPIRES_AT,
            )
            await repository.set_verification_prompt_message(
                session_id=session.id,
                prompt_message_id="1001",
            )
            bot_actions = FakeBotActions()
            service = VerificationTimeoutService(repository, bot_actions)

            expired_count = await service.process_expired_once()

            self.assertEqual(expired_count, 1)
            self.assertEqual(bot_actions.deleted_messages, [("aiocqhttp", "1001")])


class FakeBotActions:
    def __init__(self) -> None:
        self.kicks: list[tuple[str, str, str, bool]] = []
        self.mutes: list[tuple[str, str, int]] = []
        self.deleted_messages: list[tuple[str, str]] = []

    async def kick_group_member(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        reject_add_request: bool = False,
    ) -> BotActionResult:
        self.kicks.append((platform, group_id, user_id, reject_add_request))
        return BotActionResult(ok=True)

    async def set_group_mute(
        self,
        event: object | None,
        *,
        group_id: str,
        user_id: str,
        duration_seconds: int,
    ) -> BotActionResult:
        _ = event
        self.mutes.append((group_id, user_id, duration_seconds))
        return BotActionResult(ok=True)

    async def delete_message(
        self,
        *,
        platform: str,
        message_id: str,
    ) -> BotActionResult:
        self.deleted_messages.append((platform, message_id))
        return BotActionResult(ok=True)


if __name__ == "__main__":
    unittest.main()

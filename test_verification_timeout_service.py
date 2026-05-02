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
                timeout_seconds=1,
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
                timeout_seconds=1,
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


class FakeBotActions:
    def __init__(self) -> None:
        self.kicks: list[tuple[str, str, str, bool]] = []

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


if __name__ == "__main__":
    unittest.main()

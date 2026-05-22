from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_verify.domain.notice_adapter import parse_new_member_notice  # noqa: E402
from captcha_verify.persistence.repository import VerifyRepository  # noqa: E402
from captcha_verify.platforms.bot_actions import BotActionResult  # noqa: E402
from captcha_verify.platforms.bot_actions import SendGroupTextResult  # noqa: E402
from captcha_verify.workflow.verification_workflow import (  # noqa: E402
    OK_EMOJI_ID,
    QUESTION_EMOJI_ID,
    VerificationWorkflow,
)


class VerifyTimeoutWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_member_prompt_uses_group_timeout_not_mute_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            await repository.set_group_enabled(
                platform="aiocqhttp",
                group_id="10001",
                enabled=True,
                updated_by="90001",
            )
            await repository.set_group_verify_window_seconds(
                platform="aiocqhttp",
                group_id="10001",
                verify_window_seconds=120,
                updated_by="90001",
            )
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(),
            )

            await workflow.handle_new_member_joined(object(), _new_member_notice())
            session = await repository.find_pending_session_by_group_prompt(
                platform="aiocqhttp",
                group_id="10001",
                message_id="1001",
            )

            self.assertIsNotNone(session)
            self.assertEqual(session.verify_window_seconds if session else 0, 120)
            self.assertEqual(
                bot_actions.sent_messages[0],
                "群管在2分钟内点击下方OK手势即可完成认证\n"
                "本人私信机器人任意一条信息即可通过\n"
                "群主或管理员点击下方问号表情将踢出并加入黑名单",
            )
            self.assertEqual(
                bot_actions.mutes,
                [("10001", "30001", 120)],
            )


class FakePermissions:
    def is_global_admin_id(self, user_id: str) -> bool:
        _ = user_id
        return False

    async def is_group_admin_or_owner(
        self,
        event: Any,
        user_id: str,
        group_id: str,
    ) -> bool:
        _ = event, user_id, group_id
        return False


class FakeBlacklistRepository:
    async def is_group_whitelisted(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
    ) -> bool:
        _ = platform, group_id, user_id
        return False

    async def is_group_blacklisted(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
    ) -> bool:
        _ = platform, group_id, user_id
        return False

    async def add_group_blacklist_entry(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        operator_id: str,
        reason: str,
    ) -> None:
        _ = platform, group_id, user_id, operator_id, reason


class FakeBotActions:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []
        self.mutes: list[tuple[str, str, int]] = []
        self.reactions: list[tuple[str, str]] = []
        self.deleted_messages: list[tuple[str, str]] = []
        self._next_message_id = 1000

    async def send_group_text(
        self,
        event: Any,
        *,
        target_group_id: str,
        message: str,
    ) -> SendGroupTextResult:
        _ = event, target_group_id
        self.sent_messages.append(message)
        self._next_message_id += 1
        return SendGroupTextResult(
            ok=True,
            target_group_id=target_group_id,
            message_id=str(self._next_message_id),
        )

    async def set_group_mute(
        self,
        event: Any,
        *,
        group_id: str,
        user_id: str,
        duration_seconds: int,
    ) -> BotActionResult:
        _ = event
        self.mutes.append((group_id, user_id, duration_seconds))
        return BotActionResult(ok=True)

    async def kick_group_member(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        reject_add_request: bool = False,
    ) -> BotActionResult:
        _ = platform, group_id, user_id, reject_add_request
        return BotActionResult(ok=True)

    async def add_message_reaction(
        self,
        event: Any,
        *,
        message_id: str,
        emoji_id: str,
    ) -> BotActionResult:
        _ = event
        self.reactions.append((message_id, emoji_id))
        return BotActionResult(ok=emoji_id in {OK_EMOJI_ID, QUESTION_EMOJI_ID})

    async def delete_message(
        self,
        *,
        platform: str,
        message_id: str,
    ) -> BotActionResult:
        self.deleted_messages.append((platform, message_id))
        return BotActionResult(ok=True)


def _new_member_notice():
    notice = parse_new_member_notice(
        {
            "post_type": "notice",
            "notice_type": "group_increase",
            "group_id": 10001,
            "user_id": 30001,
            "operator_id": 90001,
            "sub_type": "approve",
            "time": 1710000000,
        },
        platform="aiocqhttp",
    )
    if notice is None:
        raise AssertionError("new member notice should parse")
    return notice


if __name__ == "__main__":
    unittest.main()

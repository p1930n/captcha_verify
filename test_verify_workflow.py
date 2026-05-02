from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_verify.domain.models import (  # noqa: E402
    DEFAULT_VERIFY_WINDOW_SECONDS,
    PrivateMessageNotice,
)
from captcha_verify.domain.notice_adapter import (  # noqa: E402
    parse_group_emoji_reaction_notice,
    parse_new_member_notice,
)
from captcha_verify.persistence.repository import (  # noqa: E402
    VerifyRepository,
)
from captcha_verify.platforms.bot_actions import BotActionResult  # noqa: E402
from captcha_verify.platforms.bot_actions import SendGroupTextResult  # noqa: E402
from captcha_verify.workflow.verification_workflow import (  # noqa: E402
    OK_EMOJI_ID,
    OK_EMOJI_SYMBOL,
    QUESTION_EMOJI_ID,
    QUESTION_EMOJI_LEGACY_ID,
    QUESTION_EMOJI_SYMBOL,
    VerificationWorkflow,
)


class VerificationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_member_starts_verification_and_pre_reacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(),
            )
            notice = _new_member_notice()

            result = await workflow.handle_new_member_joined(object(), notice)

            self.assertTrue(result.handled)
            self.assertEqual(
                bot_actions.mutes,
                [("10001", "30001", DEFAULT_VERIFY_WINDOW_SECONDS)],
            )
            self.assertEqual(bot_actions.sent_groups[:2], ["10001", "20001"])
            self.assertEqual(
                bot_actions.reactions,
                [
                    ("1001", OK_EMOJI_ID),
                    ("1001", QUESTION_EMOJI_ID),
                    ("1002", OK_EMOJI_ID),
                    ("1002", QUESTION_EMOJI_ID),
                ],
            )
            self.assertEqual(
                bot_actions.sent_messages[0],
                "群管在6小时内点击下方OK手势即可完成认证\n"
                "本人私信机器人任意一条信息即可通过\n"
                "群主或管理员点击下方问号表情将踢出并加入黑名单",
            )

    async def test_source_group_new_member_reaction_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="30001",
                message_id="1001",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertTrue(result.handled)
            self.assertIn(("10001", "30001", 0), bot_actions.mutes)
            self.assertTrue(
                any("验证方式=新人本人 👌 回应" in msg for msg in bot_actions.sent_messages)
            )

    async def test_unicode_ok_hand_reaction_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="30001",
                message_id="1001",
                emoji_id=OK_EMOJI_SYMBOL,
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertTrue(result.handled)
            self.assertIn(("10001", "30001", 0), bot_actions.mutes)

    async def test_source_group_non_admin_reaction_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="40001",
                message_id="1001",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertFalse(result.handled)
            self.assertEqual(result.reason, "source_reaction_denied")
            self.assertNotIn(("10001", "30001", 0), bot_actions.mutes)

    async def test_source_group_admin_reaction_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(group_admin_ids={"40001"}),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="40001",
                message_id="1001",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertTrue(result.handled)
            self.assertIn(("10001", "30001", 0), bot_actions.mutes)
            self.assertTrue(any("审批人=40001" in msg for msg in bot_actions.sent_messages))

    async def test_push_group_any_reaction_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="20001",
                user_id="50001",
                message_id="1002",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertTrue(result.handled)
            self.assertIn(("10001", "30001", 0), bot_actions.mutes)
            self.assertTrue(any("审批人=50001" in msg for msg in bot_actions.sent_messages))

    async def test_non_ok_reaction_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(group_admin_ids={"40001"}),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="40001",
                message_id="1001",
                emoji_id="14",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertFalse(result.handled)
            self.assertEqual(result.reason, "emoji_mismatch")
            self.assertNotIn(("10001", "30001", 0), bot_actions.mutes)

    async def test_bot_self_reaction_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(global_admin=True),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="10000",
                message_id="1001",
                self_id="10000",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertFalse(result.handled)
            self.assertEqual(result.reason, "self_reaction_ignored")
            self.assertNotIn(("10001", "30001", 0), bot_actions.mutes)

    async def test_reaction_is_ignored_until_bot_pre_reaction_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions(reaction_ok=False)
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(group_admin_ids={"40001"}),
            )
            with self.assertLogs(
                "captcha_verify.workflow.verification_workflow",
                level="ERROR",
            ):
                await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="40001",
                message_id="1001",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertFalse(result.handled)
            self.assertEqual(result.reason, "session_not_found")
            self.assertNotIn(("10001", "30001", 0), bot_actions.mutes)

    async def test_push_reaction_requires_that_push_log_pre_reaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions(failed_reaction_message_ids={"1002"})
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(group_admin_ids={"40001"}),
            )
            with self.assertLogs(
                "captcha_verify.workflow.verification_workflow",
                level="ERROR",
            ):
                await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="20001",
                user_id="50001",
                message_id="1002",
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertFalse(result.handled)
            self.assertEqual(result.reason, "session_not_found")
            self.assertNotIn(("10001", "30001", 0), bot_actions.mutes)

    async def test_private_message_from_pending_user_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                FakeBlacklistRepository(),
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())

            result = await workflow.handle_private_message(
                object(),
                PrivateMessageNotice(
                    platform="aiocqhttp",
                    user_id="30001",
                    message_id="9001",
                ),
            )

            self.assertTrue(result.handled)
            self.assertIn(("10001", "30001", 0), bot_actions.mutes)
            self.assertTrue(
                any("验证方式=新人私信机器人" in msg for msg in bot_actions.sent_messages)
            )
            self.assertTrue(
                any(
                    "CAPTCHA VERIFICATION EVENT: APPROVED" in msg
                    for msg in bot_actions.sent_messages
                )
            )

    async def test_push_group_question_reaction_rejects_and_blacklists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            blacklist_repository = FakeBlacklistRepository()
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                blacklist_repository,
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="20001",
                user_id="50001",
                message_id="1002",
                emoji_id=QUESTION_EMOJI_SYMBOL,
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertTrue(result.handled)
            self.assertEqual(
                bot_actions.kicks,
                [("aiocqhttp", "10001", "30001", False)],
            )
            self.assertEqual(
                blacklist_repository.entries,
                [("aiocqhttp", "10001", "30001", "50001", "question_reaction")],
            )
            self.assertTrue(
                any("已拒绝并加入黑名单" in msg for msg in bot_actions.sent_messages)
            )
            self.assertTrue(
                any(
                    "CAPTCHA VERIFICATION EVENT: REJECTED_AND_BLACKLISTED" in msg
                    for msg in bot_actions.sent_messages
                )
            )

    async def test_legacy_question_reaction_rejects_and_blacklists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            blacklist_repository = FakeBlacklistRepository()
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                blacklist_repository,
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="20001",
                user_id="50001",
                message_id="1002",
                emoji_id=QUESTION_EMOJI_LEGACY_ID,
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertTrue(result.handled)
            self.assertEqual(
                bot_actions.kicks,
                [("aiocqhttp", "10001", "30001", False)],
            )

    async def test_source_group_question_reaction_requires_admin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            blacklist_repository = FakeBlacklistRepository()
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                blacklist_repository,
                bot_actions,
                FakePermissions(),
            )
            await workflow.handle_new_member_joined(object(), _new_member_notice())
            reaction = _emoji_reaction(
                group_id="10001",
                user_id="40001",
                message_id="1001",
                emoji_id=QUESTION_EMOJI_SYMBOL,
            )

            result = await workflow.handle_emoji_reaction(object(), reaction)

            self.assertFalse(result.handled)
            self.assertEqual(result.reason, "source_rejection_denied")
            self.assertEqual(bot_actions.kicks, [])
            self.assertEqual(blacklist_repository.entries, [])

    async def test_blacklisted_new_member_is_kicked_without_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            blacklist_repository = FakeBlacklistRepository()
            blacklist_repository.blacklisted.add(("aiocqhttp", "10001", "30001"))
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                blacklist_repository,
                bot_actions,
                FakePermissions(),
            )

            result = await workflow.handle_new_member_joined(
                object(),
                _new_member_notice(),
            )

            self.assertTrue(result.handled)
            self.assertEqual(result.reason, "blacklisted_member_kicked")
            self.assertEqual(
                bot_actions.kicks,
                [("aiocqhttp", "10001", "30001", False)],
            )
            self.assertEqual(bot_actions.sent_messages, [])

    async def test_blacklisted_new_member_is_not_kicked_when_switch_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            await repository.set_group_blacklist_kick_enabled(
                platform="aiocqhttp",
                group_id="10001",
                enabled=False,
                updated_by="90001",
            )
            blacklist_repository = FakeBlacklistRepository()
            blacklist_repository.blacklisted.add(("aiocqhttp", "10001", "30001"))
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                blacklist_repository,
                bot_actions,
                FakePermissions(),
            )

            result = await workflow.handle_new_member_joined(
                object(),
                _new_member_notice(),
            )

            self.assertTrue(result.handled)
            self.assertEqual(bot_actions.kicks, [])
            self.assertNotEqual(bot_actions.sent_messages, [])

    async def test_zero_count_ok_reaction_is_ignored(self) -> None:
        reaction = parse_group_emoji_reaction_notice(
            {
                "post_type": "notice",
                "notice_type": "group_msg_emoji_like",
                "group_id": "10001",
                "user_id": "30001",
                "self_id": "10000",
                "message_id": "1001",
                "likes": [{"emoji_id": OK_EMOJI_ID, "count": 0}],
            },
            platform="aiocqhttp",
        )

        self.assertIsNone(reaction)


class FakePermissions:
    def __init__(
        self,
        *,
        global_admin: bool = False,
        group_admin_ids: set[str] | None = None,
    ) -> None:
        self._global_admin = global_admin
        self._group_admin_ids = group_admin_ids or set()

    def is_global_admin(self, event: Any) -> bool:
        _ = event
        return self._global_admin

    def is_global_admin_id(self, user_id: str) -> bool:
        _ = user_id
        return self._global_admin

    async def is_group_admin_or_owner(
        self,
        event: Any,
        user_id: str,
        group_id: str,
    ) -> bool:
        _ = event, user_id, group_id
        return user_id in self._group_admin_ids


class FakeBlacklistRepository:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str, str, str]] = []
        self.blacklisted: set[tuple[str, str, str]] = set()

    async def add_group_blacklist_entry(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        operator_id: str,
        reason: str,
    ) -> None:
        self.entries.append((platform, group_id, user_id, operator_id, reason))
        self.blacklisted.add((platform, group_id, user_id))

    async def is_group_blacklisted(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
    ) -> bool:
        return (platform, group_id, user_id) in self.blacklisted


class FakeBotActions:
    def __init__(
        self,
        *,
        reaction_ok: bool = True,
        failed_reaction_message_ids: set[str] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.sent_groups: list[str] = []
        self.sent_messages: list[str] = []
        self.mutes: list[tuple[str, str, int]] = []
        self.kicks: list[tuple[str, str, str, bool]] = []
        self.reactions: list[tuple[str, str]] = []
        self.reaction_ok = reaction_ok
        self.failed_reaction_message_ids = failed_reaction_message_ids or set()
        self._next_message_id = 1000

    async def send_group_text(
        self,
        event: Any,
        *,
        target_group_id: str,
        message: str,
    ) -> SendGroupTextResult:
        _ = event
        self.calls.append((target_group_id, message))
        self.sent_groups.append(target_group_id)
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

    async def add_message_reaction(
        self,
        event: Any,
        *,
        message_id: str,
        emoji_id: str,
    ) -> BotActionResult:
        _ = event
        self.reactions.append((message_id, emoji_id))
        reaction_ok = (
            self.reaction_ok and message_id not in self.failed_reaction_message_ids
        )
        return BotActionResult(
            ok=reaction_ok,
            reason="" if reaction_ok else "reaction failed",
        )

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


async def _enabled_repository(temp_dir: str) -> VerifyRepository:
    repository = VerifyRepository(temp_dir)
    await repository.set_group_enabled(
        platform="aiocqhttp",
        group_id="10001",
        enabled=True,
        updated_by="90001",
    )
    await repository.add_push_binding(
        platform="aiocqhttp",
        group_id="10001",
        push_group_id="20001",
        created_by="90001",
    )
    return repository


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


def _emoji_reaction(
    *,
    group_id: str,
    user_id: str,
    message_id: str,
    emoji_id: str = OK_EMOJI_ID,
    self_id: str = "10000",
):
    reaction = parse_group_emoji_reaction_notice(
        {
            "post_type": "notice",
            "notice_type": "group_msg_emoji_like",
            "group_id": group_id,
            "user_id": user_id,
            "self_id": self_id,
            "message_id": message_id,
            "likes": [{"emoji_id": emoji_id, "count": 1}],
            "time": 1710000060,
        },
        platform="aiocqhttp",
    )
    if reaction is None:
        raise AssertionError("emoji reaction notice should parse")
    return reaction


if __name__ == "__main__":
    unittest.main()

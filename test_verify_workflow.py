from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_verify.commands.command_controller import (  # noqa: E402
    VerifyCommandController,
)
from captcha_verify.commands.command_service import VerifyCommandService  # noqa: E402
from captcha_verify.domain.models import PlatformEventSnapshot  # noqa: E402
from captcha_verify.domain.notice_adapter import (  # noqa: E402
    parse_group_emoji_reaction_notice,
    parse_new_member_notice,
)
from captcha_verify.persistence.repository import (  # noqa: E402
    DATABASE_FILENAME,
    VerifyRepository,
    default_data_root,
)
from captcha_verify.platforms.bot_actions import BotActionResult  # noqa: E402
from captcha_verify.platforms.bot_actions import SendGroupTextResult  # noqa: E402
from captcha_verify.workflow.messages import format_push_verification_log  # noqa: E402
from captcha_verify.workflow.verification_workflow import (  # noqa: E402
    OK_EMOJI_ID,
    OK_EMOJI_SYMBOL,
    VERIFICATION_MUTE_SECONDS,
    VerificationWorkflow,
)


class VerifyRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_persists_enabled_group_and_push_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            await repository.initialize()
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

            config = await repository.get_group_config(
                platform="aiocqhttp",
                group_id="10001",
            )
            overview = await repository.list_enabled_overview(platform="aiocqhttp")

            self.assertTrue(config.enabled)
            self.assertEqual(config.push_group_ids, ("20001",))
            self.assertEqual(len(overview), 1)
            self.assertEqual(overview[0].group_id, "10001")
            self.assertEqual(overview[0].push_group_ids, ("20001",))
            self.assertTrue((Path(temp_dir) / DATABASE_FILENAME).is_file())

    async def test_overview_only_lists_enabled_groups(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            await repository.set_group_enabled(
                platform="aiocqhttp",
                group_id="10001",
                enabled=False,
                updated_by="90001",
            )
            await repository.add_push_binding(
                platform="aiocqhttp",
                group_id="10001",
                push_group_id="20001",
                created_by="90001",
            )

            overview = await repository.list_enabled_overview(platform="aiocqhttp")

            self.assertEqual(overview, [])

    def test_default_data_root_uses_dist_namespace(self) -> None:
        current_dir = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                root = Path(default_data_root())
            finally:
                os.chdir(current_dir)

        self.assertEqual(
            root,
            Path(temp_dir) / "data" / "dist" / "astrbot_plugin_captcha_verify",
        )

    async def test_migrates_v2_verification_ready_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _create_v2_database(temp_dir)
            repository = VerifyRepository(temp_dir)
            await repository.initialize()

            source_session = await repository.find_pending_session_by_group_prompt(
                platform="aiocqhttp",
                group_id="10001",
                message_id="1001",
            )
            push_session = await repository.find_pending_session_by_push_prompt(
                platform="aiocqhttp",
                push_group_id="20001",
                message_id="1002",
            )

            self.assertIsNotNone(source_session)
            self.assertIsNotNone(push_session)


class VerifyCommandControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_bind_one_argument_binds_current_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(repository),
                FakePermissions(),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
                sender_role="admin",
            )

            message = await controller.bind(
                object(),
                snapshot,
                "20001",
                "",
            )
            config = await repository.get_group_config(
                platform="aiocqhttp",
                group_id="10001",
            )

            self.assertIn("推送群绑定已保存", message)
            self.assertEqual(config.push_group_ids, ("20001",))

    async def test_bind_explicit_group_requires_global_admin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(repository),
                FakePermissions(),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
                sender_role="admin",
            )

            message = await controller.bind(
                object(),
                snapshot,
                "10002",
                "20001",
            )

            self.assertIn("需要 AstrBot 管理员权限", message)

    async def test_overview_csv_lists_enabled_group_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            service = VerifyCommandService(repository)
            controller = VerifyCommandController(service, FakePermissions(global_admin=True))
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
            )
            await service.set_enabled(
                platform="aiocqhttp",
                group_id="10001",
                enabled=True,
                updated_by="90001",
            )
            await service.bind_push_group(
                platform="aiocqhttp",
                group_id="10001",
                push_group_id="20001",
                created_by="90001",
            )

            csv_text = await controller.overview(object(), snapshot, "csv")

            self.assertEqual(
                csv_text,
                "platform,group_id,enabled,push_groups\n"
                "aiocqhttp,10001,true,20001",
            )


class VerificationMessageTests(unittest.TestCase):
    def test_formats_unix_notice_time_as_local_datetime(self) -> None:
        notice = parse_new_member_notice(
            {
                "post_type": "notice",
                "notice_type": "group_increase",
                "group_id": 10001,
                "user_id": 30001,
                "sub_type": "invite",
                "time": 1710000000,
            },
            platform="aiocqhttp",
        )

        self.assertIsNotNone(notice)
        self.assertIn("时间=2024-03-10 00-00", format_push_verification_log(notice))


class VerificationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_member_starts_verification_and_pre_reacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
                bot_actions,
                FakePermissions(),
            )
            notice = _new_member_notice()

            result = await workflow.handle_new_member_joined(object(), notice)

            self.assertTrue(result.handled)
            self.assertEqual(
                bot_actions.mutes,
                [("10001", "30001", VERIFICATION_MUTE_SECONDS)],
            )
            self.assertEqual(bot_actions.sent_groups[:2], ["10001", "20001"])
            self.assertEqual(
                bot_actions.reactions,
                [("1001", OK_EMOJI_ID), ("1002", OK_EMOJI_ID)],
            )
            self.assertEqual(
                bot_actions.sent_messages[0],
                "本人或群管在6小时内点击下方OK手势即可完成认证\n"
                "如遇QQ兼容问题，私信机器人一条信息即可触发验证码验证流程",
            )

    async def test_source_group_new_member_reaction_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
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
            self.assertIn("验证方式=新人本人 👌 回应", bot_actions.sent_messages[-1])

    async def test_unicode_ok_hand_reaction_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
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
            self.assertIn("审批人=40001", bot_actions.sent_messages[-1])

    async def test_push_group_any_reaction_approves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
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
            self.assertIn("审批人=50001", bot_actions.sent_messages[-1])

    async def test_non_ok_reaction_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = await _enabled_repository(temp_dir)
            bot_actions = FakeBotActions()
            workflow = VerificationWorkflow(
                repository,
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


def _create_v2_database(temp_dir: str) -> None:
    database_path = Path(temp_dir) / DATABASE_FILENAME
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            CREATE TABLE verification_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'pending',
                            'approved',
                            'superseded',
                            'expired'
                        )
                    ),
                prompt_message_id TEXT NOT NULL DEFAULT '',
                muted_until TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT NOT NULL DEFAULT '',
                approver_id TEXT NOT NULL DEFAULT '',
                approval_source TEXT NOT NULL DEFAULT '',
                approval_group_id TEXT NOT NULL DEFAULT '',
                approval_message_id TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE verification_push_messages (
                session_id INTEGER NOT NULL,
                push_group_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (session_id, push_group_id, message_id),
                FOREIGN KEY (session_id)
                    REFERENCES verification_sessions(id)
                    ON DELETE CASCADE
            );

            INSERT INTO verification_sessions (
                id,
                platform,
                group_id,
                user_id,
                status,
                prompt_message_id,
                muted_until,
                created_at,
                updated_at
            )
            VALUES (
                1,
                'aiocqhttp',
                '10001',
                '30001',
                'pending',
                '1001',
                '2024-03-10 00-00',
                '2024-03-10T00:00:00+00:00',
                '2024-03-10T00:00:00+00:00'
            );

            INSERT INTO verification_push_messages (
                session_id,
                push_group_id,
                message_id,
                created_at
            )
            VALUES (
                1,
                '20001',
                '1002',
                '2024-03-10T00:00:00+00:00'
            );

            PRAGMA user_version = 2;
            """
        )
    finally:
        connection.close()


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

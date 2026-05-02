from __future__ import annotations

import os
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
from captcha_verify.domain.notice_adapter import parse_new_member_notice  # noqa: E402
from captcha_verify.persistence.repository import (  # noqa: E402
    DATABASE_FILENAME,
    VerifyRepository,
    default_data_root,
)
from captcha_verify.platforms.bot_actions import SendGroupTextResult  # noqa: E402
from captcha_verify.services.new_member_push_service import (  # noqa: E402
    NewMemberPushService,
    format_new_member_push_message,
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


class NewMemberPushServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_pushes_new_member_notice_to_bound_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
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
            bot_actions = FakeBotActions()
            service = NewMemberPushService(repository, bot_actions)
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

            self.assertIsNotNone(notice)
            result = await service.handle_new_member_notice(object(), notice)

            self.assertEqual(result.delivered_targets, ("20001",))
            self.assertEqual(bot_actions.calls[0][0], "20001")
            self.assertIn("来源群=10001", bot_actions.calls[0][1])
            self.assertIn("新人=30001", bot_actions.calls[0][1])
            self.assertIn("时间=2024-03-10 00-00", bot_actions.calls[0][1])

    async def test_formats_unix_notice_time_as_local_datetime(self) -> None:
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
        self.assertIn("时间=2024-03-10 00-00", format_new_member_push_message(notice))


class FakePermissions:
    def __init__(self, *, global_admin: bool = False) -> None:
        self._global_admin = global_admin

    def is_global_admin(self, event: Any) -> bool:
        _ = event
        return self._global_admin

    async def is_group_admin_or_owner(
        self,
        event: Any,
        user_id: str,
        group_id: str,
    ) -> bool:
        _ = event, user_id, group_id
        return False


class FakeBotActions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def send_group_text(
        self,
        event: Any,
        *,
        target_group_id: str,
        message: str,
    ) -> SendGroupTextResult:
        _ = event
        self.calls.append((target_group_id, message))
        return SendGroupTextResult(ok=True, target_group_id=target_group_id)


if __name__ == "__main__":
    unittest.main()

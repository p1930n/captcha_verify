from __future__ import annotations

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
from captcha_verify.persistence.blacklist_repository import (  # noqa: E402
    BlacklistRepository,
)
from captcha_verify.persistence.repository import VerifyRepository  # noqa: E402


class VerifyTimeoutCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_timeout_for_current_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(
                    repository,
                    BlacklistRepository(Path(temp_dir) / "blacklist"),
                ),
                FakePermissions(),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
                sender_role="admin",
            )

            message = await controller.set(
                object(),
                snapshot,
                "timeout",
                "7200",
                "",
            )
            config = await repository.get_group_config(
                platform="aiocqhttp",
                group_id="10001",
            )

            self.assertIn("验证窗口时间已保存", message)
            self.assertIn("验证窗口=2小时", message)
            self.assertEqual(config.verify_window_seconds, 7200)

    async def test_set_timeout_for_other_group_requires_global_admin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(
                    repository,
                    BlacklistRepository(Path(temp_dir) / "blacklist"),
                ),
                FakePermissions(),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
                sender_role="admin",
            )

            message = await controller.set(
                object(),
                snapshot,
                "timeout",
                "10002",
                "7200",
            )

            self.assertIn("需要 AstrBot 管理员权限", message)

    async def test_status_shows_default_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(
                    repository,
                    BlacklistRepository(Path(temp_dir) / "blacklist"),
                ),
                FakePermissions(global_admin=True),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
            )

            message = await controller.status(object(), snapshot, "10001")

            self.assertIn("验证窗口=6小时", message)
            self.assertIn("超时处理=踢出", message)
            self.assertIn("黑名单自动踢出=是", message)
            self.assertIn("自动撤回验证提示=否", message)

    async def test_set_timeout_action_for_current_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(
                    repository,
                    BlacklistRepository(Path(temp_dir) / "blacklist"),
                ),
                FakePermissions(),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
                sender_role="admin",
            )

            message = await controller.set(
                object(),
                snapshot,
                "timeout-action",
                "mute",
                "",
            )
            config = await repository.get_group_config(
                platform="aiocqhttp",
                group_id="10001",
            )

            self.assertIn("超时处理方式已保存", message)
            self.assertIn("超时处理=长时禁言", message)
            self.assertEqual(config.timeout_action, "mute")

    async def test_set_blacklist_kick_for_current_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(
                    repository,
                    BlacklistRepository(Path(temp_dir) / "blacklist"),
                ),
                FakePermissions(),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
                sender_role="admin",
            )

            message = await controller.set(
                object(),
                snapshot,
                "blacklist-kick",
                "off",
                "",
            )
            config = await repository.get_group_config(
                platform="aiocqhttp",
                group_id="10001",
            )

            self.assertIn("黑名单自动踢出开关已保存", message)
            self.assertIn("黑名单自动踢出=否", message)
            self.assertFalse(config.blacklist_kick_enabled)

    async def test_set_revoke_prompt_for_current_group(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)
            controller = VerifyCommandController(
                VerifyCommandService(
                    repository,
                    BlacklistRepository(Path(temp_dir) / "blacklist"),
                ),
                FakePermissions(),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
                sender_role="admin",
            )

            message = await controller.set(
                object(),
                snapshot,
                "revoke-prompt",
                "on",
                "",
            )
            config = await repository.get_group_config(
                platform="aiocqhttp",
                group_id="10001",
            )

            self.assertIn("验证提示自动撤回开关已保存", message)
            self.assertIn("自动撤回验证提示=是", message)
            self.assertTrue(config.revoke_prompt_enabled)


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


if __name__ == "__main__":
    unittest.main()

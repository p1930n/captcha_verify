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
from captcha_verify.persistence.repository import VerifyRepository  # noqa: E402


class VerifyTimeoutCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_timeout_for_current_group(self) -> None:
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
                VerifyCommandService(repository),
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
                VerifyCommandService(repository),
                FakePermissions(global_admin=True),
            )
            snapshot = PlatformEventSnapshot(
                platform="aiocqhttp",
                group_id="10001",
                sender_id="90001",
            )

            message = await controller.status(object(), snapshot, "10001")

            self.assertIn("验证窗口=6小时", message)


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

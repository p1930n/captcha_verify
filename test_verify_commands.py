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
            controller = VerifyCommandController(
                service,
                FakePermissions(global_admin=True),
            )
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

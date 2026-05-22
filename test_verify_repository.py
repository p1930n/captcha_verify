from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_verify.persistence.repository import (  # noqa: E402
    DATABASE_FILENAME,
    VerifyRepository,
    default_data_root,
)
from captcha_verify.persistence.blacklist_repository import (  # noqa: E402
    BLACKLIST_DATABASE_FILENAME,
    BlacklistRepository,
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

    async def test_revoke_prompt_defaults_to_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = VerifyRepository(temp_dir)

            config = await repository.get_group_config(
                platform="aiocqhttp",
                group_id="10001",
            )

            self.assertFalse(config.revoke_prompt_enabled)

    async def test_blacklist_repository_removes_blacklist_and_tracks_whitelist(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = BlacklistRepository(temp_dir)
            await repository.initialize()
            await repository.add_group_blacklist_entry(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
                operator_id="90001",
                reason="test",
            )
            await repository.add_group_whitelist_entry(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
                operator_id="90001",
                reason="test",
            )

            blacklisted_before = await repository.is_group_blacklisted(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
            )
            whitelisted_before = await repository.is_group_whitelisted(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
            )
            blacklist_removed = await repository.remove_group_blacklist_entry(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
            )
            whitelist_removed = await repository.remove_group_whitelist_entry(
                platform="aiocqhttp",
                group_id="10001",
                user_id="30001",
            )

            self.assertTrue(blacklisted_before)
            self.assertTrue(whitelisted_before)
            self.assertTrue(blacklist_removed)
            self.assertTrue(whitelist_removed)
            self.assertFalse(
                await repository.is_group_blacklisted(
                    platform="aiocqhttp",
                    group_id="10001",
                    user_id="30001",
                )
            )
            self.assertFalse(
                await repository.is_group_whitelisted(
                    platform="aiocqhttp",
                    group_id="10001",
                    user_id="30001",
                )
            )
            self.assertTrue((Path(temp_dir) / BLACKLIST_DATABASE_FILENAME).is_file())


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


if __name__ == "__main__":
    unittest.main()

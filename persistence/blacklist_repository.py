from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


BLACKLIST_DIRECTORY_NAME = "group_blacklist"
BLACKLIST_DATABASE_FILENAME = "group_blacklist.db"
BLACKLIST_SCHEMA_VERSION = 1
SQLITE_BUSY_TIMEOUT_MS = 5000


class BlacklistRepository:
    def __init__(self, root_path: str | Path) -> None:
        self._root = Path(root_path)
        self._database_path = self._root / BLACKLIST_DATABASE_FILENAME
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def add_group_blacklist_entry(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        operator_id: str,
        reason: str,
    ) -> None:
        await asyncio.to_thread(
            self._add_group_blacklist_entry_sync,
            platform=platform,
            group_id=group_id,
            user_id=user_id,
            operator_id=operator_id,
            reason=reason,
        )

    async def is_group_blacklisted(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
    ) -> bool:
        return await asyncio.to_thread(
            self._is_group_blacklisted_sync,
            platform=platform,
            group_id=group_id,
            user_id=user_id,
        )

    def _initialize_sync(self) -> None:
        with self._connection() as connection:
            self._ensure_schema(connection)

    def _add_group_blacklist_entry_sync(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        operator_id: str,
        reason: str,
    ) -> None:
        now = _utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO group_blacklist (
                        platform,
                        group_id,
                        user_id,
                        operator_id,
                        reason,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (platform, group_id, user_id)
                    DO UPDATE SET
                        operator_id = excluded.operator_id,
                        reason = excluded.reason,
                        updated_at = excluded.updated_at
                    """,
                    (platform, group_id, user_id, operator_id, reason, now, now),
                )

    def _is_group_blacklisted_sync(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
    ) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM group_blacklist
                WHERE platform = ?
                    AND group_id = ?
                    AND user_id = ?
                LIMIT 1
                """,
                (platform, group_id, user_id),
            ).fetchone()
            return row is not None

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self._root.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            self._ensure_schema(connection)
            yield connection

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        _restrict_owner_access(self._database_path)
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            _ensure_schema(connection)
            self._schema_ready = True


def default_blacklist_root() -> str:
    return os.path.join(os.getcwd(), "data", BLACKLIST_DIRECTORY_NAME)


def _ensure_schema(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS group_blacklist (
                platform TEXT NOT NULL,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                operator_id TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (platform, group_id, user_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_group_blacklist_user
            ON group_blacklist (platform, user_id)
            """
        )
        connection.execute(f"PRAGMA user_version = {BLACKLIST_SCHEMA_VERSION}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _restrict_owner_access(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, 0o600)

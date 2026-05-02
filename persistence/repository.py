from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from ..domain.models import (
    DEFAULT_VERIFY_WINDOW_SECONDS,
    VerifyGroupConfig,
    VerifyOverviewRow,
)
from .repository_schema import (
    SQLITE_BUSY_TIMEOUT_MS,
    RepositorySchemaError,
    ensure_schema,
    normalize_timeout_action,
    restrict_owner_access,
    utc_now,
)
from .repository_verification import VerificationRepositoryMixin


DIST_DIRECTORY_NAME = "dist"
PLUGIN_NAME = "astrbot_plugin_captcha_verify"
DATABASE_FILENAME = "captcha_verify.db"

__all__ = (
    "DATABASE_FILENAME",
    "RepositorySchemaError",
    "VerifyRepository",
    "default_data_root",
)


class VerifyRepository(VerificationRepositoryMixin):
    def __init__(self, root_path: str | Path) -> None:
        self._root = Path(root_path)
        self._database_path = self._root / DATABASE_FILENAME
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def set_group_enabled(
        self,
        *,
        platform: str,
        group_id: str,
        enabled: bool,
        updated_by: str,
    ) -> VerifyGroupConfig:
        return await asyncio.to_thread(
            self._set_group_enabled_sync,
            platform=platform,
            group_id=group_id,
            enabled=enabled,
            updated_by=updated_by,
        )

    async def add_push_binding(
        self,
        *,
        platform: str,
        group_id: str,
        push_group_id: str,
        created_by: str,
    ) -> VerifyGroupConfig:
        return await asyncio.to_thread(
            self._add_push_binding_sync,
            platform=platform,
            group_id=group_id,
            push_group_id=push_group_id,
            created_by=created_by,
        )

    async def set_group_verify_window_seconds(
        self,
        *,
        platform: str,
        group_id: str,
        verify_window_seconds: int,
        updated_by: str,
    ) -> VerifyGroupConfig:
        return await asyncio.to_thread(
            self._set_group_verify_window_seconds_sync,
            platform=platform,
            group_id=group_id,
            verify_window_seconds=verify_window_seconds,
            updated_by=updated_by,
        )

    async def set_group_timeout_action(
        self,
        *,
        platform: str,
        group_id: str,
        timeout_action: str,
        updated_by: str,
    ) -> VerifyGroupConfig:
        return await asyncio.to_thread(
            self._set_group_timeout_action_sync,
            platform=platform,
            group_id=group_id,
            timeout_action=timeout_action,
            updated_by=updated_by,
        )

    async def set_group_blacklist_kick_enabled(
        self,
        *,
        platform: str,
        group_id: str,
        enabled: bool,
        updated_by: str,
    ) -> VerifyGroupConfig:
        return await asyncio.to_thread(
            self._set_group_blacklist_kick_enabled_sync,
            platform=platform,
            group_id=group_id,
            enabled=enabled,
            updated_by=updated_by,
        )

    async def get_group_config(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> VerifyGroupConfig:
        return await asyncio.to_thread(
            self._get_group_config_sync,
            platform=platform,
            group_id=group_id,
        )

    async def list_enabled_overview(
        self,
        *,
        platform: str,
    ) -> list[VerifyOverviewRow]:
        return await asyncio.to_thread(
            self._list_enabled_overview_sync,
            platform=platform,
        )

    async def list_enabled_push_group_ids(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> tuple[str, ...]:
        return await asyncio.to_thread(
            self._list_enabled_push_group_ids_sync,
            platform=platform,
            group_id=group_id,
        )

    def _initialize_sync(self) -> None:
        with self._connection() as connection:
            self._ensure_schema(connection)

    def _set_group_enabled_sync(
        self,
        *,
        platform: str,
        group_id: str,
        enabled: bool,
        updated_by: str,
    ) -> VerifyGroupConfig:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO verify_group_settings (
                        platform,
                        group_id,
                        enabled,
                        timeout_seconds,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (platform, group_id)
                    DO UPDATE SET
                        enabled = excluded.enabled,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        int(enabled),
                        DEFAULT_VERIFY_WINDOW_SECONDS,
                        updated_by,
                        now,
                        now,
                    ),
                )
            return self._get_group_config_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            )

    def _add_push_binding_sync(
        self,
        *,
        platform: str,
        group_id: str,
        push_group_id: str,
        created_by: str,
    ) -> VerifyGroupConfig:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO verify_group_settings (
                        platform,
                        group_id,
                        enabled,
                        timeout_seconds,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, 0, ?, ?, ?, ?)
                    ON CONFLICT (platform, group_id)
                    DO UPDATE SET
                        updated_at = verify_group_settings.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        DEFAULT_VERIFY_WINDOW_SECONDS,
                        created_by,
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO verify_push_bindings (
                        platform,
                        group_id,
                        push_group_id,
                        enabled,
                        created_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT (platform, group_id, push_group_id)
                    DO UPDATE SET
                        enabled = 1,
                        created_by = excluded.created_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        push_group_id,
                        created_by,
                        now,
                        now,
                    ),
                )
            return self._get_group_config_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            )

    def _set_group_verify_window_seconds_sync(
        self,
        *,
        platform: str,
        group_id: str,
        verify_window_seconds: int,
        updated_by: str,
    ) -> VerifyGroupConfig:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO verify_group_settings (
                        platform,
                        group_id,
                        enabled,
                        timeout_seconds,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, 0, ?, ?, ?, ?)
                    ON CONFLICT (platform, group_id)
                    DO UPDATE SET
                        timeout_seconds = excluded.timeout_seconds,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        verify_window_seconds,
                        updated_by,
                        now,
                        now,
                    ),
                )
            return self._get_group_config_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            )

    def _set_group_timeout_action_sync(
        self,
        *,
        platform: str,
        group_id: str,
        timeout_action: str,
        updated_by: str,
    ) -> VerifyGroupConfig:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO verify_group_settings (
                        platform,
                        group_id,
                        enabled,
                        timeout_seconds,
                        timeout_action,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, 0, ?, ?, ?, ?, ?)
                    ON CONFLICT (platform, group_id)
                    DO UPDATE SET
                        timeout_action = excluded.timeout_action,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        DEFAULT_VERIFY_WINDOW_SECONDS,
                        timeout_action,
                        updated_by,
                        now,
                        now,
                    ),
                )
            return self._get_group_config_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            )

    def _set_group_blacklist_kick_enabled_sync(
        self,
        *,
        platform: str,
        group_id: str,
        enabled: bool,
        updated_by: str,
    ) -> VerifyGroupConfig:
        now = utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO verify_group_settings (
                        platform,
                        group_id,
                        enabled,
                        timeout_seconds,
                        blacklist_kick_enabled,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, 0, ?, ?, ?, ?, ?)
                    ON CONFLICT (platform, group_id)
                    DO UPDATE SET
                        blacklist_kick_enabled = excluded.blacklist_kick_enabled,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        platform,
                        group_id,
                        DEFAULT_VERIFY_WINDOW_SECONDS,
                        int(enabled),
                        updated_by,
                        now,
                        now,
                    ),
                )
            return self._get_group_config_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            )

    def _get_group_config_sync(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> VerifyGroupConfig:
        with self._connection() as connection:
            return self._get_group_config_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            )

    def _list_enabled_overview_sync(
        self,
        *,
        platform: str,
    ) -> list[VerifyOverviewRow]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT platform, group_id, enabled, timeout_seconds, timeout_action,
                    blacklist_kick_enabled
                FROM verify_group_settings
                WHERE platform = ? AND enabled = 1
                ORDER BY group_id
                """,
                (platform,),
            ).fetchall()
            return [
                VerifyOverviewRow(
                    platform=str(row[0]),
                    group_id=str(row[1]),
                    enabled=bool(row[2]),
                    verify_window_seconds=int(row[3] or DEFAULT_VERIFY_WINDOW_SECONDS),
                    timeout_action=normalize_timeout_action(row[4]),
                    blacklist_kick_enabled=bool(row[5]),
                    push_group_ids=self._list_enabled_push_group_ids_with_connection(
                        connection,
                        platform=str(row[0]),
                        group_id=str(row[1]),
                    ),
                )
                for row in rows
            ]

    def _list_enabled_push_group_ids_sync(
        self,
        *,
        platform: str,
        group_id: str,
    ) -> tuple[str, ...]:
        with self._connection() as connection:
            return self._list_enabled_push_group_ids_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            )

    def _get_group_config_with_connection(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str,
        group_id: str,
    ) -> VerifyGroupConfig:
        row = connection.execute(
            """
            SELECT enabled, timeout_seconds, timeout_action, blacklist_kick_enabled
            FROM verify_group_settings
            WHERE platform = ? AND group_id = ?
            """,
            (platform, group_id),
        ).fetchone()
        enabled = bool(row[0]) if row else False
        timeout_seconds = (
            int(row[1] or DEFAULT_VERIFY_WINDOW_SECONDS)
            if row
            else DEFAULT_VERIFY_WINDOW_SECONDS
        )
        timeout_action = normalize_timeout_action(row[2] if row else None)
        blacklist_kick_enabled = bool(row[3]) if row else True
        return VerifyGroupConfig(
            platform=platform,
            group_id=group_id,
            enabled=enabled,
            verify_window_seconds=timeout_seconds,
            timeout_action=timeout_action,
            blacklist_kick_enabled=blacklist_kick_enabled,
            push_group_ids=self._list_enabled_push_group_ids_with_connection(
                connection,
                platform=platform,
                group_id=group_id,
            ),
        )

    def _list_enabled_push_group_ids_with_connection(
        self,
        connection: sqlite3.Connection,
        *,
        platform: str,
        group_id: str,
    ) -> tuple[str, ...]:
        rows = connection.execute(
            """
            SELECT push_group_id
            FROM verify_push_bindings
            WHERE platform = ?
                AND group_id = ?
                AND enabled = 1
            ORDER BY push_group_id
            """,
            (platform, group_id),
        ).fetchall()
        return tuple(str(row[0]) for row in rows)

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
        restrict_owner_access(self._database_path)
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            ensure_schema(connection)
            self._schema_ready = True


def default_data_root() -> str:
    return os.path.join(os.getcwd(), "data", DIST_DIRECTORY_NAME, PLUGIN_NAME)

from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import (
    DEFAULT_VERIFY_WINDOW_SECONDS,
    VERIFICATION_STATUS_PENDING,
    VerifyGroupConfig,
    VerifyOverviewRow,
)
from .repository_verification import VerificationRepositoryMixin


DIST_DIRECTORY_NAME = "dist"
PLUGIN_NAME = "astrbot_plugin_captcha_verify"
DATABASE_FILENAME = "captcha_verify.db"
CURRENT_SCHEMA_VERSION = 4
SQLITE_BUSY_TIMEOUT_MS = 5000


class RepositorySchemaError(RuntimeError):
    """Raised when the persisted SQLite schema cannot be used safely."""


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
                SELECT platform, group_id, enabled, timeout_seconds
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
            SELECT enabled, timeout_seconds
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
        return VerifyGroupConfig(
            platform=platform,
            group_id=group_id,
            enabled=enabled,
            verify_window_seconds=timeout_seconds,
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
        _restrict_owner_access(self._database_path)
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


def ensure_schema(connection: sqlite3.Connection) -> None:
    current_version = _schema_version(connection)
    if current_version > CURRENT_SCHEMA_VERSION:
        raise RepositorySchemaError(
            "captcha verify database schema is newer than this plugin version: "
            f"{current_version} > {CURRENT_SCHEMA_VERSION}"
        )

    with connection:
        _create_schema_objects(connection)
        _migrate_schema(connection, current_version)
        _create_post_migration_indexes(connection)
        _validate_required_schema(connection)
        connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_after_seconds(seconds: int) -> str:
    return datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + seconds,
        tz=timezone.utc,
    ).isoformat()


def _create_schema_objects(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS verify_group_settings (
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            timeout_seconds INTEGER NOT NULL DEFAULT {DEFAULT_VERIFY_WINDOW_SECONDS},
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, group_id)
        );

        CREATE TABLE IF NOT EXISTS verify_push_bindings (
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            push_group_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (platform, group_id, push_group_id),
            FOREIGN KEY (platform, group_id)
                REFERENCES verify_group_settings(platform, group_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_verify_push_bindings_target
        ON verify_push_bindings (platform, push_group_id);

        CREATE TABLE IF NOT EXISTS verification_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            group_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('pending', 'approved', 'superseded', 'expired')),
            timeout_seconds INTEGER NOT NULL DEFAULT {DEFAULT_VERIFY_WINDOW_SECONDS},
            prompt_approval_ready INTEGER NOT NULL DEFAULT 0,
            prompt_message_id TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT '',
            muted_until TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            approved_at TEXT NOT NULL DEFAULT '',
            approver_id TEXT NOT NULL DEFAULT '',
            approval_source TEXT NOT NULL DEFAULT '',
            approval_group_id TEXT NOT NULL DEFAULT '',
            approval_message_id TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_verification_sessions_prompt
        ON verification_sessions (platform, group_id, prompt_message_id, status);

        CREATE INDEX IF NOT EXISTS idx_verification_sessions_user_status
        ON verification_sessions (platform, group_id, user_id, status, created_at);

        CREATE TABLE IF NOT EXISTS verification_push_messages (
            session_id INTEGER NOT NULL,
            push_group_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            approval_ready INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (session_id, push_group_id, message_id),
            FOREIGN KEY (session_id)
                REFERENCES verification_sessions(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_verification_push_messages_lookup
        ON verification_push_messages (push_group_id, message_id);
        """
    )


def _create_post_migration_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_verification_sessions_due
        ON verification_sessions (status, expires_at)
        """
    )


def _migrate_schema(connection: sqlite3.Connection, current_version: int) -> None:
    if current_version < 3:
        _add_column_if_missing(
            connection,
            table_name="verification_sessions",
            column_name="prompt_approval_ready",
            column_definition="prompt_approval_ready INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            connection,
            table_name="verification_push_messages",
            column_name="approval_ready",
            column_definition="approval_ready INTEGER NOT NULL DEFAULT 0",
        )
        connection.execute(
            """
            UPDATE verification_sessions
            SET prompt_approval_ready = 1
            WHERE status = ?
                AND prompt_message_id <> ''
            """,
            (VERIFICATION_STATUS_PENDING,),
        )
    if current_version < 4:
        _add_column_if_missing(
            connection,
            table_name="verify_group_settings",
            column_name="timeout_seconds",
            column_definition=(
                "timeout_seconds INTEGER NOT NULL "
                f"DEFAULT {DEFAULT_VERIFY_WINDOW_SECONDS}"
            ),
        )
        _add_column_if_missing(
            connection,
            table_name="verification_sessions",
            column_name="timeout_seconds",
            column_definition=(
                "timeout_seconds INTEGER NOT NULL "
                f"DEFAULT {DEFAULT_VERIFY_WINDOW_SECONDS}"
            ),
        )
        _add_column_if_missing(
            connection,
            table_name="verification_sessions",
            column_name="expires_at",
            column_definition="expires_at TEXT NOT NULL DEFAULT ''",
        )
        expires_at = _utc_after_seconds(DEFAULT_VERIFY_WINDOW_SECONDS)
        connection.execute(
            """
            UPDATE verification_sessions
            SET expires_at = ?
            WHERE status = ?
                AND expires_at = ''
            """,
            (expires_at, VERIFICATION_STATUS_PENDING),
        )
        connection.execute(
            """
            UPDATE verification_push_messages
            SET approval_ready = 1
            WHERE EXISTS (
                SELECT 1
                FROM verification_sessions AS session
                WHERE session.id = verification_push_messages.session_id
                    AND session.status = ?
            )
            """,
            (VERIFICATION_STATUS_PENDING,),
        )


def _add_column_if_missing(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if column_name in _table_columns(connection, table_name):
        return
    escaped_table_name = table_name.replace('"', '""')
    connection.execute(
        f'ALTER TABLE "{escaped_table_name}" ADD COLUMN {column_definition}'
    )


def _validate_required_schema(connection: sqlite3.Connection) -> None:
    required = {
        "verify_group_settings": (
            "platform",
            "group_id",
            "enabled",
            "timeout_seconds",
            "updated_by",
            "created_at",
            "updated_at",
        ),
        "verify_push_bindings": (
            "platform",
            "group_id",
            "push_group_id",
            "enabled",
            "created_by",
            "created_at",
            "updated_at",
        ),
        "verification_sessions": (
            "id",
            "platform",
            "group_id",
            "user_id",
            "status",
            "timeout_seconds",
            "prompt_approval_ready",
            "prompt_message_id",
            "expires_at",
            "muted_until",
            "created_at",
            "updated_at",
            "approved_at",
            "approver_id",
            "approval_source",
            "approval_group_id",
            "approval_message_id",
        ),
        "verification_push_messages": (
            "session_id",
            "push_group_id",
            "message_id",
            "approval_ready",
            "created_at",
        ),
    }
    table_names = _user_table_names(connection)
    missing_tables = sorted(set(required) - table_names)
    if missing_tables:
        raise RepositorySchemaError(
            "captcha verify database schema is missing required table(s): "
            f"{', '.join(missing_tables)}"
        )

    missing_columns: list[str] = []
    for table_name, required_columns in required.items():
        actual_columns = _table_columns(connection, table_name)
        for column_name in required_columns:
            if column_name not in actual_columns:
                missing_columns.append(f"{table_name}.{column_name}")
    if missing_columns:
        raise RepositorySchemaError(
            "captcha verify database schema is missing required column(s): "
            f"{', '.join(sorted(missing_columns))}"
        )


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if not row:
        return 0
    return int(row[0])


def _user_table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_schema
        WHERE type = 'table'
            AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    escaped_table_name = table_name.replace('"', '""')
    rows = connection.execute(f'PRAGMA table_info("{escaped_table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def _restrict_owner_access(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, 0o600)

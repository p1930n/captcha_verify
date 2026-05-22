from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import (
    DEFAULT_BLACKLIST_KICK_ENABLED,
    DEFAULT_REVOKE_PROMPT_ENABLED,
    DEFAULT_TIMEOUT_ACTION,
    DEFAULT_VERIFY_WINDOW_SECONDS,
    TIMEOUT_ACTION_KICK,
    TIMEOUT_ACTION_MUTE,
    VERIFICATION_STATUS_PENDING,
)

CURRENT_SCHEMA_VERSION = 7
SQLITE_BUSY_TIMEOUT_MS = 5000


class RepositorySchemaError(RuntimeError):
    """Raised when the persisted SQLite schema cannot be used safely."""


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


def restrict_owner_access(path: Path) -> None:
    if os.name == "posix":
        os.chmod(path, 0o600)


def normalize_timeout_action(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {TIMEOUT_ACTION_KICK, TIMEOUT_ACTION_MUTE}:
        return normalized
    return DEFAULT_TIMEOUT_ACTION


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
            timeout_action TEXT NOT NULL DEFAULT '{DEFAULT_TIMEOUT_ACTION}'
                CHECK (timeout_action IN ('{TIMEOUT_ACTION_KICK}', '{TIMEOUT_ACTION_MUTE}')),
            blacklist_kick_enabled INTEGER NOT NULL DEFAULT {int(DEFAULT_BLACKLIST_KICK_ENABLED)},
            revoke_prompt_enabled INTEGER NOT NULL DEFAULT {int(DEFAULT_REVOKE_PROMPT_ENABLED)},
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
            prompt_rejection_ready INTEGER NOT NULL DEFAULT 0,
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
            rejection_ready INTEGER NOT NULL DEFAULT 0,
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
    if current_version < 5:
        _add_column_if_missing(
            connection,
            table_name="verify_group_settings",
            column_name="timeout_action",
            column_definition=(
                "timeout_action TEXT NOT NULL "
                f"DEFAULT '{DEFAULT_TIMEOUT_ACTION}' "
                f"CHECK (timeout_action IN ('{TIMEOUT_ACTION_KICK}', '{TIMEOUT_ACTION_MUTE}'))"
            ),
        )
        _add_column_if_missing(
            connection,
            table_name="verification_sessions",
            column_name="prompt_rejection_ready",
            column_definition="prompt_rejection_ready INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            connection,
            table_name="verification_push_messages",
            column_name="rejection_ready",
            column_definition="rejection_ready INTEGER NOT NULL DEFAULT 0",
        )
    if current_version < 6:
        _add_column_if_missing(
            connection,
            table_name="verify_group_settings",
            column_name="blacklist_kick_enabled",
            column_definition=(
                "blacklist_kick_enabled INTEGER NOT NULL "
                f"DEFAULT {int(DEFAULT_BLACKLIST_KICK_ENABLED)}"
            ),
        )
    if current_version < 7:
        _add_column_if_missing(
            connection,
            table_name="verify_group_settings",
            column_name="revoke_prompt_enabled",
            column_definition=(
                "revoke_prompt_enabled INTEGER NOT NULL "
                f"DEFAULT {int(DEFAULT_REVOKE_PROMPT_ENABLED)}"
            ),
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
            "timeout_action",
            "blacklist_kick_enabled",
            "revoke_prompt_enabled",
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
            "prompt_rejection_ready",
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
            "rejection_ready",
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

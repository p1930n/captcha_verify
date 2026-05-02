from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

from ..domain.models import (
    VERIFICATION_STATUS_APPROVED,
    VERIFICATION_STATUS_PENDING,
    VERIFICATION_STATUS_SUPERSEDED,
    VerificationPushMessage,
    VerificationSession,
)


class VerificationRepositoryMixin:
    async def create_pending_verification_session(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        muted_until: str,
    ) -> VerificationSession:
        return await asyncio.to_thread(
            self._create_pending_verification_session_sync,
            platform=platform,
            group_id=group_id,
            user_id=user_id,
            muted_until=muted_until,
        )

    async def set_verification_prompt_message(
        self,
        *,
        session_id: int,
        prompt_message_id: str,
    ) -> VerificationSession | None:
        return await asyncio.to_thread(
            self._set_verification_prompt_message_sync,
            session_id=session_id,
            prompt_message_id=prompt_message_id,
        )

    async def add_verification_push_message(
        self,
        *,
        session_id: int,
        push_group_id: str,
        message_id: str,
    ) -> VerificationPushMessage:
        return await asyncio.to_thread(
            self._add_verification_push_message_sync,
            session_id=session_id,
            push_group_id=push_group_id,
            message_id=message_id,
        )

    async def find_pending_session_by_group_prompt(
        self,
        *,
        platform: str,
        group_id: str,
        message_id: str,
    ) -> VerificationSession | None:
        return await asyncio.to_thread(
            self._find_pending_session_by_group_prompt_sync,
            platform=platform,
            group_id=group_id,
            message_id=message_id,
        )

    async def find_pending_session_by_push_prompt(
        self,
        *,
        platform: str,
        push_group_id: str,
        message_id: str,
    ) -> VerificationSession | None:
        return await asyncio.to_thread(
            self._find_pending_session_by_push_prompt_sync,
            platform=platform,
            push_group_id=push_group_id,
            message_id=message_id,
        )

    async def approve_verification_session(
        self,
        *,
        session_id: int,
        approver_id: str,
        approval_source: str,
        approval_group_id: str,
        approval_message_id: str,
        approved_at: str,
    ) -> VerificationSession | None:
        return await asyncio.to_thread(
            self._approve_verification_session_sync,
            session_id=session_id,
            approver_id=approver_id,
            approval_source=approval_source,
            approval_group_id=approval_group_id,
            approval_message_id=approval_message_id,
            approved_at=approved_at,
        )

    async def list_verification_push_messages(
        self,
        *,
        session_id: int,
    ) -> list[VerificationPushMessage]:
        return await asyncio.to_thread(
            self._list_verification_push_messages_sync,
            session_id=session_id,
        )

    def _create_pending_verification_session_sync(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        muted_until: str,
    ) -> VerificationSession:
        now = _utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE verification_sessions
                    SET status = ?,
                        updated_at = ?
                    WHERE platform = ?
                        AND group_id = ?
                        AND user_id = ?
                        AND status = ?
                    """,
                    (
                        VERIFICATION_STATUS_SUPERSEDED,
                        now,
                        platform,
                        group_id,
                        user_id,
                        VERIFICATION_STATUS_PENDING,
                    ),
                )
                cursor = connection.execute(
                    """
                    INSERT INTO verification_sessions (
                        platform,
                        group_id,
                        user_id,
                        status,
                        muted_until,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        platform,
                        group_id,
                        user_id,
                        VERIFICATION_STATUS_PENDING,
                        muted_until,
                        now,
                        now,
                    ),
                )
                session_id = int(cursor.lastrowid)
            session = self._get_verification_session_with_connection(
                connection,
                session_id=session_id,
            )
            if session is None:
                raise RuntimeError("created verification session is missing")
            return session

    def _set_verification_prompt_message_sync(
        self,
        *,
        session_id: int,
        prompt_message_id: str,
    ) -> VerificationSession | None:
        now = _utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE verification_sessions
                    SET prompt_message_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (prompt_message_id, now, session_id),
                )
            return self._get_verification_session_with_connection(
                connection,
                session_id=session_id,
            )

    def _add_verification_push_message_sync(
        self,
        *,
        session_id: int,
        push_group_id: str,
        message_id: str,
    ) -> VerificationPushMessage:
        now = _utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO verification_push_messages (
                        session_id,
                        push_group_id,
                        message_id,
                        created_at
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (session_id, push_group_id, message_id)
                    DO UPDATE SET created_at = excluded.created_at
                    """,
                    (session_id, push_group_id, message_id, now),
                )
        return VerificationPushMessage(
            session_id=session_id,
            push_group_id=push_group_id,
            message_id=message_id,
            created_at=now,
        )

    def _find_pending_session_by_group_prompt_sync(
        self,
        *,
        platform: str,
        group_id: str,
        message_id: str,
    ) -> VerificationSession | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    platform,
                    group_id,
                    user_id,
                    status,
                    prompt_message_id,
                    muted_until,
                    created_at,
                    updated_at,
                    approved_at,
                    approver_id,
                    approval_source,
                    approval_group_id,
                    approval_message_id
                FROM verification_sessions
                WHERE platform = ?
                    AND group_id = ?
                    AND prompt_message_id = ?
                    AND status = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (platform, group_id, message_id, VERIFICATION_STATUS_PENDING),
            ).fetchone()
            return _verification_session_from_row(row)

    def _find_pending_session_by_push_prompt_sync(
        self,
        *,
        platform: str,
        push_group_id: str,
        message_id: str,
    ) -> VerificationSession | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    session.id,
                    session.platform,
                    session.group_id,
                    session.user_id,
                    session.status,
                    session.prompt_message_id,
                    session.muted_until,
                    session.created_at,
                    session.updated_at,
                    session.approved_at,
                    session.approver_id,
                    session.approval_source,
                    session.approval_group_id,
                    session.approval_message_id
                FROM verification_sessions AS session
                JOIN verification_push_messages AS push
                    ON push.session_id = session.id
                WHERE session.platform = ?
                    AND push.push_group_id = ?
                    AND push.message_id = ?
                    AND session.status = ?
                ORDER BY session.id DESC
                LIMIT 1
                """,
                (
                    platform,
                    push_group_id,
                    message_id,
                    VERIFICATION_STATUS_PENDING,
                ),
            ).fetchone()
            return _verification_session_from_row(row)

    def _approve_verification_session_sync(
        self,
        *,
        session_id: int,
        approver_id: str,
        approval_source: str,
        approval_group_id: str,
        approval_message_id: str,
        approved_at: str,
    ) -> VerificationSession | None:
        now = _utc_now()
        with self._connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE verification_sessions
                    SET status = ?,
                        approved_at = ?,
                        approver_id = ?,
                        approval_source = ?,
                        approval_group_id = ?,
                        approval_message_id = ?,
                        updated_at = ?
                    WHERE id = ? AND status = ?
                    """,
                    (
                        VERIFICATION_STATUS_APPROVED,
                        approved_at,
                        approver_id,
                        approval_source,
                        approval_group_id,
                        approval_message_id,
                        now,
                        session_id,
                        VERIFICATION_STATUS_PENDING,
                    ),
                )
                if cursor.rowcount != 1:
                    return None
            return self._get_verification_session_with_connection(
                connection,
                session_id=session_id,
            )

    def _list_verification_push_messages_sync(
        self,
        *,
        session_id: int,
    ) -> list[VerificationPushMessage]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT session_id, push_group_id, message_id, created_at
                FROM verification_push_messages
                WHERE session_id = ?
                ORDER BY push_group_id, message_id
                """,
                (session_id,),
            ).fetchall()
            return [_verification_push_message_from_row(row) for row in rows]

    def _get_verification_session_with_connection(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: int,
    ) -> VerificationSession | None:
        row = connection.execute(
            """
            SELECT
                id,
                platform,
                group_id,
                user_id,
                status,
                prompt_message_id,
                muted_until,
                created_at,
                updated_at,
                approved_at,
                approver_id,
                approval_source,
                approval_group_id,
                approval_message_id
            FROM verification_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        return _verification_session_from_row(row)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verification_session_from_row(row: object) -> VerificationSession | None:
    if row is None:
        return None
    values = tuple(row)
    return VerificationSession(
        id=int(values[0]),
        platform=str(values[1]),
        group_id=str(values[2]),
        user_id=str(values[3]),
        status=str(values[4]),
        prompt_message_id=str(values[5] or ""),
        muted_until=str(values[6] or ""),
        created_at=str(values[7] or ""),
        updated_at=str(values[8] or ""),
        approved_at=str(values[9] or ""),
        approver_id=str(values[10] or ""),
        approval_source=str(values[11] or ""),
        approval_group_id=str(values[12] or ""),
        approval_message_id=str(values[13] or ""),
    )


def _verification_push_message_from_row(row: object) -> VerificationPushMessage:
    values = tuple(row)
    return VerificationPushMessage(
        session_id=int(values[0]),
        push_group_id=str(values[1]),
        message_id=str(values[2]),
        created_at=str(values[3] or ""),
    )

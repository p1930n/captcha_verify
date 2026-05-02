from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

from ..domain.models import (
    DEFAULT_VERIFY_WINDOW_SECONDS,
    VERIFICATION_STATUS_APPROVED,
    VERIFICATION_STATUS_EXPIRED,
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
        verify_window_seconds: int,
        expires_at: str,
    ) -> VerificationSession:
        return await asyncio.to_thread(
            self._create_pending_verification_session_sync,
            platform=platform,
            group_id=group_id,
            user_id=user_id,
            muted_until=muted_until,
            verify_window_seconds=verify_window_seconds,
            expires_at=expires_at,
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

    async def mark_verification_prompt_approval_ready(
        self,
        *,
        session_id: int,
        prompt_message_id: str,
    ) -> VerificationSession | None:
        return await asyncio.to_thread(
            self._mark_verification_prompt_approval_ready_sync,
            session_id=session_id,
            prompt_message_id=prompt_message_id,
        )

    async def mark_verification_push_message_approval_ready(
        self,
        *,
        session_id: int,
        push_group_id: str,
        message_id: str,
    ) -> VerificationPushMessage | None:
        return await asyncio.to_thread(
            self._mark_verification_push_message_approval_ready_sync,
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

    async def expire_due_verification_sessions(
        self,
        *,
        expired_at: str,
        limit: int,
    ) -> list[VerificationSession]:
        return await asyncio.to_thread(
            self._expire_due_verification_sessions_sync,
            expired_at=expired_at,
            limit=limit,
        )

    def _create_pending_verification_session_sync(
        self,
        *,
        platform: str,
        group_id: str,
        user_id: str,
        muted_until: str,
        verify_window_seconds: int,
        expires_at: str,
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
                        timeout_seconds,
                        prompt_approval_ready,
                        expires_at,
                        muted_until,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (
                        platform,
                        group_id,
                        user_id,
                        VERIFICATION_STATUS_PENDING,
                        verify_window_seconds,
                        expires_at,
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
                        prompt_approval_ready = 0,
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
                        approval_ready,
                        created_at
                    )
                    VALUES (?, ?, ?, 0, ?)
                    ON CONFLICT (session_id, push_group_id, message_id)
                    DO UPDATE SET
                        approval_ready = 0,
                        created_at = excluded.created_at
                    """,
                    (session_id, push_group_id, message_id, now),
                )
        return VerificationPushMessage(
            session_id=session_id,
            push_group_id=push_group_id,
            message_id=message_id,
            approval_ready=False,
            created_at=now,
        )

    def _mark_verification_prompt_approval_ready_sync(
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
                    SET prompt_approval_ready = 1,
                        updated_at = ?
                    WHERE id = ?
                        AND prompt_message_id = ?
                        AND status = ?
                    """,
                    (
                        now,
                        session_id,
                        prompt_message_id,
                        VERIFICATION_STATUS_PENDING,
                    ),
                )
            return self._get_verification_session_with_connection(
                connection,
                session_id=session_id,
            )

    def _mark_verification_push_message_approval_ready_sync(
        self,
        *,
        session_id: int,
        push_group_id: str,
        message_id: str,
    ) -> VerificationPushMessage | None:
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE verification_push_messages
                    SET approval_ready = 1
                    WHERE session_id = ?
                        AND push_group_id = ?
                        AND message_id = ?
                    """,
                    (session_id, push_group_id, message_id),
                )
            row = connection.execute(
                """
                SELECT session_id, push_group_id, message_id, approval_ready, created_at
                FROM verification_push_messages
                WHERE session_id = ?
                    AND push_group_id = ?
                    AND message_id = ?
                """,
                (session_id, push_group_id, message_id),
            ).fetchone()
            return _verification_push_message_from_row(row) if row else None

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
                    timeout_seconds,
                    prompt_approval_ready,
                    prompt_message_id,
                    expires_at,
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
                    AND prompt_approval_ready = 1
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
                    session.timeout_seconds,
                    session.prompt_approval_ready,
                    session.prompt_message_id,
                    session.expires_at,
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
                    AND push.approval_ready = 1
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
                SELECT session_id, push_group_id, message_id, approval_ready, created_at
                FROM verification_push_messages
                WHERE session_id = ?
                ORDER BY push_group_id, message_id
                """,
                (session_id,),
            ).fetchall()
            return [_verification_push_message_from_row(row) for row in rows]

    def _expire_due_verification_sessions_sync(
        self,
        *,
        expired_at: str,
        limit: int,
    ) -> list[VerificationSession]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    platform,
                    group_id,
                    user_id,
                    status,
                    timeout_seconds,
                    prompt_approval_ready,
                    prompt_message_id,
                    expires_at,
                    muted_until,
                    created_at,
                    updated_at,
                    approved_at,
                    approver_id,
                    approval_source,
                    approval_group_id,
                    approval_message_id
                FROM verification_sessions
                WHERE status = ?
                    AND expires_at <> ''
                    AND expires_at <= ?
                ORDER BY expires_at, id
                LIMIT ?
                """,
                (VERIFICATION_STATUS_PENDING, expired_at, max(1, int(limit))),
            ).fetchall()

            expired_sessions: list[VerificationSession] = []
            with connection:
                for row in rows:
                    values = tuple(row)
                    cursor = connection.execute(
                        """
                        UPDATE verification_sessions
                        SET status = ?,
                            updated_at = ?
                        WHERE id = ? AND status = ?
                        """,
                        (
                            VERIFICATION_STATUS_EXPIRED,
                            expired_at,
                            int(values[0]),
                            VERIFICATION_STATUS_PENDING,
                        ),
                    )
                    if cursor.rowcount != 1:
                        continue
                    updated_values = (
                        values[0],
                        values[1],
                        values[2],
                        values[3],
                        VERIFICATION_STATUS_EXPIRED,
                        *values[5:11],
                        expired_at,
                        *values[12:],
                    )
                    expired_session = _verification_session_from_row(updated_values)
                    if expired_session is not None:
                        expired_sessions.append(expired_session)
            return expired_sessions

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
                timeout_seconds,
                prompt_approval_ready,
                prompt_message_id,
                expires_at,
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
        verify_window_seconds=int(values[5] or DEFAULT_VERIFY_WINDOW_SECONDS),
        prompt_approval_ready=bool(values[6]),
        prompt_message_id=str(values[7] or ""),
        expires_at=str(values[8] or ""),
        muted_until=str(values[9] or ""),
        created_at=str(values[10] or ""),
        updated_at=str(values[11] or ""),
        approved_at=str(values[12] or ""),
        approver_id=str(values[13] or ""),
        approval_source=str(values[14] or ""),
        approval_group_id=str(values[15] or ""),
        approval_message_id=str(values[16] or ""),
    )


def _verification_push_message_from_row(row: object) -> VerificationPushMessage:
    values = tuple(row)
    return VerificationPushMessage(
        session_id=int(values[0]),
        push_group_id=str(values[1]),
        message_id=str(values[2]),
        approval_ready=bool(values[3]),
        created_at=str(values[4] or ""),
    )

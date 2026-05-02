from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone

from ..domain.models import (
    VERIFICATION_STATUS_APPROVED,
    VERIFICATION_STATUS_EXPIRED,
    VERIFICATION_STATUS_PENDING,
    VERIFICATION_STATUS_SUPERSEDED,
    VerificationSession,
)
from .repository_verification_prompts import VerificationPromptRepositoryMixin
from .repository_verification_rows import (
    VERIFICATION_SESSION_SELECT,
    verification_session_from_row,
)


class VerificationRepositoryMixin(VerificationPromptRepositoryMixin):
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
            platform=platform, group_id=group_id, user_id=user_id,
            muted_until=muted_until, verify_window_seconds=verify_window_seconds,
            expires_at=expires_at,
        )

    async def list_pending_sessions_by_user(
        self, *, platform: str, user_id: str,
    ) -> list[VerificationSession]:
        return await asyncio.to_thread(
            self._list_pending_sessions_by_user_sync,
            platform=platform, user_id=user_id,
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
            session_id=session_id, approver_id=approver_id,
            approval_source=approval_source, approval_group_id=approval_group_id,
            approval_message_id=approval_message_id, approved_at=approved_at,
        )

    async def expire_verification_session(
        self, *, session_id: int, expired_at: str,
    ) -> VerificationSession | None:
        return await asyncio.to_thread(
            self._expire_verification_session_sync,
            session_id=session_id, expired_at=expired_at,
        )

    async def expire_due_verification_sessions(
        self, *, expired_at: str, limit: int,
    ) -> list[VerificationSession]:
        return await asyncio.to_thread(
            self._expire_due_verification_sessions_sync,
            expired_at=expired_at, limit=limit,
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

    def _list_pending_sessions_by_user_sync(
        self,
        *,
        platform: str,
        user_id: str,
    ) -> list[VerificationSession]:
        with self._connection() as connection:
            rows = connection.execute(
                f"{VERIFICATION_SESSION_SELECT}"
                " WHERE platform = ?"
                " AND user_id = ?"
                " AND status = ?"
                " ORDER BY id",
                (platform, user_id, VERIFICATION_STATUS_PENDING),
            ).fetchall()
            return [
                session
                for row in rows
                if (session := verification_session_from_row(row)) is not None
            ]

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

    def _expire_verification_session_sync(
        self,
        *,
        session_id: int,
        expired_at: str,
    ) -> VerificationSession | None:
        with self._connection() as connection:
            session = self._get_verification_session_with_connection(
                connection,
                session_id=session_id,
            )
            if session is None:
                return None
            with connection:
                cursor = connection.execute(
                    "UPDATE verification_sessions"
                    " SET status = ?, updated_at = ?"
                    " WHERE id = ? AND status = ?",
                    (
                        VERIFICATION_STATUS_EXPIRED,
                        expired_at,
                        session_id,
                        VERIFICATION_STATUS_PENDING,
                    ),
                )
                if cursor.rowcount != 1:
                    return None
            return replace(
                session,
                status=VERIFICATION_STATUS_EXPIRED,
                updated_at=expired_at,
            )

    def _expire_due_verification_sessions_sync(
        self,
        *,
        expired_at: str,
        limit: int,
    ) -> list[VerificationSession]:
        with self._connection() as connection:
            rows = connection.execute(
                f"{VERIFICATION_SESSION_SELECT}"
                " WHERE status = ?"
                " AND expires_at <> ''"
                " AND expires_at <= ?"
                " ORDER BY expires_at, id"
                " LIMIT ?",
                (VERIFICATION_STATUS_PENDING, expired_at, max(1, int(limit))),
            ).fetchall()

            expired_sessions: list[VerificationSession] = []
            with connection:
                for row in rows:
                    session = verification_session_from_row(row)
                    if session is None:
                        continue
                    cursor = connection.execute(
                        "UPDATE verification_sessions"
                        " SET status = ?, updated_at = ?"
                        " WHERE id = ? AND status = ?",
                        (
                            VERIFICATION_STATUS_EXPIRED,
                            expired_at,
                            session.id,
                            VERIFICATION_STATUS_PENDING,
                        ),
                    )
                    if cursor.rowcount != 1:
                        continue
                    expired_sessions.append(
                        replace(session, status=VERIFICATION_STATUS_EXPIRED, updated_at=expired_at)
                    )
            return expired_sessions

    def _get_verification_session_with_connection(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: int,
    ) -> VerificationSession | None:
        row = connection.execute(
            f"{VERIFICATION_SESSION_SELECT} WHERE id = ?",
            (session_id,),
        ).fetchone()
        return verification_session_from_row(row)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

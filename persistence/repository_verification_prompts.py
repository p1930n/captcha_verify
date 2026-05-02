from __future__ import annotations

import asyncio

from ..domain.models import VERIFICATION_STATUS_PENDING, VerificationPushMessage
from .repository_verification_rows import (
    PUSH_SESSION_COLUMNS,
    VERIFICATION_SESSION_SELECT,
    verification_push_message_from_row,
    verification_session_from_row,
)


class VerificationPromptRepositoryMixin:
    async def set_verification_prompt_message(
        self, *, session_id: int, prompt_message_id: str,
    ):
        return await asyncio.to_thread(
            self._set_verification_prompt_message_sync,
            session_id=session_id, prompt_message_id=prompt_message_id,
        )

    async def add_verification_push_message(
        self, *, session_id: int, push_group_id: str, message_id: str,
    ) -> VerificationPushMessage:
        return await asyncio.to_thread(
            self._add_verification_push_message_sync,
            session_id=session_id, push_group_id=push_group_id, message_id=message_id,
        )

    async def mark_verification_prompt_approval_ready(
        self, *, session_id: int, prompt_message_id: str,
    ):
        return await asyncio.to_thread(
            self._mark_verification_prompt_approval_ready_sync,
            session_id=session_id, prompt_message_id=prompt_message_id,
        )

    async def mark_verification_prompt_rejection_ready(
        self, *, session_id: int, prompt_message_id: str,
    ):
        return await asyncio.to_thread(
            self._mark_verification_prompt_rejection_ready_sync,
            session_id=session_id, prompt_message_id=prompt_message_id,
        )

    async def mark_verification_push_message_approval_ready(
        self, *, session_id: int, push_group_id: str, message_id: str,
    ) -> VerificationPushMessage | None:
        return await asyncio.to_thread(
            self._mark_verification_push_message_approval_ready_sync,
            session_id=session_id, push_group_id=push_group_id, message_id=message_id,
        )

    async def mark_verification_push_message_rejection_ready(
        self, *, session_id: int, push_group_id: str, message_id: str,
    ) -> VerificationPushMessage | None:
        return await asyncio.to_thread(
            self._mark_verification_push_message_rejection_ready_sync,
            session_id=session_id, push_group_id=push_group_id, message_id=message_id,
        )

    async def find_pending_session_by_group_prompt(
        self, *, platform: str, group_id: str, message_id: str,
    ):
        return await asyncio.to_thread(
            self._find_pending_session_by_group_prompt_sync,
            platform=platform, group_id=group_id, message_id=message_id,
        )

    async def find_pending_session_by_group_prompt_for_rejection(
        self, *, platform: str, group_id: str, message_id: str,
    ):
        return await asyncio.to_thread(
            self._find_pending_session_by_group_prompt_for_rejection_sync,
            platform=platform, group_id=group_id, message_id=message_id,
        )

    async def find_pending_session_by_push_prompt(
        self, *, platform: str, push_group_id: str, message_id: str,
    ):
        return await asyncio.to_thread(
            self._find_pending_session_by_push_prompt_sync,
            platform=platform, push_group_id=push_group_id, message_id=message_id,
        )

    async def find_pending_session_by_push_prompt_for_rejection(
        self, *, platform: str, push_group_id: str, message_id: str,
    ):
        return await asyncio.to_thread(
            self._find_pending_session_by_push_prompt_for_rejection_sync,
            platform=platform, push_group_id=push_group_id, message_id=message_id,
        )

    async def list_verification_push_messages(
        self, *, session_id: int,
    ) -> list[VerificationPushMessage]:
        return await asyncio.to_thread(
            self._list_verification_push_messages_sync, session_id=session_id,
        )

    def _set_verification_prompt_message_sync(
        self,
        *,
        session_id: int,
        prompt_message_id: str,
    ):
        now = _utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE verification_sessions
                    SET prompt_message_id = ?,
                        prompt_approval_ready = 0,
                        prompt_rejection_ready = 0,
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
                        rejection_ready,
                        created_at
                    )
                    VALUES (?, ?, ?, 0, 0, ?)
                    ON CONFLICT (session_id, push_group_id, message_id)
                    DO UPDATE SET
                        approval_ready = 0,
                        rejection_ready = 0,
                        created_at = excluded.created_at
                    """,
                    (session_id, push_group_id, message_id, now),
                )
        return VerificationPushMessage(
            session_id=session_id,
            push_group_id=push_group_id,
            message_id=message_id,
            approval_ready=False,
            rejection_ready=False,
            created_at=now,
        )

    def _mark_verification_prompt_approval_ready_sync(
        self,
        *,
        session_id: int,
        prompt_message_id: str,
    ):
        return self._mark_prompt_ready(
            session_id=session_id,
            prompt_message_id=prompt_message_id,
            column_name="prompt_approval_ready",
        )

    def _mark_verification_prompt_rejection_ready_sync(
        self,
        *,
        session_id: int,
        prompt_message_id: str,
    ):
        return self._mark_prompt_ready(
            session_id=session_id,
            prompt_message_id=prompt_message_id,
            column_name="prompt_rejection_ready",
        )

    def _mark_prompt_ready(
        self,
        *,
        session_id: int,
        prompt_message_id: str,
        column_name: str,
    ):
        now = _utc_now()
        with self._connection() as connection:
            with connection:
                connection.execute(
                    f"""
                    UPDATE verification_sessions
                    SET {column_name} = 1,
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
        return self._mark_push_message_ready(
            session_id=session_id,
            push_group_id=push_group_id,
            message_id=message_id,
            column_name="approval_ready",
        )

    def _mark_verification_push_message_rejection_ready_sync(
        self,
        *,
        session_id: int,
        push_group_id: str,
        message_id: str,
    ) -> VerificationPushMessage | None:
        return self._mark_push_message_ready(
            session_id=session_id,
            push_group_id=push_group_id,
            message_id=message_id,
            column_name="rejection_ready",
        )

    def _mark_push_message_ready(
        self,
        *,
        session_id: int,
        push_group_id: str,
        message_id: str,
        column_name: str,
    ) -> VerificationPushMessage | None:
        with self._connection() as connection:
            with connection:
                connection.execute(
                    f"""
                    UPDATE verification_push_messages
                    SET {column_name} = 1
                    WHERE session_id = ?
                        AND push_group_id = ?
                        AND message_id = ?
                    """,
                    (session_id, push_group_id, message_id),
                )
            row = _push_message_row(
                connection,
                session_id=session_id,
                push_group_id=push_group_id,
                message_id=message_id,
            )
            return verification_push_message_from_row(row) if row else None

    def _find_pending_session_by_group_prompt_sync(
        self,
        *,
        platform: str,
        group_id: str,
        message_id: str,
    ):
        return self._find_pending_session_by_group_prompt_ready(
            platform=platform,
            group_id=group_id,
            message_id=message_id,
            ready_column_name="prompt_approval_ready",
        )

    def _find_pending_session_by_group_prompt_for_rejection_sync(
        self,
        *,
        platform: str,
        group_id: str,
        message_id: str,
    ):
        return self._find_pending_session_by_group_prompt_ready(
            platform=platform,
            group_id=group_id,
            message_id=message_id,
            ready_column_name="prompt_rejection_ready",
        )

    def _find_pending_session_by_group_prompt_ready(
        self,
        *,
        platform: str,
        group_id: str,
        message_id: str,
        ready_column_name: str,
    ):
        with self._connection() as connection:
            row = connection.execute(
                f"{VERIFICATION_SESSION_SELECT}"
                " WHERE platform = ?"
                " AND group_id = ?"
                " AND prompt_message_id = ?"
                " AND status = ?"
                f" AND {ready_column_name} = 1"
                " ORDER BY id DESC"
                " LIMIT 1",
                (platform, group_id, message_id, VERIFICATION_STATUS_PENDING),
            ).fetchone()
            return verification_session_from_row(row)

    def _find_pending_session_by_push_prompt_sync(
        self,
        *,
        platform: str,
        push_group_id: str,
        message_id: str,
    ):
        return self._find_pending_session_by_push_prompt_ready(
            platform=platform,
            push_group_id=push_group_id,
            message_id=message_id,
            ready_column_name="approval_ready",
        )

    def _find_pending_session_by_push_prompt_for_rejection_sync(
        self,
        *,
        platform: str,
        push_group_id: str,
        message_id: str,
    ):
        return self._find_pending_session_by_push_prompt_ready(
            platform=platform,
            push_group_id=push_group_id,
            message_id=message_id,
            ready_column_name="rejection_ready",
        )

    def _find_pending_session_by_push_prompt_ready(
        self,
        *,
        platform: str,
        push_group_id: str,
        message_id: str,
        ready_column_name: str,
    ):
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT {PUSH_SESSION_COLUMNS}"
                " FROM verification_sessions AS session"
                " JOIN verification_push_messages AS push"
                " ON push.session_id = session.id"
                " WHERE session.platform = ?"
                " AND push.push_group_id = ?"
                " AND push.message_id = ?"
                " AND session.status = ?"
                f" AND push.{ready_column_name} = 1"
                " ORDER BY session.id DESC"
                " LIMIT 1",
                (
                    platform,
                    push_group_id,
                    message_id,
                    VERIFICATION_STATUS_PENDING,
                ),
            ).fetchone()
            return verification_session_from_row(row)

    def _list_verification_push_messages_sync(
        self,
        *,
        session_id: int,
    ) -> list[VerificationPushMessage]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT session_id, push_group_id, message_id, approval_ready,
                    rejection_ready, created_at
                FROM verification_push_messages
                WHERE session_id = ?
                ORDER BY push_group_id, message_id
                """,
                (session_id,),
            ).fetchall()
            return [verification_push_message_from_row(row) for row in rows]


def _push_message_row(
    connection,
    *,
    session_id: int,
    push_group_id: str,
    message_id: str,
):
    return connection.execute(
        """
        SELECT session_id, push_group_id, message_id, approval_ready,
            rejection_ready, created_at
        FROM verification_push_messages
        WHERE session_id = ?
            AND push_group_id = ?
            AND message_id = ?
        """,
        (session_id, push_group_id, message_id),
    ).fetchone()


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()

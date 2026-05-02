from __future__ import annotations

from ..domain.models import (
    DEFAULT_VERIFY_WINDOW_SECONDS,
    VerificationPushMessage,
    VerificationSession,
)

VERIFICATION_SESSION_COLUMNS = ", ".join(
    (
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
    )
)
VERIFICATION_SESSION_SELECT = (
    f"SELECT {VERIFICATION_SESSION_COLUMNS} FROM verification_sessions"
)
PUSH_SESSION_COLUMNS = ", ".join(
    f"session.{col}" for col in VERIFICATION_SESSION_COLUMNS.split(", ")
)


def verification_session_from_row(row: object) -> VerificationSession | None:
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
        prompt_rejection_ready=bool(values[7]),
        prompt_message_id=str(values[8] or ""),
        expires_at=str(values[9] or ""),
        muted_until=str(values[10] or ""),
        created_at=str(values[11] or ""),
        updated_at=str(values[12] or ""),
        approved_at=str(values[13] or ""),
        approver_id=str(values[14] or ""),
        approval_source=str(values[15] or ""),
        approval_group_id=str(values[16] or ""),
        approval_message_id=str(values[17] or ""),
    )


def verification_push_message_from_row(row: object) -> VerificationPushMessage:
    values = tuple(row)
    return VerificationPushMessage(
        session_id=int(values[0]),
        push_group_id=str(values[1]),
        message_id=str(values[2]),
        approval_ready=bool(values[3]),
        rejection_ready=bool(values[4]),
        created_at=str(values[5] or ""),
    )

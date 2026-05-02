from __future__ import annotations

from dataclasses import dataclass


VERIFICATION_STATUS_PENDING = "pending"
VERIFICATION_STATUS_APPROVED = "approved"
VERIFICATION_STATUS_SUPERSEDED = "superseded"
APPROVAL_SOURCE_GROUP_PROMPT = "group_prompt"
APPROVAL_SOURCE_PUSH_PROMPT = "push_prompt"


@dataclass(frozen=True, slots=True)
class PlatformEventSnapshot:
    platform: str
    group_id: str
    sender_id: str
    sender_role: str = ""
    sender_display_name: str = ""

    @property
    def sender_is_group_manager(self) -> bool:
        return self.sender_role in {"admin", "owner"}


@dataclass(frozen=True, slots=True)
class VerifyGroupConfig:
    platform: str
    group_id: str
    enabled: bool
    push_group_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerifyOverviewRow:
    platform: str
    group_id: str
    enabled: bool
    push_group_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NewMemberNotice:
    platform: str
    group_id: str
    user_id: str
    operator_id: str
    sub_type: str
    time_raw: str = ""


@dataclass(frozen=True, slots=True)
class GroupEmojiReactionNotice:
    platform: str
    group_id: str
    user_id: str
    message_id: str
    emoji_ids: tuple[str, ...]
    time_raw: str = ""


@dataclass(frozen=True, slots=True)
class VerificationSession:
    id: int
    platform: str
    group_id: str
    user_id: str
    status: str
    prompt_message_id: str = ""
    muted_until: str = ""
    created_at: str = ""
    updated_at: str = ""
    approved_at: str = ""
    approver_id: str = ""
    approval_source: str = ""
    approval_group_id: str = ""
    approval_message_id: str = ""


@dataclass(frozen=True, slots=True)
class VerificationPushMessage:
    session_id: int
    push_group_id: str
    message_id: str
    created_at: str = ""

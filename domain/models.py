from __future__ import annotations

from dataclasses import dataclass


DEFAULT_VERIFY_WINDOW_SECONDS = 6 * 60 * 60
MIN_VERIFY_WINDOW_SECONDS = 1
MAX_VERIFY_WINDOW_SECONDS = 30 * 24 * 60 * 60
VERIFICATION_STATUS_PENDING = "pending"
VERIFICATION_STATUS_APPROVED = "approved"
VERIFICATION_STATUS_SUPERSEDED = "superseded"
VERIFICATION_STATUS_EXPIRED = "expired"
APPROVAL_SOURCE_GROUP_PROMPT = "group_prompt"
APPROVAL_SOURCE_PUSH_PROMPT = "push_prompt"
APPROVAL_SOURCE_PRIVATE_MESSAGE = "private_message"
TIMEOUT_ACTION_KICK = "kick"
TIMEOUT_ACTION_MUTE = "mute"
DEFAULT_TIMEOUT_ACTION = TIMEOUT_ACTION_KICK
DEFAULT_BLACKLIST_KICK_ENABLED = True


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
    verify_window_seconds: int = DEFAULT_VERIFY_WINDOW_SECONDS
    timeout_action: str = DEFAULT_TIMEOUT_ACTION
    blacklist_kick_enabled: bool = DEFAULT_BLACKLIST_KICK_ENABLED
    push_group_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerifyOverviewRow:
    platform: str
    group_id: str
    enabled: bool
    verify_window_seconds: int = DEFAULT_VERIFY_WINDOW_SECONDS
    timeout_action: str = DEFAULT_TIMEOUT_ACTION
    blacklist_kick_enabled: bool = DEFAULT_BLACKLIST_KICK_ENABLED
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
    self_id: str
    message_id: str
    emoji_ids: tuple[str, ...]
    time_raw: str = ""


@dataclass(frozen=True, slots=True)
class PrivateMessageNotice:
    platform: str
    user_id: str
    message_id: str = ""
    time_raw: str = ""


@dataclass(frozen=True, slots=True)
class VerificationSession:
    id: int
    platform: str
    group_id: str
    user_id: str
    status: str
    verify_window_seconds: int = DEFAULT_VERIFY_WINDOW_SECONDS
    prompt_approval_ready: bool = False
    prompt_rejection_ready: bool = False
    prompt_message_id: str = ""
    expires_at: str = ""
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
    approval_ready: bool = False
    rejection_ready: bool = False
    created_at: str = ""

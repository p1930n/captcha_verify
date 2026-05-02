from __future__ import annotations

from dataclasses import dataclass


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

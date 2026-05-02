from __future__ import annotations

import csv
import io

from ..domain.models import VerifyGroupConfig, VerifyOverviewRow
from ..persistence.repository import VerifyRepository


OVERVIEW_CSV_FORMATS = frozenset(("csv", "table"))


class VerifyCommandService:
    def __init__(self, repository: VerifyRepository) -> None:
        self._repository = repository

    async def set_enabled(
        self,
        *,
        platform: str,
        group_id: str,
        enabled: bool,
        updated_by: str,
    ) -> str:
        config = await self._repository.set_group_enabled(
            platform=platform,
            group_id=group_id,
            enabled=enabled,
            updated_by=updated_by,
        )
        state = "已启用" if config.enabled else "已停用"
        return f"验证码入群审核{state}：群 {group_id}。"

    async def bind_push_group(
        self,
        *,
        platform: str,
        group_id: str,
        push_group_id: str,
        created_by: str,
    ) -> str:
        config = await self._repository.add_push_binding(
            platform=platform,
            group_id=group_id,
            push_group_id=push_group_id,
            created_by=created_by,
        )
        return "\n".join(
            [
                "推送群绑定已保存。",
                f"监控群={config.group_id}",
                f"推送群={_format_push_groups(config)}",
            ]
        )

    async def format_status(self, *, platform: str, group_id: str) -> str:
        config = await self._repository.get_group_config(
            platform=platform,
            group_id=group_id,
        )
        return "\n".join(
            [
                "验证码入群审核状态：",
                f"平台={config.platform}",
                f"群号={config.group_id}",
                f"已启用={_format_human_bool(config.enabled)}",
                f"推送群={_format_push_groups(config)}",
            ]
        )

    async def format_overview(self, *, platform: str, output_format: str = "") -> str:
        rows = await self._repository.list_enabled_overview(platform=platform)
        if output_format.strip().casefold() in OVERVIEW_CSV_FORMATS:
            return _format_overview_csv(rows)
        return _format_overview_summary(rows)

    def format_help(self) -> str:
        return "\n".join(
            [
                "验证码入群审核命令：",
                ".verify enable [group_id] - 启用当前群或指定群",
                ".verify disable [group_id] - 停用当前群或指定群",
                ".verify status [group_id] - 查看当前群或指定群状态",
                ".verify bind <push_group_id> - 将当前群绑定到推送群",
                ".verify bind <group_id> <push_group_id> - 将指定群绑定到推送群",
                ".verify overview [csv] - 查看已启用群与推送群绑定",
            ]
        )


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _format_human_bool(value: bool) -> str:
    return "是" if value else "否"


def _format_push_groups(config: VerifyGroupConfig) -> str:
    if not config.push_group_ids:
        return "无"
    return ",".join(config.push_group_ids)


def _format_overview_summary(rows: list[VerifyOverviewRow]) -> str:
    binding_count = sum(len(row.push_group_ids) for row in rows)
    return "\n".join(
        [
            "验证码入群审核总览：",
            f"已启用群数={len(rows)}",
            f"推送绑定数={binding_count}",
            "使用 .verify overview csv 查看明细。",
        ]
    )


def _format_overview_csv(rows: list[VerifyOverviewRow]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("platform", "group_id", "enabled", "push_groups"))
    for row in rows:
        writer.writerow(
            (
                row.platform,
                row.group_id,
                _format_bool(row.enabled),
                ";".join(row.push_group_ids),
            )
        )
    return output.getvalue().rstrip("\n")

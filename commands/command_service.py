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
        state = "enabled" if config.enabled else "disabled"
        return f"Captcha Verify group {group_id} is {state}."

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
                "Captcha Verify push binding saved.",
                f"group_id={config.group_id}",
                f"push_groups={_format_push_groups(config)}",
            ]
        )

    async def format_status(self, *, platform: str, group_id: str) -> str:
        config = await self._repository.get_group_config(
            platform=platform,
            group_id=group_id,
        )
        return "\n".join(
            [
                "Captcha Verify status:",
                f"platform={config.platform}",
                f"group_id={config.group_id}",
                f"enabled={_format_bool(config.enabled)}",
                f"push_groups={_format_push_groups(config)}",
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
                "Captcha Verify commands:",
                ".verify enable [group_id]",
                ".verify disable [group_id]",
                ".verify status [group_id]",
                ".verify bind <push_group_id>",
                ".verify bind <group_id> <push_group_id>",
                ".verify overview [csv]",
            ]
        )


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def _format_push_groups(config: VerifyGroupConfig) -> str:
    if not config.push_group_ids:
        return "-"
    return ",".join(config.push_group_ids)


def _format_overview_summary(rows: list[VerifyOverviewRow]) -> str:
    binding_count = sum(len(row.push_group_ids) for row in rows)
    return "\n".join(
        [
            "Captcha Verify overview:",
            f"enabled_groups={len(rows)}",
            f"push_bindings={binding_count}",
            "Use .verify overview csv for details.",
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

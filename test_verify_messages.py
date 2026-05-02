from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from captcha_verify.domain.notice_adapter import parse_new_member_notice  # noqa: E402
from captcha_verify.workflow.messages import format_push_verification_log  # noqa: E402


class VerificationMessageTests(unittest.TestCase):
    def test_formats_unix_notice_time_as_local_datetime(self) -> None:
        notice = parse_new_member_notice(
            {
                "post_type": "notice",
                "notice_type": "group_increase",
                "group_id": 10001,
                "user_id": 30001,
                "sub_type": "invite",
                "time": 1710000000,
            },
            platform="aiocqhttp",
        )

        self.assertIsNotNone(notice)
        self.assertIn("时间=2024-03-10 00-00", format_push_verification_log(notice))


if __name__ == "__main__":
    unittest.main()

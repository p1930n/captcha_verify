from __future__ import annotations

import logging

WORKFLOW_LOGGER_NAME = "captcha_verify.workflow.verification_workflow"

try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger(WORKFLOW_LOGGER_NAME)

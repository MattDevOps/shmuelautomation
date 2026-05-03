"""Sentry error tracking — initialised once at startup, no-op when DSN unset.

We deliberately keep traces/profiles low-volume and PII off so the free tier
covers us indefinitely. Errors and unhandled exceptions are the signal we
care about; everything else is performance metrics that are nice but not
worth the data spend.
"""
import logging

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from shmuel_backend.config import settings

log = logging.getLogger(__name__)


def configure_sentry() -> None:
    if not settings.sentry_dsn:
        log.info("Sentry not configured (SENTRY_DSN unset); skipping init.")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        # Capture errors and unhandled exceptions; don't sample traces by default
        # (keeps event volume low so we stay on the free tier).
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        # Don't send request bodies — they may contain owner phones or notes.
        send_default_pii=False,
        max_request_body_size="never",
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
    )
    log.info("Sentry initialised (env=%s)", settings.environment)

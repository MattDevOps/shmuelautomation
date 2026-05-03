"""Structured JSON logging for production.

Cloud Run / GCP Logs ingest stdout. When each line is a JSON object with
`severity`, `message`, etc., GCP renders them as proper log entries with
filterable fields. In development we keep human-readable formatting.
"""
import json
import logging
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """Renders a log record as a single JSON line.

    Maps Python log levels to GCP severity values so Logs Explorer can
    filter by severity correctly.
    """

    SEVERITY = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": self.SEVERITY.get(record.levelname, "DEFAULT"),
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["stack_trace"] = self.formatException(record.exc_info)
        # Allow callers to attach extra structured context via logger.info(msg, extra={...})
        for key, value in record.__dict__.items():
            if key in {
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "levelname", "levelno", "lineno",
                "module", "msecs", "message", "msg", "name", "pathname",
                "process", "processName", "relativeCreated", "stack_info",
                "thread", "threadName", "taskName",
            }:
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(environment: str) -> None:
    """Wire up logging once at app startup. Idempotent."""
    handler = logging.StreamHandler(sys.stdout)
    if environment == "development":
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Quiet down libraries that are too chatty by default.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

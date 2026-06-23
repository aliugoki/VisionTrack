"""Structured logging via structlog.

Human-readable colored output in development, JSON in production.

Why PrintLoggerFactory instead of LoggerFactory?
   structlog can write through Python's stdlib logging (LoggerFactory)
   or directly to stdout (PrintLoggerFactory). The stdlib path is
   convenient but Celery captures stdout-via-stdlib and re-emits at
   WARNING level for any non-task log line, which makes every INFO
   log show up as `[WARNING/ForkPoolWorker-2]` in `docker compose logs`.

   Writing directly to stdout via PrintLoggerFactory bypasses that
   capture entirely — Celery sees no stdlib log calls to reroute, and
   our INFO lines render as INFO.
"""

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO

    # Configure stdlib too so uvicorn/SQLAlchemy logs still flow.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.APP_ENV == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        # PrintLoggerFactory writes straight to stdout, bypassing the
        # stdlib log -> Celery WARNING-capture problem.
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name) if name else structlog.get_logger()

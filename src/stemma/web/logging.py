"""Production logging configuration with the server access logger disabled."""

from __future__ import annotations

ACCESS_LOGGER_NAME = "stemma.web.access"

SERVER_LOG_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "format": "%(levelprefix)s %(name)s %(message)s",
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "format": "%(levelprefix)s %(name)s access log disabled",
        },
        "safe": {
            "format": "%(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "safe_stderr": {
            "class": "logging.StreamHandler",
            "formatter": "safe",
            "stream": "ext://sys.stderr",
        },
        "discard": {"class": "logging.NullHandler"},
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["safe_stderr"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["safe_stderr"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["discard"],
            "level": "CRITICAL",
            "propagate": False,
        },
        ACCESS_LOGGER_NAME: {
            "handlers": ["safe_stderr"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

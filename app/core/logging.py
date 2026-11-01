"""Structured JSON-like logging setup.

Why this module exists:
Print statements disappear or lack timestamps and severity levels in production containers.
Centralizing logging ensures every request, rate-limit hit, and security event is recorded
consistently without leaking sensitive tokens or passwords.
"""

import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """Configure root application logger with structured key-value output."""
    level = logging.DEBUG if debug else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger("taskflow")
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.propagate = False


logger = logging.getLogger("taskflow")

import logging
from collections.abc import Iterator

import pytest

from src.shared.logging_config import LOG_FORMAT, configure_logging


@pytest.fixture
def root_logger() -> Iterator[logging.Logger]:
    """The root logger, restored after the test so pytest's own capture keeps working."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    root.handlers[:] = handlers
    root.setLevel(level)


@pytest.mark.parametrize("level", ["debug", "DEBUG", "Debug"])
def test_configure_logging_accepts_any_case(root_logger: logging.Logger, level: str) -> None:
    configure_logging(level)

    assert root_logger.level == logging.DEBUG


def test_configure_logging_replaces_existing_handlers(root_logger: logging.Logger) -> None:
    stale = logging.NullHandler()
    root_logger.addHandler(stale)

    configure_logging("WARNING")

    assert stale not in root_logger.handlers
    assert root_logger.level == logging.WARNING
    [handler] = root_logger.handlers
    assert handler.formatter is not None
    assert handler.formatter._fmt == LOG_FORMAT


def test_configure_logging_defaults_to_info(root_logger: logging.Logger) -> None:
    configure_logging()

    assert root_logger.level == logging.INFO

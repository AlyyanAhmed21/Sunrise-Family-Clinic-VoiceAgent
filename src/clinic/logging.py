from __future__ import annotations

import atexit
import copy
import logging
import queue
import traceback
from datetime import date, timedelta
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path
from typing import TextIO

from clinic.security.masking import mask_text


def _mask_or_marker(value: str) -> str:
    try:
        return mask_text(value)
    except Exception:
        return "[REDACTED_LOG_CONTENT]"


class MaskingFilter(logging.Filter):
    """Mask every record at the sink. Deterministic regexes only: this runs on every log line,
    so it must stay cheap and must never log anything itself."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in [key for key in record.__dict__ if key.startswith("lk.pii")]:
            delattr(record, key)  # LiveKit attaches raw transcripts as `lk.pii.*` extras
        try:
            message = record.getMessage()
        except Exception as error:
            try:
                template = str(record.msg)
            except Exception:
                template = "[UNPRINTABLE_LOG_MESSAGE]"
            message = f"[LOG_FORMAT_ERROR:{type(error).__name__}] {template}"
        record.msg = _mask_or_marker(message)
        record.args = ()

        if record.exc_info is not None:
            try:
                exception_text = "".join(traceback.format_exception(*record.exc_info))
            except Exception:
                exception_text = "[REDACTED_EXCEPTION]"
            record.exc_text = _mask_or_marker(exception_text)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = _mask_or_marker(record.exc_text)
        if record.stack_info:
            record.stack_info = _mask_or_marker(record.stack_info)
        return True


class NonBlockingQueueHandler(QueueHandler):
    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return copy.copy(record)


_listener: QueueListener | None = None


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
LOG_PREFIX = "agent-"


def daily_log_file(directory: Path, *, keep_days: int = 7, today: date | None = None) -> Path:
    """Today's log file (`agent-YYYY-MM-DD.log`); deletes files older than `keep_days`.

    One file per day instead of renaming a live file, so concurrent call processes on Windows
    never fight over a rotation.
    """
    today = today or date.today()
    directory.mkdir(parents=True, exist_ok=True)
    oldest_kept = today - timedelta(days=keep_days - 1)
    for old in directory.glob(f"{LOG_PREFIX}*.log"):
        try:
            if date.fromisoformat(old.stem.removeprefix(LOG_PREFIX)) < oldest_kept:
                old.unlink(missing_ok=True)
        except (ValueError, OSError):
            continue  # not one of ours, or in use by another process: leave it
    return directory / f"{LOG_PREFIX}{today.isoformat()}.log"


def configure_logging(
    level: int = logging.INFO,
    *,
    stream: TextIO | None = None,
    log_file: Path | None = None,
) -> None:
    """Route every log record through a queue; mask it on the listener thread, never on the
    audio event loop. Optionally also append to `log_file` (masked the same way)."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None

    handlers: list[logging.Handler] = [logging.StreamHandler(stream)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for handler in handlers:
        handler.addFilter(MaskingFilter())
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
    log_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    _listener = QueueListener(log_queue, *handlers, respect_handler_level=True)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(NonBlockingQueueHandler(log_queue))
    root.setLevel(level)
    _listener.start()


def shutdown_logging() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


atexit.register(shutdown_logging)

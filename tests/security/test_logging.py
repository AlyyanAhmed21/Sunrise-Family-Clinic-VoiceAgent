from __future__ import annotations

import io
import logging
import sys

from clinic import logging as clinic_logging


def test_parameterized_log_record_is_rendered_once(monkeypatch) -> None:
    monkeypatch.setattr(clinic_logging, "mask_text", lambda value: value)
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "name=%s count=%d",
        ("caller", 2),
        None,
    )

    assert clinic_logging.MaskingFilter().filter(record)
    assert record.args == ()
    assert record.getMessage() == "name=caller count=2"


def test_log_arguments_are_redacted_after_formatting() -> None:
    record = logging.LogRecord(
        "third_party",
        logging.INFO,
        __file__,
        1,
        "callback=%s",
        ("555-201-3344",),
        None,
    )

    clinic_logging.MaskingFilter().filter(record)

    assert record.args == ()
    assert "555-201-3344" not in record.getMessage()
    assert "[REDACTED_PHONE]" in record.getMessage()


def test_malformed_parameterized_record_does_not_raise(monkeypatch) -> None:
    monkeypatch.setattr(clinic_logging, "mask_text", lambda value: value)
    record = logging.LogRecord("third_party", logging.INFO, __file__, 1, "count=%d", ("bad",), None)

    clinic_logging.MaskingFilter().filter(record)

    assert record.args == ()
    assert record.getMessage().startswith("[LOG_FORMAT_ERROR:TypeError]")


def test_exception_text_is_redacted_and_not_formatted_twice(monkeypatch) -> None:
    monkeypatch.setattr(
        clinic_logging,
        "mask_text",
        lambda value: value.replace("sensitive-example", "[REDACTED]"),
    )
    try:
        raise RuntimeError("sensitive-example")
    except RuntimeError:
        record = logging.LogRecord(
            "third_party",
            logging.ERROR,
            __file__,
            1,
            "operation=%s",
            ("sensitive-example",),
            sys.exc_info(),
        )

    clinic_logging.MaskingFilter().filter(record)

    assert record.args == ()
    assert record.exc_info is None
    assert "sensitive-example" not in record.getMessage()
    assert record.exc_text is not None
    assert "sensitive-example" not in record.exc_text


def test_preformatted_exception_text_is_redacted(monkeypatch) -> None:
    monkeypatch.setattr(
        clinic_logging,
        "mask_text",
        lambda value: value.replace("sensitive-example", "[REDACTED]"),
    )
    record = logging.LogRecord("third_party", logging.ERROR, __file__, 1, "failed", (), None)
    record.exc_text = "RuntimeError: sensitive-example"

    clinic_logging.MaskingFilter().filter(record)

    assert "sensitive-example" not in record.exc_text


def test_third_party_logger_uses_redacted_async_sink() -> None:
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    logger = logging.getLogger("livekit.test_redaction")
    original_logger_level = logger.level
    original_propagate = logger.propagate
    stream = io.StringIO()
    try:
        clinic_logging.configure_logging(stream=stream)
        logger.setLevel(logging.INFO)
        logger.propagate = True
        logger.info(
            "dob=%s phone=%s",
            "1985-03-14",
            "555-201-3344",
            extra={"lk.pii.user_input": "my last four is 3344"},
        )
        clinic_logging.shutdown_logging()
        output = stream.getvalue()
    finally:
        clinic_logging.shutdown_logging()
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)
        logger.setLevel(original_logger_level)
        logger.propagate = original_propagate

    assert "555-201-3344" not in output and "1985-03-14" not in output
    assert "3344" not in output
    assert "LOG_FORMAT_ERROR" not in output
    # Regression: Presidio used to log a warning per masked line, which was masked again,
    # producing thousands of records from one line and starving the audio loop.
    assert len(output.strip().splitlines()) == 1


def test_daily_log_files_are_kept_for_a_week(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from datetime import date

    for day in ("2026-11-10", "2026-11-18", "2026-11-19", "2026-11-24"):
        (tmp_path / f"agent-{day}.log").write_text("x", encoding="utf-8")
    (tmp_path / "notes.log").write_text("not ours", encoding="utf-8")

    today = clinic_logging.daily_log_file(tmp_path, keep_days=7, today=date(2026, 11, 25))

    assert today.name == "agent-2026-11-25.log"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "agent-2026-11-19.log",
        "agent-2026-11-24.log",
        "notes.log",
    ]


def test_log_file_lines_are_masked(tmp_path) -> None:  # type: ignore[no-untyped-def]
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    log_file = tmp_path / "agent-2026-11-25.log"
    try:
        clinic_logging.configure_logging(stream=io.StringIO(), log_file=log_file)
        logging.getLogger("sunrise.test").info("callback=%s", "555-201-3344")
        clinic_logging.shutdown_logging()
    finally:
        clinic_logging.shutdown_logging()
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)

    written = log_file.read_text(encoding="utf-8")
    assert "callback=[REDACTED_PHONE]" in written and "555-201-3344" not in written


def test_livekit_transcript_extras_are_dropped() -> None:
    record = logging.LogRecord("livekit.agents", logging.WARNING, __file__, 1, "skip", (), None)
    record.__dict__["lk.pii.user_input"] = "my date of birth is March 14 1985"

    clinic_logging.MaskingFilter().filter(record)

    assert "lk.pii.user_input" not in record.__dict__

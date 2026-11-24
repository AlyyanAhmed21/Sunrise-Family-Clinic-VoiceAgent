import logging

from clinic.security.masking import mask_text


class MaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_text(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(
                mask_text(str(arg)) if isinstance(arg, str) else arg for arg in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: mask_text(str(value)) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(MaskingFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

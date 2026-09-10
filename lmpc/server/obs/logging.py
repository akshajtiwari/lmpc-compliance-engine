"""Structured logging (Part 19): one line of JSON per event, correlation ID included.
Scanning text logs is how incidents get misread; a JSON line is greppable and
machine-checkable in the same instant."""
from __future__ import annotations
import json
import logging
import uuid
from contextvars import ContextVar

trace_id: ContextVar[str] = ContextVar("trace_id", default="")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        row = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
               "level": record.levelname, "msg": record.getMessage(),
               "trace_id": trace_id.get() or str(uuid.uuid4())[:8]}
        if record.exc_info:
            row["exc"] = record.exc_info[0].__name__
        return json.dumps(row)


def setup(level: str = "INFO") -> logging.Logger:
    log = logging.getLogger("lmpc")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(JsonFormatter())
        log.addHandler(h)
    log.setLevel(level)
    return log


def get() -> logging.Logger:
    return logging.getLogger("lmpc")
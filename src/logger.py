"""Logger agent with severity, filtering, redaction, and retention."""
import re
import logging
from datetime import datetime, timezone

REDACT_PATTERNS = [
    (re.compile(r"(api[_-]?key\s*[:=]\s*)[^\s,;]+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(api[_-]?secret\s*[:=]\s*)[^\s,;]+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(token\s*[:=]\s*)[^\s,;]+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(password\s*[:=]\s*)[^\s,;]+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(secret\s*[:=]\s*)[^\s,;]+", re.I), r"\1***REDACTED***"),
]

SEVERITIES = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def redact(text):
    if text is None:
        return text
    if not isinstance(text, str):
        text = str(text)
    for pat, repl in REDACT_PATTERNS:
        text = pat.sub(repl, text)
    return text


class Logger:
    def __init__(self, storage):
        self.storage = storage
        self._fallback = logging.getLogger("logger_agent")

    def log(self, agent, event_type, message, severity="INFO", symbol="", trade_id="", status="", metadata=None):
        sev = severity.upper() if severity else "INFO"
        if sev not in SEVERITIES:
            sev = "INFO"
        msg = redact(message)
        meta = metadata
        if isinstance(meta, dict):
            meta = {k: (redact(v) if isinstance(v, str) else v) for k, v in meta.items()}
        try:
            self.storage.log_event(agent=agent, symbol=symbol, event_type=event_type, status=status,
                                 reason=msg, trade_id=trade_id, severity=sev, message=msg, metadata=meta)
        except Exception as e:
            # safe fallback
            self._fallback.error("Logger failed: %s | %s %s %s", e, agent, event_type, msg)

    def debug(self, agent, event_type, message, **kw):
        self.log(agent, event_type, message, severity="DEBUG", **kw)

    def info(self, agent, event_type, message, **kw):
        self.log(agent, event_type, message, severity="INFO", **kw)

    def warning(self, agent, event_type, message, **kw):
        self.log(agent, event_type, message, severity="WARNING", **kw)

    def error(self, agent, event_type, message, **kw):
        self.log(agent, event_type, message, severity="ERROR", **kw)

    def critical(self, agent, event_type, message, **kw):
        self.log(agent, event_type, message, severity="CRITICAL", **kw)

    def prune(self, retention_days=30):
        try:
            return self.storage.prune_logs(retention_days=retention_days)
        except Exception as e:
            self._fallback.error("Prune failed: %s", e)
            return 0

    def query(self, **kw):
        return self.storage.recent_events(**kw)
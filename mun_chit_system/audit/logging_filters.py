import logging
import re

# Defensive filter: if any log record accidentally includes something that
# looks like it came from a chit message field, redact it. This is a
# belt-and-suspenders safety net — the real rule is that application code
# must never pass chit.message into a logger call.
_SUSPECT_KEYS = re.compile(r"(message|subject)\s*=\s*.+", re.IGNORECASE)


class NoChitContentFilter(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if _SUSPECT_KEYS.search(msg):
            record.msg = _SUSPECT_KEYS.sub("[redacted]", msg)
            record.args = ()
        return True

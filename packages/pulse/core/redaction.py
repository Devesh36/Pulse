import re

SECRET = re.compile(
    r'(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:api[_-]?key|password|passwd|secret|token)\s*["\x27]?\s*[:=]\s*["\x27]?)([^\s,"\x27;}]+)'
)
KNOWN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{10,}|AKIA[A-Z0-9]{16})\b")
URL_CREDENTIALS = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@")


def redact(value):
    if isinstance(value, str):
        return URL_CREDENTIALS.sub(
            r"\1[REDACTED]@", KNOWN.sub("[REDACTED]", SECRET.sub(r"\1[REDACTED]", value))
        )
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"(?i)key|password|secret|token|authorization", k)
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

# backend/utils/redact.py
"""
Helpers that keep secrets out of logs, audit details and the admin UI.

Anything that ends up in the audit trail or the structured log stream is
visible to administrators (and may be shipped to files or external log
tooling), so it must never contain passwords, tokens, private keys or
encrypted payloads, even by accident.
"""
import json
from datetime import date, datetime

REDACTED = '[REDACTED]'

# Substrings (case-insensitive) that mark a key as sensitive.
_SENSITIVE_KEY_PARTS = (
    'password', 'passwd', 'secret', 'token', 'authorization', 'cookie',
    'private_key', 'privatekey', 'encrypted', 'signature', 'api_key',
    'apikey', 'csrf', 'session_key', 'aes_key', 'iv', 'ciphertext', 'content',
)
# 'iv' and 'content' are exact-match only (they are too short / generic to
# match as substrings without redacting harmless keys like "device").
_EXACT_ONLY = {'iv', 'content'}

MAX_STRING = 500
MAX_ITEMS = 50
MAX_DEPTH = 5


def _is_sensitive(key) -> bool:
    k = str(key).lower()
    for part in _SENSITIVE_KEY_PARTS:
        if part in _EXACT_ONLY:
            if k == part:
                return True
        elif part in k:
            return True
    return False


def redact(value, _depth=0):
    """Return a JSON-safe copy of ``value`` with sensitive keys masked."""
    if _depth > MAX_DEPTH:
        return '[TRUNCATED]'
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= MAX_ITEMS:
                out['…'] = f'{len(value) - MAX_ITEMS} more keys'
                break
            out[str(k)] = REDACTED if _is_sensitive(k) else redact(v, _depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        out = [redact(v, _depth + 1) for v in items[:MAX_ITEMS]]
        if len(items) > MAX_ITEMS:
            out.append(f'… {len(items) - MAX_ITEMS} more')
        return out
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return f'<{len(value)} bytes>'
    if isinstance(value, str):
        return value if len(value) <= MAX_STRING else value[:MAX_STRING] + '…'
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value), _depth + 1)


def safe_path(path, query_string=b''):
    """
    ``path?query`` with the values of sensitive query parameters masked.

    Some endpoints receive a password in the query string (e.g. unlocking a
    status). The live request log must never show it.
    """
    from urllib.parse import parse_qsl, urlencode
    if isinstance(query_string, bytes):
        query_string = query_string.decode('utf-8', 'replace')
    if not query_string:
        return path
    pairs = [(k, REDACTED if _is_sensitive(k) else v) for k, v in parse_qsl(query_string, keep_blank_values=True)]
    return f"{path}?{urlencode(pairs, safe='[]')}"


def parse_json_details(raw):
    """
    Audit ``details`` were historically written with ``json.dumps`` into a
    JSON column, which stores a *string containing JSON* rather than an
    object. Accept both (and double-encoded) so old rows still render.
    """
    value = raw
    for _ in range(3):
        if isinstance(value, (bytes, bytearray)):
            value = value.decode('utf-8', 'replace')
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                value = json.loads(text)
                continue
            except (ValueError, TypeError):
                return {'raw': text[:MAX_STRING]}
        break
    return value

"""Durable, correlated warehouse diagnostics without credentials or session URLs."""
from datetime import datetime, timezone
import json
import os
import re
import logging
import traceback
from urllib.parse import urlsplit


def log_exception(message, *args):
    logging.error('%s\n%s', message % args if args else message, sanitize(traceback.format_exc()))


def sanitize(value):
    if isinstance(value, dict):
        return {str(k): ('[REDACTED]' if re.search(
            r'password|passwd|cookie|authorization|csrf|token|session.?id|^details$', str(k), re.I)
            else sanitize(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value[:100]]
    if isinstance(value, str):
        def url(match):
            try:
                parsed = urlsplit(match.group())
                return f'{parsed.scheme}://{parsed.hostname or ""}{parsed.path}'
            except ValueError:
                return '[URL]'
        value = re.sub(r'https?://[^\s<>"\x27]+', url, value)
        value = re.sub(r'(?i)((?:password|passwd|csrftoken|token|sessionid|uisessionid|authorization)\s*[:=]\s*)[^\s,;]+',
                       r'\1[REDACTED]', value)
        return value[:24000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return f'<{type(value).__name__}>'


class WarehouseJournal:
    def __init__(self, stream, batch_id):
        self.stream, self.batch_id, self.sequence = stream, batch_id, 0

    def __call__(self, entry):
        self.sequence += 1
        record = {'schema_version': 2, 'batch_id': self.batch_id, 'sequence': self.sequence,
                  'at': datetime.now(timezone.utc).isoformat(), **sanitize(entry)}
        self.stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

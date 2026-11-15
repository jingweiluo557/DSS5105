"""Self-declared record attribution, separate from access-key authorization."""
from contextvars import ContextVar
from urllib.parse import unquote

record_author = ContextVar('record_author', default='')


def clean_author(value):
    return ' '.join(unquote(value).split())[:100]

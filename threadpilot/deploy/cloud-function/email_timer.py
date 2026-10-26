"""Invoke every minute; backend uses business time, durable claims and idempotency."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

def main_handler(event, context):
    origin = os.environ['BACKEND_ORIGIN'].rstrip('/')
    if urlsplit(origin).scheme != 'https':
        raise ValueError('BACKEND_ORIGIN must use HTTPS')
    request = Request(origin + '/api/internal/email/run', data=b'', method='POST',
        headers={'Authorization': 'Bearer ' + os.environ['SCHEDULER_TOKEN']})
    try:
        with urlopen(request, timeout=290) as response:
            return json.load(response)
    except Exception:
        raise RuntimeError('Email timer failed; check backend logs. Do not manually resend unknown deliveries.') from None

main = main_handler

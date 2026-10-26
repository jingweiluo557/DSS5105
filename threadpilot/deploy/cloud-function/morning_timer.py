"""Event function: daily at 07:00 Asia/Shanghai; handler index.main_handler."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

def main_handler(event, context):
    origin = os.environ['BACKEND_ORIGIN'].rstrip('/')
    if urlsplit(origin).scheme != 'https':
        raise ValueError('BACKEND_ORIGIN must use HTTPS')
    request = Request(origin + '/api/internal/briefings/run', data=b'', method='POST',
                      headers={'Authorization': 'Bearer ' + os.environ['SCHEDULER_TOKEN']})
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
        if result.get('status') not in ('completed', 'already_saved', 'already_running'):
            raise ValueError('Schedule timezone mismatch or unexpected response')
        return result
    except Exception:
        raise RuntimeError('Morning briefing trigger failed; check backend logs and trigger timezone') from None

main = main_handler

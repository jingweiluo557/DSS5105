"""Deploy separately as an event function, handler timer.main_handler."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main_handler(event, context):
    origin = os.environ['BACKEND_ORIGIN'].rstrip('/')
    if urlsplit(origin).scheme != 'https':
        raise ValueError('BACKEND_ORIGIN must use HTTPS')
    token = os.environ['SCHEDULER_TOKEN']
    request = Request(origin + '/api/internal/reminders/run', data=b'', method='POST',
                      headers={'Authorization': 'Bearer ' + token})
    try:
        with urlopen(request, timeout=90) as response:
            result = json.load(response)
        if result.get('status') not in ('completed', 'already_running'):
            raise ValueError('Unexpected scheduler result')
        return result
    except Exception:
        raise RuntimeError('Reminder trigger failed; inspect backend logs and network settings') from None

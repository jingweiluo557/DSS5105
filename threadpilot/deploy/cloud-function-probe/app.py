"""Python 3.11 HTTP function connectivity probe, not the production backend."""
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

import pymysql

LOCK = threading.Lock()
EXPECTED_DATABASE = 'dss5105-track1-i7gxvcy5k7ef5ac9b'


def check_database():
    url = urlsplit(os.environ['AI_DATABASE_URL'])
    database = unquote(url.path.lstrip('/'))
    if url.scheme != 'mysql+pymysql' or database != EXPECTED_DATABASE:
        raise ValueError('Unexpected database configuration')
    connection = pymysql.connect(
        host=url.hostname, port=url.port or 3306,
        user=unquote(url.username or ''), password=unquote(url.password or ''),
        database=database, charset='utf8mb4', connect_timeout=10,
        read_timeout=15, write_timeout=15,
    )
    try:
        with connection.cursor() as cursor:
            counts = {}
            for table in ('orders', 'production_log', 'workshops'):
                cursor.execute(f'SELECT COUNT(*) FROM `{table}`')
                counts[table] = cursor.fetchone()[0]
        return {'ok': True, 'rows': counts}
    finally:
        connection.close()


def check_model():
    base = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    if urlsplit(base).scheme != 'https':
        raise ValueError('Model base URL must use HTTPS')
    model = os.environ.get('OPENAI_MODEL', 'gpt-4.1')
    style = os.environ.get('INTENT_API_STYLE', 'responses')
    if style == 'responses':
        endpoint = '/responses'
        body = {'model': model, 'input': 'Reply with the single word OK.', 'max_output_tokens': 32}
    elif style == 'chat_completions':
        endpoint = '/chat/completions'
        body = {'model': model, 'messages': [{'role': 'user', 'content': 'Reply with the single word OK.'}], 'max_tokens': 32}
    else:
        raise ValueError('Unsupported API style')
    request = Request(base + endpoint, data=json.dumps(body).encode(), method='POST',
                      headers={'Content-Type': 'application/json',
                               'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']})
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if style == 'responses':
        has_answer = any(part.get('text') for item in result.get('output', [])
                         for part in item.get('content', []) if part.get('type') == 'output_text')
    else:
        has_answer = any(item.get('message', {}).get('content') for item in result.get('choices', []))
    return {'ok': bool(has_answer), 'received_answer': bool(has_answer)}


def safe_check(function):
    try:
        return function()
    except Exception as error:
        # Do not expose exception strings, SQL, credentials or provider replies.
        code = getattr(error, 'code', None)
        if code is None and error.args and isinstance(error.args[0], int):
            code = error.args[0]
        return {'ok': False, 'error_type': type(error).__name__, 'code': code}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path not in ('/', '/health'):
            return self.reply(404, {'error': 'not_found'})
        self.reply(200, {'status': 'ok', 'service': 'threadpilot-cloud-function-probe'})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ('/verify/database', '/verify/model'):
            return self.reply(404, {'error': 'not_found'})
        token = os.environ.get('DATA_API_TOKEN', '')
        supplied = self.headers.get('Authorization', '')
        if not token or not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
            return self.reply(401, {'error': 'unauthorized'})
        if not LOCK.acquire(blocking=False):
            return self.reply(429, {'error': 'probe_busy'})
        try:
            result = safe_check(check_database if path.endswith('/database') else check_model)
            self.reply(200 if result['ok'] else 502, result)
        finally:
            LOCK.release()


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '9000'))), Handler).serve_forever()

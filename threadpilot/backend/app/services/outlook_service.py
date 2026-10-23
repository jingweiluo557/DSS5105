"""Single-owner Outlook connection. Tokens and message bodies are encrypted at rest.

Transactions serialize MSAL cache updates across workers. Database mode uses the
shared SQL store; local mode uses SQLite on persistent disk.
"""
import hashlib
import json
import secrets
import re
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx
import msal
import requests
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

SCOPES = ['https://graph.microsoft.com/Mail.Send']


class OutlookService:
    def __init__(self, settings):
        self.settings = settings

    def missing(self):
        return [name.upper() for name in ('outlook_client_id', 'outlook_client_secret', 'outlook_encryption_key')
                if not self._value(name)]

    def _value(self, name):
        value = getattr(self.settings, name)
        return value.get_secret_value() if hasattr(value, 'get_secret_value') else value

    def cipher(self):
        if self.missing():
            raise HTTPException(503, 'Missing configuration: ' + ', '.join(self.missing()))
        uri = urlsplit(self.settings.outlook_redirect_uri)
        if (uri.scheme != 'https' and not (uri.scheme == 'http' and uri.hostname == 'localhost')) or uri.path != '/api/outlook/callback' or uri.query or uri.fragment or uri.username:
            raise HTTPException(503, 'Invalid OUTLOOK_REDIRECT_URI configuration.')
        try:
            return Fernet(self._value('outlook_encryption_key').encode())
        except (ValueError, TypeError):
            raise HTTPException(503, 'Invalid OUTLOOK_ENCRYPTION_KEY.') from None

    def pack(self, value):
        return self.cipher().encrypt(json.dumps(value).encode()).decode()

    def unpack(self, value):
        try:
            return json.loads(self.cipher().decrypt(value.encode()))
        except (InvalidToken, ValueError):
            raise HTTPException(503, 'Outlook storage cannot be decrypted; restore its encryption key.') from None

    @contextmanager
    def db(self):
        self.cipher()
        if self.settings.workflow_storage == 'database':
            from ..cloud_state import shared_store
            with shared_store(self.settings) as db:
                yield db
            return
        path = self.settings.outlook_store
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=35)
        db.row_factory = sqlite3.Row
        try:
            db.execute('CREATE TABLE IF NOT EXISTS vault (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sends (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, db, name, default=None):
        row = db.execute('SELECT value FROM vault WHERE name=?', (name,)).fetchone()
        return self.unpack(row[0]) if row else default

    def put(self, db, name, value):
        db.execute('INSERT OR REPLACE INTO vault VALUES (?, ?)', (name, self.pack(value)))

    def client(self, db):
        cache = msal.SerializableTokenCache()
        stored = self.get(db, 'cache')
        if stored:
            cache.deserialize(stored)
        client = msal.ConfidentialClientApplication(
            self.settings.outlook_client_id, authority=self.settings.outlook_authority,
            client_credential=self._value('outlook_client_secret'), token_cache=cache,
            timeout=15, enable_pii_log=False)
        return client, cache

    def status(self):
        missing = self.missing()
        if missing:
            return {'configured': False, 'missing': missing, 'connected': False}
        with self.db() as db:
            account = self.get(db, 'account')
        return {'configured': True, 'missing': [], 'connected': bool(account),
                'account': account.get('username', '') if account else None,
                'redirect_uri': self.settings.outlook_redirect_uri}

    def begin(self):
        binding = secrets.token_urlsafe(32)
        with self.db() as db:
            client, _ = self.client(db)
            flow = client.initiate_auth_code_flow(SCOPES, redirect_uri=self.settings.outlook_redirect_uri,
                                                  prompt='select_account')
            # A single pending connection prevents an older login overwriting a newer one.
            self.put(db, 'flow', {'flow': flow, 'binding': hashlib.sha256(binding.encode()).hexdigest(),
                                  'expires': time.time() + 600})
        return flow['auth_uri'], binding

    def finish(self, params, binding):
        with self.db() as db:
            pending = self.get(db, 'flow')
            if (not pending or pending['expires'] < time.time() or not binding
                    or not secrets.compare_digest(pending['binding'], hashlib.sha256(binding.encode()).hexdigest())
                    or not secrets.compare_digest(pending['flow']['state'], params.get('state', ''))):
                raise HTTPException(400, 'Authorization expired or browser/state mismatch. Connect again.')
            db.execute("DELETE FROM vault WHERE name='flow'")
            # Consume once even if Microsoft rejects the code or the user cancels.
            db.commit()
            db.execute('BEGIN IMMEDIATE')
            client, cache = self.client(db)
            try:
                result = client.acquire_token_by_auth_code_flow(pending['flow'], params)
            except ValueError:
                raise HTTPException(400, 'Invalid authorization response. Connect again.') from None
            if 'access_token' not in result:
                raise HTTPException(400, 'Microsoft authorization failed or was cancelled. Check credentials and reconnect.')
            claims = result.get('id_token_claims', {})
            if claims.get('tid') != '9188040d-6c67-4c5b-b112-36a304b66dad':
                raise HTTPException(400, 'A personal Microsoft account is required.')
            accounts = client.get_accounts()
            account = next((a for a in accounts if a.get('local_account_id') == claims.get('oid')), None)
            if not account:
                raise HTTPException(400, 'Microsoft account could not be identified. Reconnect.')
            self.put(db, 'cache', cache.serialize())
            self.put(db, 'account', account)

    def access_token(self):
        with self.db() as db:
            account = self.get(db, 'account')
            if not account:
                raise HTTPException(409, 'Connect your Outlook account first.')
            client, cache = self.client(db)
            result = client.acquire_token_silent_with_error(SCOPES, account=account)
            self.put(db, 'cache', cache.serialize())
        if not result or 'access_token' not in result:
            raise HTTPException(409, 'Outlook authorization needs renewal. Connect again.')
        return result['access_token']

    def disconnect(self):
        with self.db() as db:
            db.execute("DELETE FROM vault WHERE name IN ('cache', 'account', 'flow')")

    def send(self, message_id, payload):
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.db() as db:
            row = db.execute('SELECT * FROM sends WHERE id=?', (message_id,)).fetchone()
            if row:
                if row['fingerprint'] != fingerprint:
                    raise HTTPException(409, 'This message ID already belongs to different content.')
                return {'id': message_id, 'status': row['status'], 'diagnostic': self.get(db, 'send:' + message_id)}
        # Token failures occur before claiming a send, so renewal can safely be retried.
        token = self.access_token()
        with self.db() as db:
            inserted = db.execute('INSERT OR IGNORE INTO sends VALUES (?,?,?,?,?)',
                                  (message_id, fingerprint, self.pack(payload), 'submitting', time.time())).rowcount
            if not inserted:
                row = db.execute('SELECT * FROM sends WHERE id=?', (message_id,)).fetchone()
                if row['fingerprint'] != fingerprint:
                    raise HTTPException(409, 'This message ID already belongs to different content.')
                return {'id': message_id, 'status': row['status'], 'diagnostic': self.get(db, 'send:' + message_id)}
        message = {'subject': payload['subject'], 'body': {'contentType': 'Text', 'content': payload['body']},
                   'toRecipients': [{'emailAddress': {'address': address}} for address in payload['to']]}
        diagnostic = {}
        try:
            response = httpx.post('https://graph.microsoft.com/v1.0/me/sendMail',
                                  headers={'Authorization': 'Bearer ' + token},
                                  json={'message': message, 'saveToSentItems': True}, timeout=25,
                                  follow_redirects=False)
            status = 'accepted' if response.status_code == 202 else ('unknown' if response.status_code >= 500 else 'rejected')
            diagnostic['http_status'] = response.status_code
            diagnostic['request_id'] = response.headers.get('request-id', '')[:100]
            if response.status_code != 202:
                try:
                    error = response.json().get('error', {})
                except (ValueError, AttributeError):
                    error = {}
                if isinstance(error, dict):
                    code = error.get('code', '')
                    if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', code):
                        diagnostic['code'] = code
                    message = error.get('message', '')
                    if isinstance(message, str):
                        for secret in (token, self._value('outlook_client_secret')):
                            if secret:
                                message = message.replace(secret, '[redacted]')
                        message = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [redacted]', message)
                        diagnostic['message'] = message[:1000]
                diagnostic['retry_after'] = response.headers.get('Retry-After', '')[:40]
        except httpx.HTTPError:
            status = 'unknown'
            diagnostic = {'code': 'NETWORK_RESULT_UNKNOWN'}
        with self.db() as db:
            db.execute('UPDATE sends SET status=? WHERE id=?', (status, message_id))
            self.put(db, 'send:' + message_id, diagnostic)
        return {'id': message_id, 'status': status, 'diagnostic': diagnostic}

    def history(self):
        with self.db() as db:
            return [{**{k: r[k] for k in ('id', 'status', 'created')}, **self.unpack(r['payload']),
                     'diagnostic': self.get(db, 'send:' + r['id'])}
                    for r in db.execute('SELECT * FROM sends ORDER BY created DESC LIMIT 50').fetchall()]


def network_error_guard(operation):
    try:
        return operation()
    except (requests.RequestException, httpx.HTTPError):
        raise HTTPException(502, 'Microsoft connection unavailable. Please retry later.') from None

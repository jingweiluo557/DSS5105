import importlib.util
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('probe', Path(__file__).with_name('app.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.server = probe.ThreadingHTTPServer(('127.0.0.1', 0), probe.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_health_does_not_call_dependencies(self):
        with patch.object(probe, 'check_database') as db, patch.object(probe, 'check_model') as model:
            with urlopen(self.base + '/health') as response:
                self.assertEqual(json.load(response)['status'], 'ok')
            db.assert_not_called()
            model.assert_not_called()

    def test_missing_token_cannot_invoke_model(self):
        with patch.dict(probe.os.environ, {'DATA_API_TOKEN': 'test-secret'}), patch.object(probe, 'check_model') as model:
            with self.assertRaises(HTTPError) as result:
                urlopen(Request(self.base + '/verify/model', data=b'', method='POST'))
            self.assertEqual(result.exception.code, 401)
            result.exception.close()
            model.assert_not_called()

    def test_authenticated_database_route(self):
        with patch.dict(probe.os.environ, {'DATA_API_TOKEN': 'test-secret'}), patch.object(probe, 'check_database', return_value={'ok': True, 'rows': {'orders': 120}}):
            request = Request(self.base + '/verify/database', data=b'', headers={'Authorization': 'Bearer test-secret'})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)['rows']['orders'], 120)

    def test_error_does_not_leak_message(self):
        def fail():
            raise ValueError('private-password')
        self.assertNotIn('private-password', json.dumps(probe.safe_check(fail)))


if __name__ == '__main__':
    unittest.main()

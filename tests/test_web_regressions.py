"""Exercise malformed requests and runtime model configuration over real HTTP."""

import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from starter_kit import loomq_web


class WebRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), loomq_web.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def post(self, path, payload, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("POST", path, json.dumps(payload),
                               headers=headers or {"Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_runtime_model_configuration_returns_status_without_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            status, payload = self.post("/api/agent-key", {
                "base_url": "http://127.0.0.1:12345/v1",
                "api_key": "local-test-key",
                "model": "local-model",
            })
            self.assertEqual(status, 200)
            self.assertTrue(payload["configured"])
            self.assertNotIn("local-test-key", json.dumps(payload))
            self.assertTrue(loomq_web.llm_configured())

    def test_json_body_must_be_an_object(self):
        for payload in (None, [], "text", 12, True):
            with self.subTest(payload=payload):
                status, data = self.post("/api/run", payload)
                self.assertEqual(status, 400)
                self.assertFalse(data["ok"])

    def test_configuration_is_validated_before_mutating_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for invalid in (123, [], {}, True):
                with self.subTest(invalid=invalid):
                    status, _ = self.post("/api/agent-key", {
                        "base_url": "http://127.0.0.1:12345/v1", "api_key": invalid,
                    })
                    self.assertEqual(status, 400)
                    self.assertNotIn("LOOMQ_LLM_BASE_URL", os.environ)

    def test_non_integer_shots_are_not_coerced(self):
        qasm = "OPENQASM 2.0; qreg q[1]; creg c[1]; measure q -> c;"
        for shots in (True, 1.5, [], {}, None):
            with self.subTest(shots=shots):
                status, _ = self.post("/api/run", {"qasm": qasm, "shots": shots})
                self.assertEqual(status, 400)

    def test_non_json_content_type_is_rejected(self):
        status, _ = self.post("/api/agent-key", {}, {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)

    def test_invalid_body_length_closes_connection(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("POST", "/api/run", b"{}", headers={
                "Content-Length": "-1", "Content-Type": "application/json",
            })
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            self.assertTrue(response.will_close)
            self.assertFalse(json.loads(response.read())["ok"])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

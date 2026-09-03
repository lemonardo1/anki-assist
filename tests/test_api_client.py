import importlib.util
import json
import pathlib
import sys
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("api_client", ROOT / "api_client.py")
api_client = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = api_client
SPEC.loader.exec_module(api_client)


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class ApiClientTests(unittest.TestCase):
    def test_extracts_nested_output_text(self):
        body = {
            "output": [
                {"type": "reasoning"},
                {"type": "message", "content": [{"type": "output_text", "text": "안녕"}]},
            ]
        }
        self.assertEqual(api_client.extract_output_text(body), "안녕")

    def test_request_does_not_store_response(self):
        with patch.object(
            api_client.urllib.request,
            "urlopen",
            return_value=FakeResponse({"id": "resp_1", "output_text": "답"}),
        ) as urlopen:
            result = api_client.create_response(
                api_key="secret",
                model="gpt-test",
                instructions="help",
                input_items=[{"role": "user", "content": "question"}],
            )
        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(sent["store"])
        self.assertEqual(result.text, "답")

    def test_parses_fenced_edit_json_and_filters_unknown_fields(self):
        summary, updates = api_client.parse_edit_proposal(
            '```json\n{"summary":"정리", "updates":{"Front":"새 값", "Bad":"x"}}\n```',
            {"Front", "Back"},
        )
        self.assertEqual(summary, "정리")
        self.assertEqual(updates, {"Front": "새 값"})


if __name__ == "__main__":
    unittest.main()

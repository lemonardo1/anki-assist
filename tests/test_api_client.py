import importlib.util
import json
import pathlib
import sys
import threading
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("api_client", ROOT / "api_client.py")
api_client = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = api_client
SPEC.loader.exec_module(api_client)

FORMATTING_SPEC = importlib.util.spec_from_file_location("formatting", ROOT / "formatting.py")
formatting = importlib.util.module_from_spec(FORMATTING_SPEC)
assert FORMATTING_SPEC and FORMATTING_SPEC.loader
sys.modules[FORMATTING_SPEC.name] = formatting
FORMATTING_SPEC.loader.exec_module(formatting)


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class FakeStreamResponse:
    def __init__(self, events):
        self.lines = []
        for event in events:
            self.lines.extend([f"data: {json.dumps(event)}\n".encode(), b"\n"])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)


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

    def test_streams_deltas_and_returns_usage(self):
        events = [
            {"type": "response.output_text.delta", "delta": "안"},
            {"type": "response.output_text.delta", "delta": "녕"},
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_2",
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                },
            },
        ]
        deltas = []
        with patch.object(
            api_client.urllib.request,
            "urlopen",
            return_value=FakeStreamResponse(events),
        ) as urlopen:
            result = api_client.create_streaming_response(
                api_key="secret",
                model="gpt-test",
                instructions="help",
                input_items=[{"role": "user", "content": "question"}],
                on_delta=deltas.append,
            )
        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertTrue(sent["stream"])
        self.assertFalse(sent["store"])
        self.assertEqual(deltas, ["안", "녕"])
        self.assertEqual(result.text, "안녕")
        self.assertEqual(result.total_tokens, 12)

    def test_stream_can_be_cancelled(self):
        cancelled = threading.Event()
        cancelled.set()
        events = [{"type": "response.output_text.delta", "delta": "ignored"}]
        with patch.object(
            api_client.urllib.request,
            "urlopen",
            return_value=FakeStreamResponse(events),
        ):
            with self.assertRaises(api_client.ResponseCancelled):
                api_client.create_streaming_response(
                    api_key="secret",
                    model="gpt-test",
                    instructions="help",
                    input_items=[],
                    on_delta=lambda _delta: None,
                    cancel_event=cancelled,
                )

    def test_friendly_api_errors(self):
        self.assertIn("API 키", api_client._friendly_http_error(401, "invalid"))
        self.assertIn("한도", api_client._friendly_http_error(429, "limited"))
        self.assertIn("일시적인 오류", api_client._friendly_http_error(503, "down"))
        self.assertIn("detail", api_client._friendly_http_error(400, "detail"))

    def test_parses_fenced_edit_json_and_filters_unknown_fields(self):
        summary, updates = api_client.parse_edit_proposal(
            '```json\n{"summary":"정리", "updates":{"Front":"새 값", "Bad":"x"}}\n```',
            {"Front", "Back"},
        )
        self.assertEqual(summary, "정리")
        self.assertEqual(updates, {"Front": "새 값"})

    def test_rich_text_escapes_html_and_formats_basic_markdown(self):
        rendered = formatting.safe_rich_text('<script>x</script> **핵심** `CDK4/6`')
        self.assertNotIn("<script>", rendered)
        self.assertIn("<b>핵심</b>", rendered)
        self.assertIn("<code>CDK4/6</code>", rendered)


if __name__ == "__main__":
    unittest.main()

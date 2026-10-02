import json
import unittest
from types import SimpleNamespace

from council_v2.bundle import build_bundle
from council_v2.seats import (SEAT_OUTPUT_SCHEMA, AnthropicSeat, MockSeat, OpenAICompatibleSeat, make_output,
                              validate_seat_output, SeatOutputError)
from tests.helpers import FACULTY, FIXTURES, vec

GOOD = vec(9, 9, 8, 9, 10, 8, 9)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeAnthropic:
    """Stands in for anthropic.Anthropic(); returns an SDK-shaped Message."""

    def __init__(self, *, text=None, model="claude-opus-5-5", stop_reason="end_turn", stop_details=None):
        content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)] if text is not None else []
        resp = SimpleNamespace(
            id="msg_01TEST", model=model, stop_reason=stop_reason, stop_details=stop_details,
            usage=SimpleNamespace(input_tokens=1234, output_tokens=567), content=content,
            _request_id="req_01TEST", type="message", role="assistant",
        )
        self.messages = FakeMessages(resp)


_BUNDLE = []


def bundle():
    if not _BUNDLE:
        _BUNDLE.append(build_bundle("tiny-repo", faculty_root=FACULTY, profile_path=FIXTURES / "tiny_repo" / "README.md",
                                    evidence_manifest={"artifact_count": 1, "artifacts": [{"kind": "code", "path": "src/app.py", "sha256": "ab" * 32}], "files": []}))
    return _BUNDLE[0]


class Schema(unittest.TestCase):
    def test_seat_cannot_write_overall_or_verdict(self):
        props = SEAT_OUTPUT_SCHEMA["properties"]
        self.assertNotIn("overall_score", props)
        self.assertNotIn("verdict", props)
        out = make_output(GOOD)
        out["overall_score"] = 9.9
        with self.assertRaises(SeatOutputError):
            validate_seat_output(out)

    def test_score_range_and_type(self):
        out = make_output(GOOD)
        out["criterion_scores"]["placement_fit"]["score"] = 11
        with self.assertRaises(SeatOutputError):
            validate_seat_output(out)
        out["criterion_scores"]["placement_fit"]["score"] = True
        with self.assertRaises(SeatOutputError):
            validate_seat_output(out)

    def test_schema_uses_enum_not_min_max(self):
        s = SEAT_OUTPUT_SCHEMA["properties"]["criterion_scores"]["properties"]["body_of_work_depth"]["properties"]["score"]
        self.assertEqual(s["enum"], list(range(11)))
        self.assertNotIn("minimum", json.dumps(SEAT_OUTPUT_SCHEMA))


class Anthropic(unittest.TestCase):
    def test_request_shape_and_recorded_provenance(self):
        fake = FakeAnthropic(text=json.dumps(make_output(GOOD, evidence=["admission/RUBRIC.md", "src/app.py"])))
        r = AnthropicSeat("anthropic", client=fake).score(bundle())
        self.assertEqual(r.status, "ok", r.error)
        call = fake.messages.calls[0]
        self.assertEqual(call["model"], "claude-opus-5-5")
        self.assertEqual(call["thinking"], {"type": "adaptive"})
        self.assertEqual(call["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(call["output_config"]["format"]["schema"], SEAT_OUTPUT_SCHEMA)
        self.assertIn("effort", call["output_config"])
        for forbidden in ("tool_choice", "tools", "temperature", "top_p", "top_k"):
            self.assertNotIn(forbidden, call)
        self.assertEqual(call["messages"][0]["content"], bundle().text)
        self.assertEqual((r.model_from_response, r.response_id, r.request_id), ("claude-opus-5-5", "msg_01TEST", "req_01TEST"))
        self.assertEqual(r.usage["input_tokens"], 1234)
        self.assertEqual(r.stop_reason, "end_turn")
        self.assertEqual(r.scores, GOOD)
        self.assertEqual(r.unresolved_citations, {})

    def test_model_recorded_from_response_not_from_request(self):
        fake = FakeAnthropic(text=json.dumps(make_output(GOOD)), model="claude-opus-5-5-served-variant")
        r = AnthropicSeat("anthropic", client=fake).score(bundle())
        self.assertEqual(r.model_requested, "claude-opus-5-5")
        self.assertEqual(r.model_from_response, "claude-opus-5-5-served-variant")

    def test_refusal_is_a_null_seat_with_stop_details(self):
        fake = FakeAnthropic(text=None, stop_reason="refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": "x"})
        r = AnthropicSeat("anthropic", client=fake).score(bundle())
        self.assertEqual(r.status, "null")
        self.assertEqual(r.error["type"], "refusal")
        self.assertEqual(r.stop_details["category"], "cyber")
        self.assertEqual(r.request_id, "req_01TEST")

    def test_truncation_and_bad_json_are_null(self):
        r = AnthropicSeat("anthropic", client=FakeAnthropic(text="{", stop_reason="max_tokens")).score(bundle())
        self.assertEqual((r.status, r.error["type"]), ("null", "truncated"))
        r = AnthropicSeat("anthropic", client=FakeAnthropic(text="not json")).score(bundle())
        self.assertEqual((r.status, r.error["type"]), ("null", "JSONDecodeError"))

    def test_unresolved_citations_are_recorded(self):
        fake = FakeAnthropic(text=json.dumps(make_output(GOOD, evidence=["https://example.com/deploys"])))
        r = AnthropicSeat("anthropic", client=fake).score(bundle())
        self.assertEqual(r.status, "ok")
        self.assertEqual(len(r.unresolved_citations), 7)

    def test_live_disabled_without_client(self):
        r = AnthropicSeat("anthropic").score(bundle())  # no client, no --live, no env
        self.assertEqual(r.status, "null")
        self.assertEqual(r.error["type"], "LiveCallsDisabled")


class OpenAICompatible(unittest.TestCase):
    def test_to_confirm_refuses(self):
        s = OpenAICompatibleSeat("longctx", "[TO CONFIRM]", endpoint="[TO CONFIRM]", model="[TO CONFIRM]", api_key_env="[TO CONFIRM]")
        r = s.score(bundle())
        self.assertEqual((r.status, r.error["type"]), ("null", "SeatNotConfigured"))

    def test_fake_transport(self):
        seen = {}

        def transport(url, headers, body, timeout):
            seen["payload"] = json.loads(body)
            data = {"id": "cmpl-1", "model": "served-model-7", "usage": {"prompt_tokens": 10},
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(make_output(GOOD))}}]}
            return 200, {"X-Request-Id": "rq-9"}, json.dumps(data).encode()

        s = OpenAICompatibleSeat("velocity", "prov", endpoint="https://example.invalid/v1/chat/completions",
                                 model="requested-model", api_key_env="PROV_KEY", transport=transport)
        r = s.score(bundle())
        self.assertEqual(r.status, "ok", r.error)
        self.assertEqual((r.model_from_response, r.request_id, r.response_id), ("served-model-7", "rq-9", "cmpl-1"))
        self.assertEqual(seen["payload"]["response_format"]["type"], "json_schema")
        self.assertEqual(seen["payload"]["messages"][1]["content"], bundle().text)

    def test_http_error_is_null_with_raw(self):
        s = OpenAICompatibleSeat("velocity", "prov", endpoint="https://example.invalid", model="m", api_key_env="K",
                                 transport=lambda *a: (429, {}, b'{"error":"rate limited"}'))
        r = s.score(bundle())
        self.assertEqual((r.status, r.error["status"]), ("null", 429))
        self.assertEqual(r.raw_response, {"error": "rate limited"})


class Mock(unittest.TestCase):
    def test_mock_is_deterministic(self):
        b = bundle()
        a1 = MockSeat("anthropic", scores=GOOD).score(b)
        a2 = MockSeat("anthropic", scores=GOOD).score(b)
        self.assertEqual((a1.response_id, a1.scores), (a2.response_id, a2.scores))
        self.assertTrue(a1.mock)


if __name__ == "__main__":
    unittest.main()

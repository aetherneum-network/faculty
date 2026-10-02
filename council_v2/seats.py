"""Seat adapters behind one interface: ``score(bundle) -> SeatResult``.

Council v2 rule 1 (review 2026-09-30 §3): "Il modello dà i voti, il codice fa
i conti. Ogni seggio restituisce i sette punteggi con output strutturato."

* The output schema has NO ``overall_score`` and NO ``verdict`` field: a
  seat cannot write them.  ``scoring.py`` computes both.
* Every criterion carries ``evidence``: bundle paths or SHA-256 values the
  rationale relies on (rule 2, "deve citare un percorso o uno SHA per ogni
  affermazione").  Unresolvable citations are recorded, not silently dropped.
* The system prompt is identical for every seat and does not tell the model
  its own name: the model id recorded is the one returned by the API
  (``response.model``), never one the model repeats.
* ``BaseSeat.score`` never raises: any failure becomes a ``null`` result with
  the error and a log, which ``record.py`` writes to disk (rule 7).
* No adapter can reach the network unless the process runs with
  ``AETHERNEUM_COUNCIL_LIVE=1`` AND the seat was built with
  ``allow_live=True`` (CLI ``--live``).  Tests inject fake clients/transports.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Mapping, Protocol

from . import CRITERIA_ORDER
from .bundle import Bundle

TO_CONFIRM = "[TO CONFIRM]"
LIVE_ENV = "AETHERNEUM_COUNCIL_LIVE"

# --------------------------------------------------------------------------
# Structured output schema (shared by every provider)
# --------------------------------------------------------------------------

_CRITERION_SCHEMA = {
    "type": "object",
    "properties": {
        # enum instead of minimum/maximum: numerical constraints are not
        # supported by Anthropic structured outputs.
        "score": {"type": "integer", "enum": list(range(11))},
        "rationale": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "rationale", "evidence"],
    "additionalProperties": False,
}

SEAT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "criterion_scores": {
            "type": "object",
            "properties": {k: _CRITERION_SCHEMA for k in CRITERIA_ORDER},
            "required": list(CRITERIA_ORDER),
            "additionalProperties": False,
        },
        "revisions_required": {"type": "array", "items": {"type": "string"}},
        "dissent": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "notes": {"type": "string"},
    },
    "required": ["criterion_scores", "revisions_required", "dissent", "notes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are one voting seat of the Aetherneum admission Council (Council v2).
You receive one bundle. Every seat receives the identical bundle.

Score the candidate on the seven criteria of the rubric in the bundle
(admission/RUBRIC.md), each an integer from 0 to 10, with a rationale of one
to three sentences.

Rules:
- Judge evidence, not prose. The profile and intake are claims. The
  evidence_manifest and executor_result are what exists. A claim with no
  artifact behind it is not evidence.
- For every criterion, list in "evidence" the bundle paths or SHA-256 values
  your rationale relies on. If there is nothing to cite, return an empty list
  and say so in the rationale.
- Do not compute an overall score and do not state a verdict. The Council's
  code computes both from your seven scores, applying the rubric's weights,
  thresholds and vetoes.
- Use "revisions_required" for concrete, checkable changes. Use "dissent"
  only for a disagreement with the rubric or the process itself; otherwise
  null.
- Reply with the JSON object required by the response format and nothing else.
"""

PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


class SeatOutputError(ValueError):
    pass


def validate_seat_output(data: Any) -> dict[str, Any]:
    """Client-side validation of the structured output (no jsonschema dependency)."""
    if not isinstance(data, dict):
        raise SeatOutputError("output is not a JSON object")
    required = set(SEAT_OUTPUT_SCHEMA["required"])
    missing = required - set(data)
    extra = set(data) - set(SEAT_OUTPUT_SCHEMA["properties"])
    if missing:
        raise SeatOutputError(f"missing fields: {sorted(missing)}")
    if extra:
        raise SeatOutputError(f"fields not allowed (the seat may not write them): {sorted(extra)}")
    cs = data["criterion_scores"]
    if not isinstance(cs, dict) or set(cs) != set(CRITERIA_ORDER):
        raise SeatOutputError("criterion_scores must contain exactly the seven criteria")
    for k in CRITERIA_ORDER:
        c = cs[k]
        if not isinstance(c, dict) or set(c) != {"score", "rationale", "evidence"}:
            raise SeatOutputError(f"{k}: needs exactly score, rationale, evidence")
        s = c["score"]
        if isinstance(s, bool) or not isinstance(s, int) or not 0 <= s <= 10:
            raise SeatOutputError(f"{k}: score must be an integer 0-10")
        if not isinstance(c["rationale"], str) or not c["rationale"].strip():
            raise SeatOutputError(f"{k}: empty rationale")
        if not isinstance(c["evidence"], list) or not all(isinstance(e, str) for e in c["evidence"]):
            raise SeatOutputError(f"{k}: evidence must be a list of strings")
    if not isinstance(data["revisions_required"], list) or not all(isinstance(r, str) for r in data["revisions_required"]):
        raise SeatOutputError("revisions_required must be a list of strings")
    if data["dissent"] is not None and not isinstance(data["dissent"], str):
        raise SeatOutputError("dissent must be a string or null")
    if not isinstance(data["notes"], str):
        raise SeatOutputError("notes must be a string")
    return data


# --------------------------------------------------------------------------
# Result type and interface
# --------------------------------------------------------------------------


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class SeatResult:
    seat_id: str
    provider: str
    status: str  # "ok" | "null"
    model_requested: str
    model_from_response: str | None = None
    request_id: str | None = None
    response_id: str | None = None
    output: dict[str, Any] | None = None  # validated structured output
    unresolved_citations: dict[str, list[str]] = field(default_factory=dict)
    usage: dict[str, Any] | None = None
    stop_reason: str | None = None
    stop_details: dict[str, Any] | None = None
    raw_response: Any = None
    params: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    log: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    mock: bool = False

    @property
    def scores(self) -> dict[str, int] | None:
        if not self.output:
            return None
        return {k: self.output["criterion_scores"][k]["score"] for k in CRITERIA_ORDER}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Seat(Protocol):
    seat_id: str
    provider: str
    model: str

    def score(self, bundle: Bundle) -> SeatResult: ...


class LiveCallsDisabled(RuntimeError):
    pass


class SeatNotConfigured(RuntimeError):
    pass


def _check_live(allow_live: bool) -> None:
    if not allow_live or os.environ.get(LIVE_ENV) != "1":
        raise LiveCallsDisabled(
            f"live model calls are disabled (need --live and {LIVE_ENV}=1); "
            "use MockSeat or inject a client/transport"
        )


def _plain(obj: Any) -> Any:
    """Best-effort conversion of SDK objects to JSON-compatible data."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Mapping):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    for attr in ("to_dict", "model_dump"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return _plain(fn())
            except Exception:  # pragma: no cover
                pass
    if hasattr(obj, "__dict__"):
        return {k: _plain(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return repr(obj)


_HEX = set("0123456789abcdef")


def _resolves(citation: str, citable: set[str]) -> bool:
    """A citation resolves if it names a bundle path (optionally with an anchor
    or line suffix, e.g. ``admission/RUBRIC.md#automatic-veto``) or is a hex
    prefix (>= 7 chars) of a SHA present in the bundle."""
    c = citation.strip()
    if c in citable:
        return True
    if len(c) >= 7 and set(c.lower()) <= _HEX:
        return any(x.startswith(c.lower()) for x in citable if set(x) <= _HEX)
    return any(c.startswith(p) for p in citable if "/" in p or "." in p)


def _citations(output: dict[str, Any], bundle: Bundle) -> dict[str, list[str]]:
    citable = bundle.citable()
    bad: dict[str, list[str]] = {}
    for k in CRITERIA_ORDER:
        for e in output["criterion_scores"][k]["evidence"]:
            if not _resolves(e, citable):
                bad.setdefault(k, []).append(e)
    return bad


class BaseSeat:
    """Template: subclasses implement ``_call``; ``score`` handles failures."""

    seat_id: str
    provider: str
    model: str

    def __init__(self, seat_id: str, provider: str, model: str):
        self.seat_id, self.provider, self.model = seat_id, provider, model

    def params(self) -> dict[str, Any]:  # pragma: no cover - overridden
        return {"model": self.model}

    def _call(self, bundle: Bundle, result: SeatResult) -> None:  # pragma: no cover
        raise NotImplementedError

    def score(self, bundle: Bundle) -> SeatResult:
        res = SeatResult(self.seat_id, self.provider, "null", self.model, params=self.params(), started_at=_now())
        res.log.append(f"{_now()} seat {self.seat_id} start bundle_sha256={bundle.sha256}")
        try:
            self._call(bundle, res)
            if res.output is not None:
                res.status = "ok"
                res.unresolved_citations = _citations(res.output, bundle)
                if res.unresolved_citations:
                    res.log.append(f"{_now()} unresolved citations: {res.unresolved_citations}")
        except Exception as e:  # noqa: BLE001 - every failure becomes a null seat
            res.status = "null"
            res.output = None
            if res.error is None:
                res.error = {"type": type(e).__name__, "message": str(e)[:2000]}
            res.log.append(f"{_now()} ERROR {type(e).__name__}: {str(e)[:500]}")
        res.finished_at = _now()
        res.log.append(f"{_now()} seat {self.seat_id} end status={res.status}")
        return res


# --------------------------------------------------------------------------
# Anthropic (official SDK)
# --------------------------------------------------------------------------


class AnthropicSeat(BaseSeat):
    """Anthropic seat via the official ``anthropic`` SDK.

    Request: ``claude-opus-5-5``, ``thinking={"type": "adaptive"}``,
    ``output_config={"effort": ..., "format": {"type": "json_schema", ...}}``.
    No ``tool_choice`` (forced tool use is rejected by this model and not
    needed: structured output returns the JSON directly).  No ``temperature``:
    sampling parameters are not accepted by ``claude-opus-5-5``.

    Refusal fallbacks (the ``fallbacks`` request parameter) are OFF by
    default: a seat is a declared model, and a silent re-route to another
    model would change who voted.  A refusal therefore produces a null seat
    whose record carries ``stop_reason: "refusal"`` and ``stop_details``.
    Set ``refusal_fallbacks`` in council/council.json only by Faculty decision;
    ``response.model`` is recorded either way.
    """

    def __init__(self, seat_id: str = "anthropic", *, model: str = "claude-opus-5-5", effort: str = "high",
                 max_tokens: int = 16000, client: Any = None, allow_live: bool = False,
                 timeout_s: float = 600.0):
        super().__init__(seat_id, "anthropic", model)
        self.effort, self.max_tokens, self.client = effort, max_tokens, client
        self.allow_live, self.timeout_s = allow_live, timeout_s

    def params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema_sha256": _schema_sha()}},
            "tool_choice": None,
            "temperature": None,
            "refusal_fallbacks": None,
            "system_prompt_sha256": PROMPT_SHA256,
            "sdk": "anthropic (official Python SDK)",
        }

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        _check_live(self.allow_live)
        import anthropic  # lazy: not needed offline

        self.client = anthropic.Anthropic(timeout=self.timeout_s)
        return self.client

    def _call(self, bundle: Bundle, res: SeatResult) -> None:
        client = self._client()
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": bundle.text}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": SEAT_OUTPUT_SCHEMA},
            },
        )
        res.raw_response = _plain(response)
        res.model_from_response = getattr(response, "model", None)
        res.response_id = getattr(response, "id", None)
        res.request_id = getattr(response, "_request_id", None)
        res.usage = _plain(getattr(response, "usage", None))
        res.stop_reason = getattr(response, "stop_reason", None)
        res.stop_details = _plain(getattr(response, "stop_details", None))
        res.log.append(f"{_now()} response id={res.response_id} request_id={res.request_id} model={res.model_from_response} stop_reason={res.stop_reason}")
        if res.stop_reason == "refusal":
            res.error = {"type": "refusal", "message": "model declined (stop_reason=refusal)", "stop_details": res.stop_details}
            raise RuntimeError("refusal")
        if res.stop_reason == "max_tokens":
            res.error = {"type": "truncated", "message": "stop_reason=max_tokens; output incomplete"}
            raise RuntimeError("truncated")
        texts = [b.text for b in getattr(response, "content", []) if getattr(b, "type", None) == "text"]
        if not texts:
            raise SeatOutputError("no text block in response")
        res.output = validate_seat_output(json.loads(texts[0]))


def _schema_sha() -> str:
    return hashlib.sha256(json.dumps(SEAT_OUTPUT_SCHEMA, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------
# OpenAI-compatible HTTP (other providers) — endpoints/models [TO CONFIRM]
# --------------------------------------------------------------------------

Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, dict[str, str], bytes]]


def urllib_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - https endpoints from council.json
            return r.status, dict(r.headers.items()), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()), e.read()


class OpenAICompatibleSeat(BaseSeat):
    """Minimal chat-completions adapter for non-Anthropic seats.

    Endpoint, model, API-key env var and JSON-schema support are per provider
    and marked ``[TO CONFIRM]`` in council/council.json; a seat whose
    configuration still contains ``[TO CONFIRM]`` refuses to run live and
    produces a null record.
    """

    def __init__(self, seat_id: str, provider: str, *, endpoint: str, model: str, api_key_env: str,
                 temperature: float | None = 0.0, max_tokens: int = 8000, transport: Transport | None = None,
                 allow_live: bool = False, timeout_s: float = 600.0, json_schema_mode: bool = True):
        super().__init__(seat_id, provider, model)
        self.endpoint, self.api_key_env = endpoint, api_key_env
        self.temperature, self.max_tokens = temperature, max_tokens
        self.transport, self.allow_live, self.timeout_s = transport, allow_live, timeout_s
        self.json_schema_mode = json_schema_mode

    def params(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": "json_schema" if self.json_schema_mode else "json_object",
            "system_prompt_sha256": PROMPT_SHA256,
            "schema_sha256": _schema_sha(),
        }

    def _call(self, bundle: Bundle, res: SeatResult) -> None:
        if TO_CONFIRM in (self.endpoint + self.model + self.api_key_env):
            raise SeatNotConfigured(f"seat {self.seat_id} still has {TO_CONFIRM} endpoint/model/key")
        transport = self.transport
        if transport is None:
            _check_live(self.allow_live)
            transport = urllib_transport
        key = os.environ.get(self.api_key_env, "") if self.transport is None else "injected-test-transport"
        if not key:
            raise SeatNotConfigured(f"missing env {self.api_key_env}")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": bundle.text}],
            "max_tokens": self.max_tokens,
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        payload["response_format"] = (
            {"type": "json_schema", "json_schema": {"name": "council_seat_review", "strict": True, "schema": SEAT_OUTPUT_SCHEMA}}
            if self.json_schema_mode else {"type": "json_object"}
        )
        status, headers, body = transport(
            self.endpoint,
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json.dumps(payload).encode("utf-8"),
            self.timeout_s,
        )
        lower = {k.lower(): v for k, v in headers.items()}
        res.request_id = lower.get("x-request-id") or lower.get("request-id")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            data = {"_unparseable_body": body[:2000].decode("utf-8", "replace")}
        res.raw_response = data
        if status != 200:
            res.error = {"type": "http_error", "status": status, "message": str(data)[:1000]}
            raise RuntimeError(f"HTTP {status}")
        res.model_from_response = data.get("model")
        res.response_id = data.get("id")
        res.usage = data.get("usage")
        choice = (data.get("choices") or [{}])[0]
        res.stop_reason = choice.get("finish_reason")
        res.log.append(f"{_now()} response id={res.response_id} request_id={res.request_id} model={res.model_from_response} finish_reason={res.stop_reason}")
        if res.stop_reason == "length":
            res.error = {"type": "truncated", "message": "finish_reason=length"}
            raise RuntimeError("truncated")
        content = (choice.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise SeatOutputError("no message content")
        res.output = validate_seat_output(json.loads(content))


# --------------------------------------------------------------------------
# Mock seat (tests, dry runs, calibration drills)
# --------------------------------------------------------------------------


def make_output(scores: Mapping[str, int], *, evidence: list[str] | None = None, notes: str = "mock") -> dict[str, Any]:
    ev = evidence if evidence is not None else ["admission/RUBRIC.md"]
    return {
        "criterion_scores": {
            k: {"score": int(scores[k]), "rationale": f"mock rationale for {k}", "evidence": list(ev)}
            for k in CRITERIA_ORDER
        },
        "revisions_required": [],
        "dissent": None,
        "notes": notes,
    }


class MockSeat(BaseSeat):
    """Deterministic seat.  ``scores`` is a dict or ``callable(bundle) -> dict``.

    ``fail`` makes the seat raise (to exercise null records).  ``output``
    overrides the full structured output (to exercise validation).
    """

    def __init__(self, seat_id: str, provider: str = "mock", *, scores: Any = None, model: str = "mock-model-1",
                 fail: str | None = None, output: dict[str, Any] | None = None):
        super().__init__(seat_id, provider, model)
        self._scores, self._fail, self._output = scores, fail, output

    def params(self) -> dict[str, Any]:
        return {"model": self.model, "mock": True, "system_prompt_sha256": PROMPT_SHA256}

    def _call(self, bundle: Bundle, res: SeatResult) -> None:
        res.mock = True
        if self._fail:
            raise RuntimeError(self._fail)
        scores = self._scores(bundle) if callable(self._scores) else self._scores
        output = self._output if self._output is not None else make_output(scores or {k: 5 for k in CRITERIA_ORDER})
        res.model_from_response = self.model
        res.response_id = f"mock_{hashlib.sha256((self.seat_id + bundle.sha256).encode()).hexdigest()[:16]}"
        res.request_id = f"mockreq_{res.response_id[5:]}"
        res.usage = {"input_tokens": len(bundle.text) // 4, "output_tokens": 0}
        res.stop_reason = "end_turn"
        res.raw_response = {"mock": True, "output": output}
        res.output = validate_seat_output(json.loads(json.dumps(output)))

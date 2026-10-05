import base64
import json
import logging
import time
import traceback

import httpx
import pytest

from local_typeless.openrouter import NetworkError, OpenRouterClient, OpenRouterError, RequestTimeout


def make_client(handler) -> OpenRouterClient:
    return OpenRouterClient(api_key="test-key", transport=httpx.MockTransport(handler))


def sse(*events: dict | str) -> bytes:
    lines = [": OPENROUTER PROCESSING", ""]
    for ev in events:
        lines += [f"data: {ev if isinstance(ev, str) else json.dumps(ev)}", ""]
    return "\n".join(lines).encode()


def test_chat_streams_and_collects_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        body = sse(
            {"model": "m", "provider": "P", "choices": [{"delta": {"content": "你好"}}]},
            {"model": "m", "provider": "P", "choices": [{"delta": {"content": "，世界"}}]},
            {"model": "m", "choices": [], "usage": {"cost": 0.0001}},
            "[DONE]",
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    deltas = []
    with make_client(handler) as c:
        res = c.chat(
            [{"role": "user", "content": "x"}], "m", extra={"reasoning": {"enabled": False}}, on_delta=deltas.append
        )

    assert res.text == "你好，世界"
    assert deltas == ["你好", "，世界"]
    assert res.cost_usd == 0.0001
    assert res.provider == "P"
    assert res.ttft_s is not None
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["stream"] is True
    assert seen["body"]["reasoning"] == {"enabled": False}


def test_chat_raises_on_midstream_error():
    def handler(request):
        return httpx.Response(200, content=sse({"error": {"message": "overloaded"}}))

    with make_client(handler) as c, pytest.raises(OpenRouterError, match="provider error"):
        c.chat([], "m")


def test_http_error_is_wrapped():
    with (
        make_client(lambda r: httpx.Response(429, text="rate limited")) as c,
        pytest.raises(OpenRouterError, match="429"),
    ):
        c.chat([], "m")


class _BreaksMidStream(httpx.SyncByteStream):
    def __init__(self, first: bytes):
        self.first = first

    def __iter__(self):
        yield self.first
        raise httpx.ReadError("SSL: UNEXPECTED_EOF_WHILE_READING")


def test_chat_retries_once_when_connection_dies_before_output():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadError("SSL: UNEXPECTED_EOF_WHILE_READING")
        return httpx.Response(200, content=sse({"choices": [{"delta": {"content": "ok"}}]}, "[DONE]"))

    with make_client(handler) as c:
        assert c.chat([], "m").text == "ok"
    assert len(calls) == 2


def test_chat_does_not_retry_after_partial_output():
    calls = []

    def handler(request):
        calls.append(1)
        first = sse({"choices": [{"delta": {"content": "半"}}]})
        return httpx.Response(200, stream=_BreaksMidStream(first))

    with make_client(handler) as c, pytest.raises(NetworkError):
        c.chat([], "m")
    assert len(calls) == 1


class _KeepAliveOnly(httpx.SyncByteStream):
    """A provider that never produces text: only OpenRouter keep-alive comments."""

    def __iter__(self):
        for _ in range(50):
            time.sleep(0.02)
            yield b": OPENROUTER PROCESSING\n\n"


def test_chat_gives_up_when_no_text_arrives_in_time():
    with make_client(lambda r: httpx.Response(200, stream=_KeepAliveOnly())) as c, pytest.raises(RequestTimeout):
        c.chat([], "m", first_token_timeout_s=0.2)


def test_timeouts_are_not_retried_on_the_same_model():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow provider")

    with make_client(handler) as c:
        with pytest.raises(RequestTimeout):
            c.transcribe(b"a", "ogg", "openai/gpt-transcribe", timeout_s=1)
        with pytest.raises(RequestTimeout):
            c.chat([], "m", first_token_timeout_s=1)
    assert len(calls) == 2  # one per call, no retry


def test_transcribe_retries_once_on_network_error():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("proxy reset")
        return httpx.Response(200, json={"text": "ok"})

    with make_client(handler) as c:
        assert c.transcribe(b"a", "ogg", "openai/gpt-transcribe").text == "ok"
    assert len(calls) == 2


def test_transcribe_puts_hints_under_provider_options_for_gpt_transcribe():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": " 你好 ", "usage": {"seconds": 1.5, "cost": 0.0001}})

    with make_client(handler) as c:
        t = c.transcribe(b"abc", "ogg", "openai/gpt-transcribe", keywords=["Claude Code"], languages=["zh-cn"])

    assert t.text == "你好"
    assert t.audio_seconds == 1.5
    body = seen["body"]
    assert body["input_audio"] == {"data": base64.b64encode(b"abc").decode(), "format": "ogg"}
    assert body["provider"] == {"options": {"openai": {"keywords": ["Claude Code"], "languages": ["zh-cn"]}}}


def test_transcribe_merges_routing_prefs_with_hint_options():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "hi"})

    with make_client(handler) as c:
        c.transcribe(b"a", "ogg", "openai/gpt-transcribe", keywords=["k"], provider={"data_collection": "deny"})

    assert seen["body"]["provider"] == {"data_collection": "deny", "options": {"openai": {"keywords": ["k"]}}}


def test_transcribe_sends_no_hints_to_models_that_ignore_them():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"text": "hi"})

    with make_client(handler) as c:
        c.transcribe(b"abc", "ogg", "microsoft/mai-transcribe-2", keywords=["x"])

    assert "provider" not in seen["body"]


def test_account_balance_from_credits_and_key_usage():
    def handler(req):
        if req.url.path.endswith("/credits"):
            return httpx.Response(200, json={"data": {"total_credits": 175, "total_usage": 170.35}})
        return httpx.Response(200, json={"data": {"usage_daily": 0.03, "usage_weekly": 0.8, "usage_monthly": 3.65}})

    a = make_client(handler).account()
    assert round(a.balance, 2) == 4.65 and a.key_month == 3.65 and a.key_limit_remaining is None


def test_account_without_credits_access_still_reports_key_usage():
    def handler(req):
        if req.url.path.endswith("/credits"):
            return httpx.Response(403, json={"error": {"message": "forbidden"}})
        return httpx.Response(200, json={"data": {"usage_daily": 0.5}})

    a = make_client(handler).account()
    assert a.balance is None and a.key_today == 0.5


SECRET_MARKER = "SYNTHETIC_RESPONSE_SECRET_DO_NOT_LOG"


def call_endpoint(client: OpenRouterClient, endpoint: str):
    if endpoint == "transcribe":
        return client.transcribe(b"synthetic-audio", "ogg", "m")
    if endpoint == "chat":
        return client.chat([], "m")
    return getattr(client, endpoint)()


def assert_private_error(error: BaseException) -> None:
    assert SECRET_MARKER not in "".join(traceback.format_exception(error))
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert SECRET_MARKER not in str(current)
        assert SECRET_MARKER not in repr(current)
        pending.extend(e for e in (current.__cause__, current.__context__) if e is not None)


@pytest.mark.parametrize("endpoint", ["check", "account", "transcribe", "chat"])
@pytest.mark.parametrize("response_kind", ["http-json", "http-html", "html-200", "json-error-200"])
def test_response_errors_never_expose_server_content(endpoint, response_kind, caplog):
    status = 502 if response_kind.startswith("http-") else 200

    def handler(request):
        if "html" in response_kind:
            return httpx.Response(status, text=f"<html>{SECRET_MARKER}</html>", headers={"content-type": "text/html"})
        return httpx.Response(
            status, json={"error": {"code": 429, "message": SECRET_MARKER, "metadata": {"raw": SECRET_MARKER}}}
        )

    with make_client(handler) as client, pytest.raises(OpenRouterError) as caught:
        call_endpoint(client, endpoint)
    error = caught.value
    assert_private_error(error)
    assert error.status_code == status
    assert f"HTTP {status}" in str(error)
    assert "/" in str(error)
    if response_kind == "json-error-200":
        assert error.code == 429
    logging.getLogger(__name__).warning("synthetic failure", exc_info=error)
    assert SECRET_MARKER not in caplog.text


@pytest.mark.parametrize("code", [429, "429", SECRET_MARKER, {"raw": SECRET_MARKER}, 123456789, True])
@pytest.mark.parametrize("partial_output", [False, True])
def test_stream_error_codes_are_bounded_and_body_is_private(code, partial_output):
    calls, deltas = [], []

    def handler(request):
        calls.append(request)
        events = [{"choices": [{"delta": {"content": "partial"}}]}] if partial_output else []
        events.append({"error": {"code": code, "message": SECRET_MARKER, "metadata": {"raw": SECRET_MARKER}}})
        return httpx.Response(200, content=sse(*events))

    with make_client(handler) as client, pytest.raises(OpenRouterError) as caught:
        client.chat([], "m", on_delta=deltas.append)
    assert_private_error(caught.value)
    assert caught.value.status_code == 200
    assert caught.value.code == (429 if code in (429, "429") else None)
    assert len(calls) == 1
    assert deltas == (["partial"] if partial_output else [])


@pytest.mark.parametrize("endpoint", ["check", "account", "transcribe", "chat"])
@pytest.mark.parametrize("payload", [b'{"' + SECRET_MARKER.encode(), b'"' + SECRET_MARKER.encode() + b'\xff"'])
def test_malformed_json_has_no_sensitive_parser_exception_chain(endpoint, payload):
    body = b"data: " + payload + b"\n\n" if endpoint == "chat" else payload
    with make_client(lambda r: httpx.Response(200, content=body)) as client, pytest.raises(OpenRouterError) as caught:
        call_endpoint(client, endpoint)
    assert_private_error(caught.value)
    assert caught.value.status_code == 200


@pytest.mark.parametrize("endpoint", ["check", "account", "transcribe", "chat"])
@pytest.mark.parametrize("failure", [httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError])
def test_transport_exceptions_cannot_reintroduce_server_content(endpoint, failure):
    def handler(request):
        raise failure(SECRET_MARKER)

    with make_client(handler) as client, pytest.raises(OpenRouterError) as caught:
        call_endpoint(client, endpoint)
    assert_private_error(caught.value)


def test_fallback_logging_keeps_status_without_response_body(caplog):
    from local_typeless import pipeline
    from local_typeless.config import Config

    cfg = Config()
    calls = []

    def handler(request):
        calls.append(json.loads(request.content)["model"])
        if len(calls) == 1:
            return httpx.Response(400, json={"error": {"message": SECRET_MARKER}})
        return httpx.Response(200, json={"text": "synthetic result"})

    with make_client(handler) as client:
        result = pipeline.transcribe(client, cfg, b"synthetic-audio", "ogg")
    assert result.text == "synthetic result"
    assert calls == [cfg.asr.model, cfg.asr.fallback_model]
    assert cfg.app.log_text is False
    assert "HTTP 400" in caplog.text
    assert SECRET_MARKER not in caplog.text

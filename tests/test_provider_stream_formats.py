"""Exercise saved-provider SDK parsers, not mock Pydantic's normalized output.

Only the HTTPS response bytes are synthetic. Factory selection, both pinned
HTTP clients, vendor event parsing and Decision validation are the real code.
"""
import json
import time
from unittest.mock import Mock, patch

import pytest
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.usage import UsageLimits

from leadzen.ai import build_model
from leadzen.chat.engine import Decision
from tests.test_chat import chat_client, post, turn


TEXT = "Hello world 🌍"
PROVIDERS = ["openai", "openai_compatible", "groq", "anthropic", "google", "mistral"]


def frame(data, event=None):
    prefix = f"event: {event}\r\n" if event else ""
    return (prefix + "data: " + json.dumps(data, ensure_ascii=False) + "\r\n\r\n").encode()


def output_tool(payload, provider):
    tools = payload["tools"]
    if provider == "anthropic":
        return tools[0]["name"]
    if provider == "google":
        return tools[0]["functionDeclarations"][0]["name"]
    return tools[0]["function"]["name"]


def stream_frames(provider, name):
    if provider == "anthropic":
        events = [
            ("message_start", {"message": {"id": "msg_synthetic", "type": "message", "role": "assistant", "model": "synthetic-model", "content": [], "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 8, "output_tokens": 1}}}),
            ("content_block_start", {"index": 0, "content_block": {"type": "tool_use", "id": "call_synthetic", "name": name, "input": {}}}),
            ("content_block_delta", {"index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"tool":"answer","text":"Hello'}}),
            ("content_block_delta", {"index": 0, "delta": {"type": "input_json_delta", "partial_json": " world 🌍"}}),
            ("content_block_delta", {"index": 0, "delta": {"type": "input_json_delta", "partial_json": '\",\"arguments\":{}}'}}),
            ("content_block_stop", {"index": 0}),
            ("message_delta", {"delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 20}}),
            ("message_stop", {}),
        ]
        return [frame({"type": event, **body}, event) for event, body in events]
    if provider == "google":
        # Gemini supplies complete function arguments, even on its SSE route.
        # Do not pretend those arguments are OpenAI-style incremental strings.
        return [
            frame({"candidates": [{"index": 0, "content": {"role": "model", "parts": [{"functionCall": {"name": name, "args": {"tool": "answer", "text": TEXT, "arguments": {}}}}]}}], "modelVersion": "synthetic-model"}),
            frame({"candidates": [{"index": 0, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 20, "totalTokenCount": 28}, "modelVersion": "synthetic-model"}),
        ]
    if provider == "mistral":
        # Mistral's adapter likewise receives a complete explicit tool call.
        deltas = [{"role": "assistant", "tool_calls": [{"id": "call_synthetic", "type": "function", "function": {"name": name, "arguments": json.dumps({"tool": "answer", "text": TEXT, "arguments": {}}, ensure_ascii=False)}}]}]
    else:
        deltas = [
            {"role": "assistant", "tool_calls": [{"index": 0, "id": "call_synthetic", "type": "function", "function": {"name": name, "arguments": '{"tool":"answer","text":"Hello'}}]},
            {"tool_calls": [{"index": 0, "function": {"arguments": " world 🌍"}}]},
            {"tool_calls": [{"index": 0, "function": {"arguments": '\",\"arguments\":{}}'}}]},
        ]
    chunks = [frame({"id": "chat_synthetic", "object": "chat.completion.chunk", "created": 1_700_000_000, "model": "synthetic-model", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}) for delta in deltas]
    chunks.append(frame({"id": "chat_synthetic", "object": "chat.completion.chunk", "created": 1_700_000_000, "model": "synthetic-model", "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 8, "completion_tokens": 20, "total_tokens": 28}}))
    chunks.append(b"data: [DONE]\r\n\r\n")
    return chunks


def prompted_frames(*, ending='\",\"arguments\":{}}', tool="answer"):
    deltas = [
        {"role": "assistant", "content": '{"tool":' + json.dumps(tool) + ',"text":"Hello'},
        {"content": " world 🌍"},
        {"content": ending},
        {},
    ]
    chunks = [frame({"id": "chat_synthetic", "object": "chat.completion.chunk", "created": 1_700_000_000, "model": "synthetic-model", "choices": [{"index": 0, "delta": delta, "finish_reason": "stop" if index == len(deltas) - 1 else None}]}) for index, delta in enumerate(deltas)]
    chunks.append(b"data: [DONE]\r\n\r\n")
    return chunks


class WireResponse:
    status = 200

    def __init__(self, chunks, delay=0):
        # Fragment both framing and a multi-byte UTF-8 character just as TCP can.
        fragmented = []
        for chunk in chunks:
            split = chunk.find("🌍".encode())
            split = split + 1 if split >= 0 else min(7, len(chunk))
            fragmented.extend([chunk[:split], chunk[split:]])
        self.chunks = iter(fragmented)
        self.eof = False
        self.delay = delay

    def getheaders(self):
        return [("content-type", "text/event-stream")]

    def read1(self, size):
        if self.delay:
            time.sleep(self.delay)
        try:
            return next(self.chunks)
        except StopIteration:
            self.eof = True
            return b""


@pytest.fixture
def wire(monkeypatch):
    monkeypatch.setenv("LEADZEN_LLM_HOSTS", "api.example.com")
    monkeypatch.delenv("LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS", raising=False)
    with patch("leadzen.ai.pinned_open") as opening, patch("leadzen.ai.pinned_request") as buffered, patch("leadzen.chat.engine.assert_action_access"), patch("leadzen.outreach.generation_guard"), patch("socket.socket.connect", side_effect=AssertionError("real network forbidden")):
        yield opening, buffered


@pytest.mark.parametrize("provider", PROVIDERS)
def test_native_provider_streams_normalize_to_validated_decisions(provider, wire):
    opening, buffered = wire
    connection = Mock()
    response = None
    request_payload = None

    def open_response(method, url, headers, content, host, **kwargs):
        nonlocal response, request_payload
        request_payload = json.loads(content)
        assert method == "POST" and host == "api.example.com"
        if provider == "google":
            assert ":streamGenerateContent?alt=sse" in url
        else:
            assert request_payload["stream"] is True
        response = WireResponse(stream_frames(provider, output_tool(request_payload, provider)))
        return connection, response

    opening.side_effect = open_response
    model = build_model(provider, "synthetic-model", "synthetic-key", "https://api.example.com/v1")
    agent = Agent(model, output_type=Decision, retries=0, model_settings={"max_tokens": 500})
    seen = []
    with agent.run_stream_sync("Give a short answer", usage_limits=UsageLimits(request_limit=1)) as result:
        for part in result.stream_output(debounce_by=None):
            if part.text:
                if not seen:
                    assert not response.eof  # First user-visible output precedes network EOF.
                seen.append(part.text)
        output = result.get_output()
    assert output == Decision(tool="answer", text=TEXT, arguments={})
    assert seen and seen[-1] == TEXT
    if provider in {"openai", "openai_compatible", "groq", "anthropic"}:
        assert any(text != TEXT for text in seen)
        assert all(TEXT.startswith(text) for text in seen)
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("provider", ["openai", "groq", "anthropic"])
def test_provider_error_event_is_not_retried_or_exposed_as_answer(provider, wire):
    opening, buffered = wire
    connection = Mock()
    payload = {"error": {"type": "invalid_request_error", "message": "Synthetic stream failed", "code": "synthetic_error"}}
    if provider == "anthropic":
        payload["type"] = "error"
    response = WireResponse([frame(payload, "error" if provider == "anthropic" else None)])
    opening.return_value = connection, response
    model = build_model(provider, "synthetic-model", "synthetic-key", "https://api.example.com/v1")
    agent = Agent(model, output_type=Decision, retries=0)
    with pytest.raises(ModelAPIError):
        with agent.run_stream_sync("Read-only answer", usage_limits=UsageLimits(request_limit=1)) as result:
            list(result.stream_output(debounce_by=None))
            result.get_output()
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("provider", PROVIDERS)
def test_empty_provider_stream_fails_without_starting_another_request(provider, wire):
    opening, buffered = wire
    connection = Mock()
    opening.return_value = connection, WireResponse([])
    model = build_model(provider, "synthetic-model", "synthetic-key", "https://api.example.com/v1")
    agent = Agent(model, output_type=Decision, retries=0)
    with pytest.raises(UnexpectedModelBehavior):
        with agent.run_stream_sync("Read-only answer", usage_limits=UsageLimits(request_limit=1)) as result:
            list(result.stream_output(debounce_by=None))
            result.get_output()
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("provider", ["openai", "groq", "anthropic"])
def test_truncated_structured_arguments_are_not_accepted_or_retried(provider, wire):
    opening, buffered = wire
    connection = Mock()

    def open_response(method, url, headers, content, host, **kwargs):
        chunks = stream_frames(provider, output_tool(json.loads(content), provider))
        # Network EOF arrives after an unclosed JSON string, before valid output.
        return connection, WireResponse(chunks[:4] if provider == "anthropic" else chunks[:2])

    opening.side_effect = open_response
    model = build_model(provider, "synthetic-model", "synthetic-key", "https://api.example.com/v1")
    agent = Agent(model, output_type=Decision, retries=0)
    with pytest.raises(UnexpectedModelBehavior):
        with agent.run_stream_sync("Read-only answer", usage_limits=UsageLimits(request_limit=1)) as result:
            list(result.stream_output(debounce_by=None))
            result.get_output()
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("provider,prompted", [("openai", False), ("groq", False), ("anthropic", False), ("openai_compatible", True)])
def test_stop_guard_during_vendor_stream_closes_without_retry(provider, prompted, wire):
    opening, buffered = wire
    connection = Mock()

    def open_response(method, url, headers, content, host, **kwargs):
        payload = json.loads(content)
        if prompted:
            assert not payload.get("tools")
            chunks = prompted_frames()
        else:
            chunks = stream_frames(provider, output_tool(payload, provider))
        return connection, WireResponse(chunks)

    opening.side_effect = open_response
    model = build_model(provider, "synthetic-model", "synthetic-key", "https://api.example.com/v1")
    agent = Agent(model, output_type=PromptedOutput(Decision) if prompted else Decision, retries=0)
    seen = []
    with patch("leadzen.chat.engine.assert_action_access") as guard:
        with pytest.raises(PermissionError, match="generation stopped"):
            with agent.run_stream_sync("Read-only answer", usage_limits=UsageLimits(request_limit=1)) as result:
                for part in result.stream_output(debounce_by=None):
                    if part.text:
                        seen.append(part.text)
                        # The next transport read sees the normal Stop/revocation
                        # boundary; neither the vendor SDK nor Agent may retry it.
                        guard.side_effect = PermissionError("generation stopped")
                result.get_output()
    assert seen and seen[0] != TEXT
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("prompted", [False, True])
@pytest.mark.parametrize("expire_initial_stream", [False, True])
def test_real_sdk_chunks_persist_and_use_existing_authenticated_sse(chat_client, wire, monkeypatch, prompted, expire_initial_stream):
    from types import SimpleNamespace
    from django.db.models import QuerySet
    from django.db.models.signals import post_save
    from leadzen.chat.engine import drive
    from leadzen.config.models import ChatMessage

    opening, buffered = wire
    connection = Mock()
    provider = "openai_compatible"  # Saved employee provider, not a model mock.
    # The real endpoint rotates at 20 seconds. Advance only its clock in the
    # expiry regression; SDK deadlines, auth expiry and provider bytes stay real.
    from leadzen.chat import views
    clock_offset = 0
    monkeypatch.setattr(views, "time", SimpleNamespace(monotonic=lambda: time.monotonic() + clock_offset, sleep=time.sleep))
    if prompted:
        monkeypatch.setenv("LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS", "api.example.com")

    def open_response(method, url, headers, content, host, **kwargs):
        nonlocal clock_offset
        if expire_initial_stream:
            clock_offset = 21
        payload = json.loads(content)
        if prompted:
            assert not payload.get("tools")
            chunks = prompted_frames()
        else:
            chunks = stream_frames(provider, output_tool(payload, provider))
        return connection, WireResponse(chunks, delay=0.14)

    opening.side_effect = open_response
    thread, run = turn(chat_client, "Give me a short greeting")
    stream = chat_client.get(f"/api/chat/threads/{thread}/stream")
    assert stream.status_code == 200
    assert stream["Content-Type"] == "text/event-stream"
    frames = iter(stream.streaming_content)
    assert b'"status": "queued"' in next(frames)
    stream_started = views.time.monotonic()
    progressive = []
    original_update = QuerySet.update

    def record_frame():
        nonlocal stream, frames, stream_started
        try:
            event = next(frames).decode()
        except StopIteration:
            # An unexpected early close still fails. A timed-out connection is
            # renewed as the dashboard does, without another model request.
            assert views.time.monotonic() - stream_started >= 20
            stream.close()
            stream = chat_client.get(f"/api/chat/threads/{thread}/stream")
            assert stream.status_code == 200
            frames = iter(stream.streaming_content)
            event = next(frames).decode()
            stream_started = views.time.monotonic()
        if event.startswith("data: "):
            progressive.append(event)

    def created_message(sender, instance, created, **kwargs):
        if created and str(instance.thread_id) == thread and instance.data.get("streaming"):
            record_frame()

    def record_updates(queryset, **kwargs):
        changed = original_update(queryset, **kwargs)
        if queryset.model is ChatMessage and "content" in kwargs and kwargs.get("data", {}).get("streaming") is True:
            record_frame()
        return changed

    post_save.connect(created_message, sender=ChatMessage, weak=False)
    try:
        with patch.object(QuerySet, "update", record_updates):
            drive(run)
            drive(run)  # Duplicate dispatch cannot call the provider again.
        terminal = b"".join(frames).decode()
    finally:
        post_save.disconnect(created_message, sender=ChatMessage)
        stream.close()
    assert progressive
    assert any('"content": "Hello"' in event for event in progressive)
    assert all('"streaming": true' in event for event in progressive)
    assert all(event.startswith("data: ") for event in progressive)
    assert '"status": "succeeded"' in terminal and '"streaming": false' in terminal
    assert "synthetic-secret-ai" not in "".join(progressive) + terminal
    detail = chat_client.get(f"/api/chat/threads/{thread}").json()
    assistant = [message for message in detail["messages"] if message["role"] == "assistant"]
    assert len(assistant) == 1 and assistant[0]["content"] == TEXT
    assert assistant[0]["data"]["streaming"] is False
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("invalid", [None, "truncated", "tool_name"])
def test_prompted_content_deltas_use_real_sdk_and_strict_final_validation(wire, invalid):
    opening, buffered = wire
    connection = Mock()
    chunks = prompted_frames(ending="" if invalid == "truncated" else '\",\"arguments\":{}}', tool="execute_shell" if invalid == "tool_name" else "answer")
    response = WireResponse(chunks)

    def open_response(method, url, headers, content, host, **kwargs):
        payload = json.loads(content)
        assert payload["stream"] is True and not payload.get("tools")
        return connection, response

    opening.side_effect = open_response
    model = build_model("openai_compatible", "synthetic-model", "synthetic-key", "https://api.example.com/v1")
    agent = Agent(model, output_type=PromptedOutput(Decision), retries=0)

    def consume():
        seen = []
        with agent.run_stream_sync("Read-only answer", usage_limits=UsageLimits(request_limit=1)) as result:
            for part in result.stream_output(debounce_by=None):
                if part.text:
                    if not seen:
                        assert not response.eof
                    seen.append(part.text)
            output = result.get_output()
        return seen, output

    if invalid:
        with pytest.raises(UnexpectedModelBehavior):
            consume()
    else:
        seen, output = consume()
        assert output == Decision(tool="answer", text=TEXT, arguments={})
        assert seen[0] == "Hello" and seen[-1] == TEXT
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("provider,hosts,prompted", [
    ("openai_compatible", None, False),
    ("openai_compatible", "api.example.com", True),
    ("openai_compatible", "other.example.com, api.example.com", True),
    ("openai_compatible", "example.com", False),
    ("openai_compatible", "*.example.com", False),
    ("openai_compatible", "child.api.example.com", False),
    ("openai", "api.example.com", False),
    ("anthropic", "api.example.com", False),
])
def test_chat_prompted_output_is_server_opt_in_for_exact_compatible_host(chat_client, wire, monkeypatch, provider, hosts, prompted):
    from leadzen.chat.engine import drive
    from leadzen.configuration import save_dashboard_settings

    opening, buffered = wire
    connection = Mock()
    if hosts is not None:
        monkeypatch.setenv("LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS", hosts)
    save_dashboard_settings({"provider": provider, "model": "synthetic-model", "base_url": "https://api.example.com/v1"}, llm_api_key="synthetic-secret-ai")

    def open_response(method, url, headers, content, host, **kwargs):
        payload = json.loads(content)
        if prompted:
            assert not payload.get("tools")
            chunks = prompted_frames()
        else:
            chunks = stream_frames(provider, output_tool(payload, provider))
        return connection, WireResponse(chunks)

    opening.side_effect = open_response
    thread, run = turn(chat_client, "Give me a short greeting")
    drive(run)
    saved = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert saved["run"]["status"] == "succeeded"
    assistants = [message for message in saved["messages"] if message["role"] == "assistant"]
    assert len(assistants) == 1 and assistants[0]["content"] == TEXT
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()


@pytest.mark.parametrize("content_type", ["application/json", "application/x-ndjson"])
def test_unsupported_compatible_stream_protocol_fails_safely_without_replay(chat_client, wire, content_type):
    from leadzen.chat.engine import drive
    opening, buffered = wire
    connection = Mock()
    response = WireResponse([b'{"text":"synthetic-secret-ai raw provider content"}\n'])
    response.getheaders = lambda: [("content-type", content_type)]
    opening.return_value = connection, response
    thread, run = turn(chat_client, "Give a short answer")
    with patch("leadzen.chat.engine.perform") as perform, patch("leadzen.chat.engine.prepare") as prepare:
        drive(run)
        drive(run)
    saved = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert saved["run"]["status"] == "failed"
    assistants = [message for message in saved["messages"] if message["role"] == "assistant"]
    assert len(assistants) == 1 and "raw provider content" not in assistants[0]["content"]
    assert "synthetic-secret-ai" not in json.dumps(saved)
    perform.assert_not_called()
    prepare.assert_not_called()
    opening.assert_called_once()
    buffered.assert_not_called()
    connection.close.assert_called()

"""Provider compatibility and pinned transport tests without external requests."""
from unittest.mock import patch

import pytest

from leadzen.ai import build_model, install_engine_adapters, pinned_request
from tests.test_chat import chat_client, turn


@pytest.mark.parametrize("provider", ["openai", "openai_compatible", "groq", "anthropic", "google", "mistral", "cohere"])
def test_all_saved_provider_factories_construct_without_network(provider, monkeypatch):
    monkeypatch.setenv("LEADZEN_LLM_HOSTS", "api.example.com")
    with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
        model = build_model(provider, "synthetic-model", "synthetic-key", "https://api.example.com/v1")
        assert model.model_name == "synthetic-model"


def test_engine_factory_patch_fixes_removed_openai_model(monkeypatch):
    from cold_outreach.core import llm as sender
    from openoutfind.core import llm as finder
    monkeypatch.setenv("LEADZEN_LLM_HOSTS", "api.example.com")
    original_sender, original_finder = sender._PROVIDER_BUILDERS.copy(), finder._PROVIDER_BUILDERS.copy()
    try:
        install_engine_adapters()
        with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            for child in (sender, finder):
                model = child.build_llm_model("openai_compatible:synthetic-model", "synthetic-key", "https://api.example.com/v1")
                assert model.model_name == "synthetic-model"
    finally:
        sender._PROVIDER_BUILDERS, finder._PROVIDER_BUILDERS = original_sender, original_finder


def test_transport_refuses_different_host_before_dns():
    with patch("leadzen.transports.public_socket") as dial:
        with pytest.raises(ValueError):
            pinned_request("POST", "https://evil.example/v1", {}, b"{}", "api.openai.com")
        dial.assert_not_called()


def test_revoked_worker_never_dials_ai():
    with patch("leadzen.workspaces.assert_worker_access", side_effect=PermissionError("revoked")), patch("leadzen.transports.public_socket") as dial:
        with pytest.raises(PermissionError):
            pinned_request("POST", "https://api.openai.com/v1/chat/completions", {}, b"{}", "api.openai.com")
        dial.assert_not_called()


@pytest.mark.parametrize("modern", [True, False])
def test_both_sdk_http_clients_use_the_pinned_transport(modern):
    import asyncio
    from leadzen.ai import http_client
    async def request():
        async with http_client("api.openai.com", modern=modern) as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", json={"model": "synthetic"})
            assert response.json() == {"ok": True}
    with patch("leadzen.ai.pinned_request", return_value=(200, [("content-type", "application/json")], b'{"ok":true}')) as pin:
        asyncio.run(request())
        pin.assert_called_once()


@pytest.mark.parametrize("modern", [True, False])
@pytest.mark.parametrize("failure", [None, "size", "revocation", "cancel"])
def test_streaming_yields_before_completion_and_closes_on_every_exit(modern, failure):
    import asyncio
    from unittest.mock import Mock
    from leadzen.ai import http_client
    connection = Mock()
    response = Mock(status=200)
    response.getheaders.return_value = [("content-type", "text/event-stream")]
    reads = iter([b'data: first\n\n', b'data: second\n\n', b''])
    response.read1.side_effect = lambda size: next(reads)
    async def request():
        async with http_client("api.openai.com", modern=modern) as client:
            async with client.stream("POST", "https://api.openai.com/v1/chat/completions", json={"stream": True}) as reply:
                iterator = reply.aiter_raw()
                assert await anext(iterator) == b'data: first\n\n'
                assert response.read1.call_count == 1  # The rest is still unread.
                if failure == "cancel":
                    await iterator.aclose()
                    return
                if failure == "size":
                    response.read1.side_effect = lambda size: b'x' * 2097153
                    with pytest.raises(ValueError, match="exceeded"):
                        await anext(iterator)
                elif failure == "revocation":
                    guard.side_effect = PermissionError("revoked")
                    with pytest.raises(PermissionError):
                        await anext(iterator)
                else:
                    assert await anext(iterator) == b'data: second\n\n'
                    with pytest.raises(StopAsyncIteration):
                        await anext(iterator)
    with patch("leadzen.ai.pinned_open", return_value=(connection, response)) as opening, patch("leadzen.ai.pinned_request") as buffered, patch("leadzen.chat.engine.assert_action_access") as guard, patch("leadzen.outreach.generation_guard"):
        asyncio.run(request())
        opening.assert_called_once()
        buffered.assert_not_called()
        connection.close.assert_called()


def test_stream_open_rejects_redirect_and_closes_socket():
    from unittest.mock import Mock
    connection = Mock()
    connection.getresponse.return_value.status = 302
    with patch("leadzen.ai.http.client.HTTPSConnection.__init__", return_value=None), patch("leadzen.ai.http.client.HTTPSConnection.request"), patch("leadzen.ai.http.client.HTTPSConnection.getresponse", return_value=connection.getresponse.return_value), patch("leadzen.ai.http.client.HTTPSConnection.close") as close:
        from leadzen.ai import pinned_open
        with pytest.raises(ValueError, match="redirected"):
            pinned_open("POST", "https://api.openai.com/v1/chat/completions", {}, b'{"stream":true}', "api.openai.com")
        close.assert_called_once()


@pytest.mark.parametrize("status", [200, 429, 500, "cancel"])
def test_cohere_buffered_answer_uses_real_sdk_once_and_persists_safely(chat_client, status):
    """The installed Cohere adapter cannot stream; choose buffering before I/O."""
    import json
    import uuid
    from pydantic_ai import Agent
    from leadzen.config.models import ChatRun
    from leadzen.configuration import save_dashboard_settings
    from leadzen.chat.engine import drive
    from tests.test_chat import post
    save_dashboard_settings({"provider": "cohere", "model": "command-r", "base_url": "https://api.cohere.com"}, llm_api_key="synthetic-secret-ai")
    thread, run = turn(chat_client, "Answer only: explain streaming briefly.")

    def response(method, url, headers, content, host, **kwargs):
        body = json.loads(content)
        assert url == "https://api.cohere.com/v2/chat"
        assert not body.get("stream")
        if status in {429, 500}:
            return status, [("content-type", "application/json"), ("retry-after", "0")], b'{"message":"synthetic-secret-ai provider error"}'
        tool = body["tools"][0]["function"]["name"]
        output = {"id": "synthetic-response", "finish_reason": "TOOL_CALL", "message": {"role": "assistant", "content": [], "tool_calls": [{"id": "synthetic-call", "type": "function", "function": {"name": tool, "arguments": json.dumps({"tool": "answer", "text": "One completed provider answer.", "arguments": {}})}}]}, "usage": {"billed_units": {"input_tokens": 10, "output_tokens": 10}, "tokens": {"input_tokens": 10, "output_tokens": 10}}}
        return 200, [("content-type", "application/json")], json.dumps(output).encode()

    actual_run_sync = Agent.run_sync
    def buffered_response(agent, *args, **kwargs):
        result = actual_run_sync(agent, *args, **kwargs)
        if status == "cancel":
            # Change the saved task on the owning DB thread immediately after
            # real SDK completion; a late answer cannot undo a Stop request.
            ChatRun.objects.filter(pk=run).update(cancel_requested=True)
        return result

    with patch("leadzen.ai.pinned_request", side_effect=response) as request, patch("leadzen.ai.pinned_open") as streaming, patch.object(Agent, "run_sync", buffered_response), patch("leadzen.chat.engine.prepare") as prepare, patch("leadzen.chat.engine.perform") as perform:
        drive(run)
        drive(run)  # Duplicate dispatch cannot repeat provider work.
        prepare.assert_not_called()
        perform.assert_not_called()
    request.assert_called_once()
    streaming.assert_not_called()
    saved = chat_client.get(f"/api/chat/threads/{thread}").json()
    assert saved["run"]["status"] == ("succeeded" if status == 200 else "cancelled" if status == "cancel" else "failed")
    assistants = [message for message in saved["messages"] if message["role"] == "assistant"]
    assert len(assistants) == 1
    assert not assistants[0]["data"].get("streaming")
    assert "synthetic-secret-ai" not in json.dumps(saved)
    if status == 200:
        assert assistants[0]["content"] == "One completed provider answer."
    if status == 500:
        # Reconnect/replay is inert; only a new employee request retries the model.
        path = f"/api/chat/threads/{thread}/messages"
        old_request = str(ChatRun.objects.get(pk=run).request_id)
        with patch("leadzen.chat.views.launch") as launch:
            replay = post(chat_client, path, {"content": "Answer only: explain streaming briefly.", "request_id": old_request})
            assert replay.json()["run"]["id"] == run
            launch.assert_not_called()
            retry = post(chat_client, path, {"content": "Try that answer again.", "request_id": str(uuid.uuid4())})
            assert retry.status_code == 202
            launch.assert_called_once()
        status = 200
        with patch("leadzen.ai.pinned_request", side_effect=response) as retried:
            drive(retry.json()["run"]["id"])
        retried.assert_called_once()
        final = chat_client.get(f"/api/chat/threads/{thread}").json()
        assert final["run"]["status"] == "succeeded"
        assert [m["content"] for m in final["messages"] if m["role"] == "assistant"] == [assistants[0]["content"], "One completed provider answer."]

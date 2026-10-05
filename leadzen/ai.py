"""Explicit provider factories with bounded, pinned HTTPS; no ambient credentials.

The adapter lives here, not in either installed outreach dependency. In particular,
new Pydantic AI releases call the chat-completions model OpenAIChatModel.
"""
import asyncio
import http.client
import importlib
import ssl
import json
import time
from urllib.parse import urlparse

from leadzen.configuration import SettingsError, _valid_url, approved_host

BASES = {"openai": "https://api.openai.com/v1", "groq": "https://api.groq.com", "anthropic": "https://api.anthropic.com", "google": "https://generativelanguage.googleapis.com", "mistral": "https://api.mistral.ai/v1", "cohere": "https://api.cohere.com"}


def pinned_open(method, url, headers, content, host, *, kind="LLM", timeout=40):
    from leadzen.transports import public_socket
    from leadzen.workspaces import assert_worker_access
    assert_worker_access()
    from leadzen.chat.engine import assert_action_access
    assert_action_access(reserve_model=kind == "LLM")
    if kind == "LLM":
        from leadzen.outreach import generation_guard
        generation_guard()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.port not in (None, 443) or parsed.username or parsed.password:
        raise SettingsError("AI request must stay on the approved HTTPS endpoint")
    if kind == "LLM":
        approved_host(host, "LLM")
    elif kind != "BETTERCONTACT" or host != "app.bettercontact.rocks":
        raise SettingsError("Unapproved lead-provider endpoint")
    if method not in ({"POST"} if kind == "LLM" else {"GET", "POST"}) or len(content) > 262144:
        raise SettingsError("AI request is not supported or is too large")

    class PinnedHTTPS(http.client.HTTPSConnection):
        def connect(self):
            sock = public_socket(self.host, 443, timeout)
            try:
                self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
                # DNS/TCP/TLS can block after the initial reservation. Recheck
                # authority before writing HTTP bytes without reserving again.
                assert_action_access()
                if kind == "LLM":
                    from leadzen.outreach import generation_guard
                    generation_guard()
            except Exception:
                (self.sock if self.sock is not None else sock).close()
                raise

    connection = PinnedHTTPS(host, timeout=timeout)
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        clean_headers = {key: value for key, value in headers.items() if key.lower() not in {"host", "content-length", "accept-encoding"}}
        connection.request(method, path, content, clean_headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise SettingsError("AI response redirected")
        return connection, response
    except PermissionError:
        connection.close()
        raise
    except (OSError, http.client.HTTPException):
        connection.close()
        raise SettingsError("AI provider could not be reached. Check Connections.") from None
    except BaseException:
        connection.close()
        raise


def response_headers(response):
    return [(key, value) for key, value in response.getheaders() if key.lower() not in {"content-encoding", "transfer-encoding", "content-length"}]


def pinned_request(method, url, headers, content, host, *, kind="LLM", timeout=40):
    deadline = time.monotonic() + timeout
    connection, response = pinned_open(method, url, headers, content, host, kind=kind, timeout=timeout)
    try:
        from leadzen.provider_io import read_response
        raw = read_response(connection, response, limit=2097152, deadline=deadline, description="AI")
        return response.status, response_headers(response), raw
    except (OSError, http.client.HTTPException):
        raise SettingsError("AI provider could not be reached. Check Connections.") from None
    finally:
        connection.close()


def http_client(host, *, modern=False, request_timeout=40):
    http = importlib.import_module("httpx2" if modern else "httpx")

    class Stream(http.AsyncByteStream):
        def __init__(self, connection, response):
            self.connection, self.response = connection, response
            self.size, self.deadline = 0, time.monotonic() + 90

        async def __aiter__(self):
            try:
                while True:
                    def read():
                        from leadzen.chat.engine import assert_action_access
                        from leadzen.outreach import generation_guard
                        assert_action_access()
                        generation_guard()
                        if time.monotonic() >= self.deadline:
                            raise SettingsError("AI streaming deadline exceeded")
                        return self.response.read1(8192)
                    chunk = await asyncio.to_thread(read)
                    if not chunk:
                        break
                    self.size += len(chunk)
                    if self.size > 2097152:
                        raise SettingsError("AI response exceeded the limit")
                    yield chunk
            finally:
                await self.aclose()

        async def aclose(self):
            self.connection.close()

    class Transport(http.AsyncBaseTransport):
        async def handle_async_request(self, request):
            content = await request.aread()
            try:
                stream_requested = json.loads(content).get("stream") is True
            except (ValueError, AttributeError):
                stream_requested = False
            stream_requested = stream_requested or "alt=sse" in str(request.url) or "text/event-stream" in request.headers.get("accept", "")
            if not stream_requested:
                status, headers, body = await asyncio.to_thread(pinned_request, request.method, str(request.url), dict(request.headers), content, host, timeout=request_timeout)
                return http.Response(status, headers=headers, content=body, request=request)
            opening = asyncio.create_task(asyncio.to_thread(pinned_open, request.method, str(request.url), dict(request.headers), content, host, timeout=request_timeout))
            try:
                connection, response = await asyncio.shield(opening)
            except asyncio.CancelledError:
                # A cancelled coroutine cannot orphan the pending socket opener.
                def close_late(task):
                    try:
                        task.result()[0].close()
                    except BaseException:
                        pass
                opening.add_done_callback(close_late)
                raise
            return http.Response(response.status, headers=response_headers(response), stream=Stream(connection, response), request=request)

    return http.AsyncClient(transport=Transport(), timeout=45, follow_redirects=False, trust_env=False)


def build_model(provider, model, api_key, base_url="", *, request_timeout=40):
    if not api_key or not model:
        raise SettingsError("Connect an AI model and API key first")
    url = _valid_url(base_url or BASES.get(provider, ""), "AI endpoint")
    if not url:
        raise SettingsError("An OpenAI-compatible Base URL is required")
    # The Groq SDK itself appends /openai/v1/chat/completions. Accept the
    # familiar compatibility base without accidentally doubling that path.
    if provider == "groq" and url.rstrip("/").endswith("/openai/v1"):
        url = url.rstrip("/")[:-len("/openai/v1")]
    host = urlparse(url).hostname
    if provider in {"openai", "openai_compatible"}:
        from openai import AsyncOpenAI
        from pydantic_ai.models import openai as models
        from pydantic_ai.providers.openai import OpenAIProvider
        model_class = getattr(models, "OpenAIChatModel", None) or getattr(models, "OpenAIModel")
        client = AsyncOpenAI(api_key=api_key, base_url=url, http_client=http_client(host, modern=True, request_timeout=request_timeout), max_retries=0)
        return model_class(model, provider=OpenAIProvider(openai_client=client))
    names = {"groq": ("Groq", False), "anthropic": ("Anthropic", True), "google": ("Google", True), "mistral": ("Mistral", True), "cohere": ("Cohere", False)}
    if provider not in names:
        raise SettingsError("Choose a supported AI provider")
    name, modern = names[provider]
    provider_class = getattr(importlib.import_module(f"pydantic_ai.providers.{provider}"), name + "Provider")
    model_class = getattr(importlib.import_module(f"pydantic_ai.models.{provider}"), name + "Model")
    options = {"api_key": api_key, "base_url": url, "http_client": http_client(host, modern=modern, request_timeout=request_timeout)}
    if provider == "google":
        from google.genai.types import HttpRetryOptions
        options["retry_options"] = HttpRetryOptions(attempts=1)
    if provider == "cohere":
        from cohere import AsyncClientV2
        options = {"cohere_client": AsyncClientV2(api_key=api_key, base_url=url, httpx_client=options["http_client"], max_retries=0)}
    adapter = provider_class(**options)
    # SDK retries multiply model budgets. Do not retry provider calls implicitly.
    if hasattr(adapter.client, "max_retries"):
        adapter.client.max_retries = 0
    return model_class(model, provider=adapter)


def install_engine_adapters():
    """Replace factories in memory only, preserving the children and their stores."""
    for module_name in ("openoutfind.core.llm", "cold_outreach.core.llm"):
        module = importlib.import_module(module_name)
        for provider in module._PROVIDER_BUILDERS:
            module._PROVIDER_BUILDERS[provider] = lambda model, api_key, api_base, p=provider: build_model(p, model, api_key, api_base)

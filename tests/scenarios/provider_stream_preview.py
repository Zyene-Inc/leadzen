"""Disposable browser validation of the existing real provider/Chat/SSE path.

Use a fresh ``LEADZEN_PREVIEW_DIR=.../leadzen-preview.*`` directory. Server-only
inputs are LEADZEN_STREAM_TEST_{PROVIDER,MODEL,BASE_URL,API_KEY}, or a user-supplied
LEADZEN_STREAM_TEST_CONFIG file containing api_key, model and ai_url. Live key
loading requires LEADZEN_STREAM_TEST_APPROVED=1. The cumulative request budget
defaults to three; LEADZEN_STREAM_TEST_REQUEST_LIMIT can explicitly raise it to at
most five without resetting the existing ledger. Each run permits one request,
512 output tokens and no domain tools or retries. Provider evidence records only
HTTP status, content type and received chunk sizes/times, never payloads or keys.
``--check`` validates fixtures and guards without a provider key or network call.
This harness neither replaces nor changes production streaming code.
"""
import contextlib
from dataclasses import replace
import fcntl
import io
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time
from typing import Literal
from unittest.mock import patch
from urllib.parse import urlparse

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))


def disposable_root(value):
    root = Path(value).resolve()
    if not root.is_dir() or not root.name.startswith("leadzen-preview."):
        raise ValueError("A disposable leadzen-preview.* directory is required")
    return root


def blocked(*args, **kwargs):
    raise PermissionError("Only answer-only AI streaming is enabled in this preview")


def request_limit(value="3"):
    limit = int(value or "3")
    if not 1 <= limit <= 5:
        raise ValueError("The cumulative live-preview budget must be between one and five requests")
    return limit


class EvidenceResponse:
    """Delegate the actual HTTP response while recording non-content metadata."""
    def __init__(self, response, root, ordinal, started):
        self.response, self.root, self.ordinal, self.started = response, root, ordinal, started
        content_type = next((value.split(";", 1)[0].strip() for name, value in response.getheaders()
                             if name.lower() == "content-type"), "unknown")
        if not re.fullmatch(r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+", content_type):
            content_type = "unknown"
        self.record({"status": response.status, "contentType": content_type})

    def __getattr__(self, name):
        return getattr(self.response, name)

    def record(self, value):
        with (self.root / "provider-stream-evidence.jsonl").open("a") as evidence:
            os.chmod(evidence.name, 0o600)
            fcntl.flock(evidence, fcntl.LOCK_EX)
            evidence.write(json.dumps({"request": self.ordinal, "elapsedMs": round((time.monotonic() - self.started) * 1000), **value}) + "\n")

    def read1(self, size):
        chunk = self.response.read1(size)
        self.record({"chunkBytes": len(chunk)})
        return chunk

    def read(self, size):
        chunk = self.response.read(size)
        self.record({"chunkBytes": len(chunk)})
        return chunk


def worker_guards(root):
    """Keep the real model, network pinning, worker ownership and Stop guards."""
    from pydantic_ai import Agent as RealAgent, PromptedOutput
    from leadzen.chat.engine import Decision
    from leadzen import ai, transports
    from leadzen.configuration import effective

    class AnswerOnly(Decision):
        tool: Literal["answer"]

    values = effective()
    host = urlparse(values.base_url or ai.BASES.get(values.provider, "")).hostname
    if not host:
        raise ValueError("Configure a supported provider endpoint")
    budget = request_limit(os.environ.get("LEADZEN_STREAM_TEST_REQUEST_LIMIT", "3"))
    real_open, real_socket = ai.pinned_open, transports.public_socket
    used = False

    def answer_agent(model, **kwargs):
        output = kwargs.get("output_type")
        output = replace(output, outputs=AnswerOnly) if isinstance(output, PromptedOutput) else AnswerOnly
        kwargs.update(output_type=output, retries=0,
                      instructions="This is a bounded streaming connection test. Reply to the user's message with tool='answer', arguments={}, and a useful Markdown answer in text. Use at most 250 words. No outreach, tools, external lookups, or private reasoning.",
                      model_settings={**kwargs.get("model_settings", {}), "max_tokens": 512, "timeout": 35})
        return RealAgent(model, **kwargs)

    def limited_open(*args, **kwargs):
        nonlocal used
        if used or kwargs.get("kind", "LLM") != "LLM":
            raise PermissionError("The answer-only run used its one provider request")
        # Reserve before the request. An uncertain submission consumes the budget.
        with (root / "live-provider-call-count").open("a+") as ledger:
            os.chmod(ledger.name, 0o600)
            fcntl.flock(ledger, fcntl.LOCK_EX)
            ledger.seek(0)
            count = int(ledger.read() or "0")
            if count >= budget:
                raise PermissionError("The approved live-preview request budget is exhausted")
            ledger.seek(0)
            ledger.truncate()
            ledger.write(str(count + 1))
            ledger.flush()
        used = True
        started = time.monotonic()
        connection, response = real_open(*args, **kwargs)
        return connection, EvidenceResponse(response, root, count + 1, started)

    def provider_socket(request_host, port, timeout=10):
        if request_host != host or port != 443:
            blocked()
        return real_socket(request_host, port, timeout)

    stack = contextlib.ExitStack()
    for name, replacement in {
        "pydantic_ai.Agent": answer_agent,
        "leadzen.ai.pinned_open": limited_open,
        "leadzen.transports.public_socket": provider_socket,
        "leadzen.chat.engine.perform": blocked,
        "leadzen.chat.engine.prepare": blocked,
        "leadzen.chat.engine.find_leads": blocked,
        "leadzen.outreach.generate": blocked,
        "leadzen.outreach.sync_replies_strict": blocked,
        "leadzen.email_api.post_email": blocked,
        "leadzen.accounts.invitations.post_email": blocked,
        "smtplib.SMTP": blocked,
        "smtplib.SMTP_SSL": blocked,
    }.items():
        stack.enter_context(patch(name, replacement))
    return stack


def run_worker(identifier):
    root = disposable_root(os.environ["LEADZEN_STREAM_TEST_DIR"])
    if Path(os.environ.get("LEADZEN_CONTROL_DB", "")).resolve() != root / "control.sqlite3":
        raise ValueError("Only a disposable preview control database may run")
    if not Path(os.environ.get("LEADZEN_DB", "")).resolve().is_relative_to(root / "workspaces"):
        raise ValueError("Only a disposable preview employee database may run")
    import django
    django.setup()
    from leadzen.chat_worker import main
    with worker_guards(root):
        return main(identifier)


def main(check=False):
    root = disposable_root(os.environ["LEADZEN_PREVIEW_DIR"])
    prompted_hosts = os.environ.get("LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS", "")
    values = {key: os.environ.pop("LEADZEN_STREAM_TEST_" + key, "")
              for key in ("API_KEY", "PROVIDER", "MODEL", "BASE_URL", "APPROVED", "CONFIG", "REQUEST_LIMIT")}
    if values["CONFIG"]:
        if values["APPROVED"] != "1":
            raise ValueError("Fresh approval is required before loading a live key")
        selected = {}
        for line in Path(values["CONFIG"]).read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() in {"api_key", "model", "ai_url"}:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                selected[key.strip()] = value
        values.update(API_KEY=selected.get("api_key", ""), MODEL=selected.get("model", ""),
                      BASE_URL=selected.get("ai_url", ""), PROVIDER="openai_compatible")
    if not check and values["API_KEY"] and values["APPROVED"] != "1":
        raise ValueError("A freshly approved server-only test key is required")
    budget = request_limit(values["REQUEST_LIMIT"])

    class SeedOnly:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def serve_forever(self):
            pass

    # Reuse all existing disposable accounts/fixtures/migrations. No listener or
    # provider runs while seeding; the synthetic patches unwind on return.
    with patch("wsgiref.simple_server.make_server", return_value=SeedOnly()), contextlib.redirect_stdout(io.StringIO()):
        fixture = runpy.run_path(str(REPOSITORY / "tests/scenarios/local_preview.py"))
    from leadzen.accounts.models import AccountProfile
    from leadzen.configuration import save_dashboard_settings
    from leadzen.workspaces import workspace_scope, worker_environment
    profile = AccountProfile.objects.select_related("user").get(user__email="ready@preview.example")
    if values["BASE_URL"]:
        host = urlparse(values["BASE_URL"]).hostname
        if not host:
            raise ValueError("The supplied provider URL has no host")
        os.environ["LEADZEN_LLM_HOSTS"] = host
    with workspace_scope(profile):
        save_dashboard_settings({"ai_enabled": True, "provider": values["PROVIDER"] or "openai",
                                 "model": values["MODEL"] or "gpt-4o-mini", "base_url": values["BASE_URL"],
                                 "mailbox_address": "sender@preview.example", "smtp_host": "smtp.zoho.com", "smtp_port": 587,
                                 "imap_host": "imap.zoho.com", "imap_port": 993},
                                llm_api_key=values["API_KEY"] or ("synthetic-stream-check-only" if check else None),
                                clear_llm_api_key=not values["API_KEY"] and not check)
    values["API_KEY"] = ""  # Worker reads encrypted fixture Settings, never argv/env.
    os.environ.update(LEADZEN_STREAM_TEST_DIR=str(root), LEADZEN_STREAM_TEST_REQUEST_LIMIT=str(budget),
                      LEADZEN_CHAT_PROMPTED_OUTPUT_HOSTS=prompted_hosts)

    def launch(request, run):
        if request.actor.pk != profile.user_id or run.thread.context.get("mcpConnectionId"):
            blocked()
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", str(run.pk)],
                         env=worker_environment(request.actor.leadzen_profile), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def restricted_application(environ, start_response):
        path, method = environ.get("PATH_INFO", ""), environ.get("REQUEST_METHOD", "")
        read = method == "GET" and (path in {"/api/auth/me", "/api/settings", "/api/chat/context", "/api/chat/threads", "/api/health"}
                                    or re.fullmatch(r"/api/chat/threads/[0-9a-f-]{36}(?:/stream)?", path))
        write = ((method == "POST" and path in {"/api/auth/login", "/api/auth/logout", "/api/chat/threads"})
                 or (method == "PUT" and path in {"/api/chat/context", "/api/settings"})
                 or (method == "POST" and re.fullmatch(r"/api/chat/(?:threads/[0-9a-f-]{36}/messages|runs/[0-9a-f-]{36}/cancel)", path)))
        if not read and not write:
            start_response("403 Forbidden", [("Content-Type", "application/json"), ("Cache-Control", "no-store")])
            return [json.dumps({"error": "Only Chat streaming validation is available in this preview"}).encode()]
        return application(environ, start_response)

    if check:
        with workspace_scope(profile), worker_guards(root):
            blocked_checks = ["leadzen.chat.engine.perform", "leadzen.chat.engine.prepare", "leadzen.chat.engine.find_leads"]
            import importlib
            for name in blocked_checks:
                module, member = name.rsplit(".", 1)
                try:
                    getattr(importlib.import_module(module), member)(None)
                except PermissionError:
                    continue
                raise AssertionError("A domain tool was not blocked")
            from pydantic_ai import Agent, PromptedOutput
            from leadzen.ai import build_model
            from leadzen.chat.engine import Decision
            from leadzen.configuration import effective
            configured = effective()
            marker = PromptedOutput(Decision, name="preview-answer", description="Answer only", template="Return JSON using {schema}")
            agent = Agent(build_model(configured.provider, configured.model, configured.llm_api_key, configured.base_url), output_type=marker)
            assert isinstance(agent.output_type, PromptedOutput)
            assert (agent.output_type.name, agent.output_type.description, agent.output_type.template) == (marker.name, marker.description, marker.template)
            assert agent.output_type.outputs.model_fields["tool"].annotation == Literal["answer"]
        from types import SimpleNamespace
        actual_chunk = b"never-log-this-body"
        response = SimpleNamespace(status=200, getheaders=lambda: [("Content-Type", "text/event-stream"), ("X-Private", "never-log-this-header")], read1=lambda size: actual_chunk)
        with patch.object(EvidenceResponse, "record") as record:
            proof = EvidenceResponse(response, root, 1, time.monotonic())
            assert proof.read1(8192) == actual_chunk
            assert [call.args[0] for call in record.call_args_list] == [{"status": 200, "contentType": "text/event-stream"}, {"chunkBytes": len(actual_chunk)}]
        assert request_limit("5") == 5
        try:
            request_limit("6")
        except ValueError:
            pass
        else:
            raise AssertionError("A wider request budget was accepted")
        # Reusing a fixture never erases an earlier reservation or evidence.
        print("Disposable fixtures and answer-only guards verified; no provider calls made", flush=True)
        return 0

    from django.core.wsgi import get_wsgi_application
    from wsgiref.simple_server import make_server
    application = get_wsgi_application()
    with patch("leadzen.chat.views.launch", launch), patch("leadzen.ai.build_model", blocked), patch("leadzen.transports.public_socket", blocked):
        print(f"Answer-only provider preview at http://127.0.0.1:8000; at most {budget} live model requests. Domain actions are blocked.", flush=True)
        with make_server("127.0.0.1", 8000, restricted_application, handler_class=fixture["QuietLog"], server_class=fixture["PreviewServer"]) as server:
            server.serve_forever()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run_worker(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == "--worker" else main(check="--check" in sys.argv[1:]))
    except Exception:
        # SDK exception text can contain provider request details. Keep all output
        # generic; app persistence/status and browser observations are the evidence.
        raise SystemExit("Provider preview could not start; check disposable directory, server-only inputs and authorization") from None

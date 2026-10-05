"""Recheck the employee's revocable MCP grant at each existing external sink."""
from contextlib import contextmanager
from contextvars import ContextVar
import os

_connection = ContextVar("leadzen_mcp_execution", default=None)


def assert_connection_access():
    identity = _connection.get()
    if identity is None:
        return
    from leadzen.mcp.auth import connection_live
    connection_live(*identity)
    run_id = os.environ.get("LEADZEN_CHAT_RUN_ID")
    if run_id:
        from django.utils import timezone
        from leadzen.config.models import ChatRun
        row = ChatRun.objects.select_related("thread").filter(
            pk=run_id, actor_id=identity[1], status="running", cancel_requested=False,
            deadline_at__gt=timezone.now(), approval_expires_at__gt=timezone.now(),
        ).first()
        if not row or row.thread.context.get("mcpConnectionId") != str(identity[0]):
            raise PermissionError("This MCP action stopped or its approval expired.")


@contextmanager
def connection_execution(connection_id, actor_id):
    token = _connection.set((connection_id, actor_id))
    try:
        assert_connection_access()
        yield
    finally:
        _connection.reset(token)

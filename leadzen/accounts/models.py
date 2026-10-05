import uuid

from django.conf import settings
from django.db import models


class AccountProfile(models.Model):
    """Company account and a server-assigned, private outreach workspace."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="leadzen_profile")
    must_change_password = models.BooleanField(default=True)
    purpose = models.CharField(max_length=32, blank=True, default="")
    workspace_name = models.CharField(max_length=160, blank=True, default="")
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    tour_started_at = models.DateTimeField(null=True, blank=True)
    tour_current_step = models.CharField(max_length=64, default="welcome")
    tour_completed_at = models.DateTimeField(null=True, blank=True)
    tour_skipped_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginSession(models.Model):
    token_hash = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LoginThrottle(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    window_started_at = models.DateTimeField()


class AccountAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    target_id = models.PositiveIntegerField(null=True)
    action = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)


class EmployeeInvitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    encrypted_token = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    delivery_status = models.CharField(max_length=16, default="pending")
    provider_message_id = models.CharField(max_length=200, blank=True, default="")
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MCPClient(models.Model):
    """Public OAuth client registration; all MCP identity state stays in control DB."""

    id = models.CharField(primary_key=True, max_length=80)
    name = models.CharField(max_length=160)
    redirect_uris = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class MCPConnection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    client = models.ForeignKey(MCPClient, on_delete=models.CASCADE)
    resource = models.CharField(max_length=1000)
    scopes = models.JSONField(default=list)
    password_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


class MCPAuthorizationRequest(models.Model):
    request_hash = models.CharField(primary_key=True, max_length=64)
    client = models.ForeignKey(MCPClient, on_delete=models.CASCADE)
    redirect_uri = models.CharField(max_length=1000)
    resource = models.CharField(max_length=1000)
    scopes = models.JSONField(default=list)
    code_challenge = models.CharField(max_length=43)
    state = models.CharField(max_length=2000, blank=True, default="")
    expires_at = models.DateTimeField(db_index=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    connection = models.ForeignKey(MCPConnection, null=True, blank=True, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64, null=True, blank=True, unique=True)
    code_expires_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MCPAccessToken(models.Model):
    token_hash = models.CharField(primary_key=True, max_length=64)
    connection = models.ForeignKey(MCPConnection, on_delete=models.CASCADE)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MCPRefreshToken(models.Model):
    token_hash = models.CharField(primary_key=True, max_length=64)
    connection = models.ForeignKey(MCPConnection, on_delete=models.CASCADE)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

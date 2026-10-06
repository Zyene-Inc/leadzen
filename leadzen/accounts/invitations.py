"""Admin-issued, expiring capabilities; acceptance never grants a submitted role."""
import hashlib
import html
import os
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from leadzen.accounts.models import AccountAudit, AccountProfile, EmployeeInvitation, LoginSession
from leadzen.accounts.service import audit, email_address, password_value
from leadzen.configuration import _encode
from leadzen.email_api import DeliveryError, post_email


def invitation_config():
    origin = os.environ.get("LEADZEN_PUBLIC_URL", "https://leadzen.zyene.com").rstrip("/")
    parsed = urlsplit(origin)
    local = parsed.hostname in {"localhost", "127.0.0.1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path or (parsed.scheme != "https" and not (local and parsed.scheme == "http")):
        raise ValueError("Configure the LeadZen public URL before inviting employees")
    key = os.environ.get("LEADZEN_RESEND_API_KEY", "")
    sender = os.environ.get("LEADZEN_INVITATION_FROM", "LeadZen by Zyene <accounts@leadzen.zyene.com>")
    if not key or "\n" in sender or "\r" in sender:
        raise ValueError("Configure Resend and a verified invitation sender before inviting employees")
    return origin, key, sender


def issue_invitation(actor, *, email=None, name=None, target=None):
    origin, key, sender = invitation_config()
    # Encrypt before any account write; missing encryption must fail closed.
    raw = secrets.token_urlsafe(48)
    encrypted = _encode({"invitation_token": raw})
    now = timezone.now()
    with transaction.atomic(using="default"):
        actor = get_user_model().objects.using("default").get(pk=actor.pk)
        if not actor.is_active or not actor.is_staff or actor.leadzen_profile.deleted_at:
            raise PermissionError("Administrator access is required")
        recent = AccountAudit.objects.using("default").filter(actor=actor, action="invitation_issued", created_at__gt=now - timedelta(hours=1)).count()
        if recent >= 20:
            raise ValueError("Invitation limit reached. Try again in an hour.")
        if target is None:
            email = email_address(email)
            if not isinstance(name, str) or not name.strip() or len(name) > 150 or any(ord(c) < 32 for c in name):
                raise ValueError("Enter an employee name of up to 150 characters")
            existing = (get_user_model().objects.using("default")
                        .select_for_update().filter(username=email).first())
            if existing:
                profile = AccountProfile.objects.using("default").filter(user=existing).first()
                if existing.is_staff or profile is None:
                    raise ValueError("An account with that email already exists.")
                if profile.deleted_at is None and not existing.is_active:
                    raise ValueError("That account is disabled. Enable it, then send an invitation.")
                if existing.is_active or profile.deleted_at is None:
                    raise ValueError("An account with that email already exists. Use Resend invitation instead.")
                # Keep the deleted employee and their outreach history archived.
                # A new invitation receives a new user ID and isolated workspace,
                # so old permissions and automatic approvals cannot resume.
                existing.username = f"deleted-{existing.pk}-{secrets.token_hex(12)}"
                existing.save(using="default", update_fields=["username"])
                audit(actor, "account_replaced", existing.pk)
            target = get_user_model()(username=email, email=email, first_name=name.strip(), is_staff=False)
            target.set_unusable_password()
            target.save(using="default")
            AccountProfile.objects.using("default").create(user=target, must_change_password=False)
        else:
            target = get_user_model().objects.using("default").select_related("leadzen_profile").get(pk=target.pk)
            if not target.is_active or target.leadzen_profile.deleted_at or target.pk == actor.pk or target.is_staff:
                raise ValueError("Only active employee accounts can receive a setup invitation")
            previous = EmployeeInvitation.objects.using("default").filter(user=target).order_by("-created_at").first()
            if previous and previous.last_attempt_at and previous.last_attempt_at > now - timedelta(seconds=60):
                raise ValueError("Wait one minute before resending an invitation")
        EmployeeInvitation.objects.using("default").filter(user=target, consumed_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now, encrypted_token="")
        invitation = EmployeeInvitation.objects.using("default").create(user=target, token_hash=hashlib.sha256(raw.encode()).hexdigest(), encrypted_token=encrypted, expires_at=now + timedelta(hours=48), last_attempt_at=now)
        LoginSession.objects.using("default").filter(user=target).delete()
        from leadzen.mcp.auth import revoke_actor_connections
        revoke_actor_connections(target.pk)
        audit(actor, "invitation_issued", target.pk)
    link = f"{origin}/setup#token={raw}"
    safe_name, safe_link = html.escape(target.first_name), html.escape(link, quote=True)
    text = f"Hi {target.first_name},\n\nYou have been invited to LeadZen by Zyene. Create your password here:\n{link}\n\nThis link expires in 48 hours and can be used once.\nNeed help? support@zyene.com"
    # Commit the capability before network I/O. A slow provider must not hold
    # the control database write lock and block other employees signing in.
    invitation.delivery_status = "failed"
    try:
        actor_live = get_user_model().objects.using("default").filter(
            pk=actor.pk, is_active=True, is_staff=True, leadzen_profile__deleted_at__isnull=True,
        ).exists()
        if not actor_live or valid_invitation(raw) is None:
            raise ValueError("Account access changed before this invitation could be sent")
        identifier = post_email("https://api.resend.com/emails", key, {"from": sender, "to": [target.email], "reply_to": "support@zyene.com", "subject": "Your LeadZen workspace is ready to set up", "text": text, "html": f'<p>Hi {safe_name},</p><p>You have been invited to LeadZen by Zyene.</p><p><a href="{safe_link}">Create your password</a></p><p>This link expires in 48 hours and can be used once.</p><p>Need help? support@zyene.com</p>'}, operation_id=f"employee-invite/{invitation.pk}")
        invitation.delivery_status = "sent"
        invitation.provider_message_id = identifier
    except DeliveryError:
        invitation.delivery_status = "failed"
    finally:
        # Token plaintext is never returned to the admin or persisted in logs.
        invitation.encrypted_token = ""
        invitation.save(using="default", update_fields=["delivery_status", "provider_message_id", "encrypted_token"])
    return target, invitation


def valid_invitation(raw):
    if not isinstance(raw, str) or not 40 <= len(raw) <= 200:
        return None
    return EmployeeInvitation.objects.using("default").select_related("user__leadzen_profile").filter(token_hash=hashlib.sha256(raw.encode()).hexdigest(), consumed_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now(), user__is_active=True, user__leadzen_profile__deleted_at__isnull=True).first()


def accept_invitation(raw, password):
    with transaction.atomic(using="default"):
        invitation = valid_invitation(raw)
        if invitation is None:
            raise ValueError("This setup link is invalid or expired. Ask your administrator for a new invitation.")
        user = invitation.user
        user.set_password(password_value(password, user))
        changed = EmployeeInvitation.objects.using("default").filter(pk=invitation.pk, consumed_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()).update(consumed_at=timezone.now(), encrypted_token="")
        if changed != 1:
            raise ValueError("This setup link has already been used")
        user.save(using="default", update_fields=["password"])
        AccountProfile.objects.using("default").filter(user=user).update(must_change_password=False)
        LoginSession.objects.using("default").filter(user=user).delete()
        from leadzen.mcp.auth import revoke_actor_connections
        revoke_actor_connections(user.pk)
        audit(user, "invitation_accepted", user.pk)
    return user

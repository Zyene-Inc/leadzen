"""Company-owned accounts, revocable opaque sessions, and live role checks."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from functools import wraps

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from leadzen.accounts.models import AccountAudit, AccountProfile, LoginSession, LoginThrottle

SESSION_SECONDS = 12 * 60 * 60
_dummy_hash = make_password("LeadZen invalid-account timing check")


def payload(request):
    if len(request.body) > 65536:
        raise ValueError("Request is too large")
    try:
        value = json.loads(request.body or "{}")
    except (ValueError, RecursionError) as exc:
        raise ValueError("Request must contain valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("A JSON object is required")
    return value


def email_address(value):
    if not isinstance(value, str):
        raise ValueError("A valid email address is required")
    value = value.strip().lower()
    validate_email(value)
    if len(value) > 150:
        raise ValueError("Email address is too long")
    return value


def password_value(value, user=None):
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError("Password must be between 12 and 256 characters")
    validate_password(value, user=user)
    return value


def error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def session_user(request):
    token = request.headers.get("X-LeadZen-Session", "")
    if not token or len(token) > 200:
        return None
    session = LoginSession.objects.using("default").select_related("user__leadzen_profile").filter(
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at__gt=timezone.now(),
        user__is_active=True, user__leadzen_profile__deleted_at__isnull=True, user__leadzen_profile__isnull=False,
    ).first()
    return session.user if session else None


def tour_payload(profile):
    return {
        "tourStarted": profile.tour_started_at is not None or profile.tour_completed_at is not None,
        "currentStep": profile.tour_current_step,
        "tourCompleted": profile.tour_completed_at is not None,
        "tourSkipped": profile.tour_skipped_at is not None,
    }


def user_payload(user):
    profile = user.leadzen_profile
    return {
        "id": user.pk, "email": user.email, "name": user.first_name,
        "is_admin": user.is_staff, "is_active": user.is_active,
        "must_change_password": profile.must_change_password,
        "onboarded": profile.onboarding_completed_at is not None,
        "purpose": profile.purpose, "workspace_name": profile.workspace_name,
        "created_at": profile.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "tour_completed": profile.tour_completed_at is not None,
        "tour_started": profile.tour_started_at is not None or profile.tour_completed_at is not None,
        "tour_skipped": profile.tour_skipped_at is not None,
        "tour": tour_payload(profile),
        "invitation_pending": not user.has_usable_password(),
    }


def access(*, admin=False, workspace=False, allow_setup=False):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            from leadzen.web import _cors, _token_is_valid
            if not _token_is_valid(request):
                return _cors(error("Unauthorized", 401), request)
            user = session_user(request)
            if user is None:
                return _cors(error("Your session has expired. Please sign in again.", 401), request)
            if admin and not user.is_staff:
                return _cors(error("Administrator access is required", 403), request)
            profile = user.leadzen_profile
            if not allow_setup and profile.must_change_password:
                return _cors(JsonResponse({"error": "Change your temporary password first", "redirect": "/password"}, status=403), request)
            if workspace and profile.onboarding_completed_at is None:
                return _cors(JsonResponse({"error": "Complete your workspace setup first", "redirect": "/onboarding"}, status=403), request)
            request.actor = user
            try:
                if workspace:
                    from leadzen.workspaces import workspace_scope
                    with workspace_scope(profile):
                        response = view(request, *args, **kwargs)
                else:
                    response = view(request, *args, **kwargs)
            except (ValueError, ValidationError) as exc:
                message = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
                response = error(message)
            return _cors(response, request)
        return wrapped
    return decorate


def audit(actor, action, target_id=None):
    AccountAudit.objects.using("default").create(actor=actor, action=action, target_id=target_id)


def create_account(*, email, name, password, is_admin=False, require_change=True):
    email = email_address(email)
    user = get_user_model()(username=email, email=email, first_name=str(name).strip()[:150], is_staff=is_admin)
    user.set_password(password_value(password, user))
    with transaction.atomic(using="default"):
        if get_user_model().objects.using("default").filter(username=email).exists():
            raise ValueError("An account with that email already exists")
        user.save(using="default")
        AccountProfile.objects.using("default").create(user=user, must_change_password=require_change)
    return user


def login(email, password):
    # DB-backed limiter is shared by all API workers; it cannot reset on redeploy.
    key = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic(using="default"):
        LoginThrottle.objects.using("default").filter(window_started_at__lt=now - timedelta(days=1)).delete()
        global_counter, _ = LoginThrottle.objects.using("default").select_for_update().get_or_create(key="global_login", defaults={"window_started_at": now})
        if global_counter.window_started_at < now - timedelta(minutes=1):
            global_counter.attempts, global_counter.window_started_at = 0, now
        if global_counter.attempts >= 60:
            return None, None, 429
        global_counter.attempts += 1
        global_counter.save(using="default")
        counter, _ = LoginThrottle.objects.using("default").select_for_update().get_or_create(key=key, defaults={"window_started_at": now})
        if counter.window_started_at < now - timedelta(minutes=15):
            counter.attempts, counter.window_started_at = 0, now
        if counter.attempts >= 5:
            return None, None, 429
        counter.attempts += 1
        counter.save(using="default")
    user = get_user_model().objects.using("default").select_related("leadzen_profile").filter(
        username=email.lower().strip(), is_active=True, leadzen_profile__deleted_at__isnull=True,
        leadzen_profile__isnull=False,
    ).first()
    valid = check_password(password, user.password if user else _dummy_hash)
    if not user or not valid:
        return None, None, 401
    verified_hash = user.password
    with transaction.atomic(using="default"):
        # Password checks deliberately run outside the database write lock.
        # A reset/deactivation during hashing must not mint a new session from
        # the stale user object after the reset has revoked previous sessions.
        user = get_user_model().objects.using("default").select_for_update().select_related("leadzen_profile").filter(
            pk=user.pk, is_active=True, leadzen_profile__deleted_at__isnull=True,
            leadzen_profile__isnull=False,
        ).first()
        if user is None or not hmac.compare_digest(user.password, verified_hash):
            return None, None, 401
        LoginThrottle.objects.using("default").filter(pk=key).update(attempts=0)
        LoginSession.objects.using("default").filter(user=user, expires_at__lte=now).delete()
        stale = list(LoginSession.objects.using("default").filter(user=user).order_by("-created_at").values_list("pk", flat=True)[19:])
        LoginSession.objects.using("default").filter(pk__in=stale).delete()
        token = secrets.token_urlsafe(48)
        LoginSession.objects.using("default").create(user=user, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=now + timedelta(seconds=SESSION_SECONDS))
        user.last_login = now
        user.save(using="default", update_fields=["last_login"])
    return user, token, 200

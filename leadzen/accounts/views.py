import hashlib
import hmac
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pytz import country_names

from leadzen.accounts.models import AccountProfile, LoginSession
from leadzen.accounts.service import access, audit, email_address, error, login, password_value, payload, session_user, tour_payload, user_payload


@csrf_exempt
@require_http_methods(["POST"])
def sign_in(request):
    from leadzen.web import _cors, _token_is_valid
    if not _token_is_valid(request):
        return _cors(error("Unauthorized", 401), request)
    try:
        body = payload(request)
        email = email_address(body.get("email"))
        password = body.get("password", "")
        if not isinstance(password, str) or len(password) > 256:
            raise ValueError("Invalid credentials")
        user, token, status = login(email, password)
        if user is None:
            return _cors(error("Too many attempts. Try again in 15 minutes." if status == 429 else "Incorrect email or password", status), request)
        return _cors(JsonResponse({"user": user_payload(user), "session_token": token}), request)
    except (ValueError, ValidationError):
        return _cors(error("Incorrect email or password", 401), request)


@require_http_methods(["GET"])
@access(allow_setup=True)
def me(request):
    return JsonResponse({"user": user_payload(request.actor)})


@csrf_exempt
@require_http_methods(["POST"])
@access(allow_setup=True)
def sign_out(request):
    token = request.headers.get("X-LeadZen-Session", "")
    LoginSession.objects.using("default").filter(token_hash=hashlib.sha256(token.encode()).hexdigest(), user=request.actor).delete()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
@access(allow_setup=True)
def change_password(request):
    body = payload(request)
    user = request.actor
    if not user.check_password(str(body.get("current_password", ""))):
        return error("Current password is incorrect", 403)
    new_password = password_value(body.get("new_password"), user)
    if user.check_password(new_password):
        return error("Choose a password different from the temporary password")
    verified_hash = user.password
    with transaction.atomic(using="default"):
        live = session_user(request)
        if live is None or live.pk != user.pk or not hmac.compare_digest(live.password, verified_hash):
            return error("Your account access changed. Sign in again before changing your password.", 401)
        user = live
        user.set_password(new_password)
        user.save(using="default", update_fields=["password"])
        AccountProfile.objects.using("default").filter(user=user).update(must_change_password=False)
        LoginSession.objects.using("default").filter(user=user).delete()
        from leadzen.mcp.auth import revoke_actor_connections
        revoke_actor_connections(user.pk)
        audit(user, "password_changed", user.pk)
    return JsonResponse({"ok": True, "redirect": "/login"})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(admin=True)
def admin_users(request):
    if request.method == "POST":
        body = payload(request)
        from leadzen.accounts.invitations import issue_invitation
        if body.get("role", "employee") != "employee":
            return error("This page creates employee accounts only")
        user, invitation = issue_invitation(request.actor, email=body.get("email"), name=body.get("name"))
        return JsonResponse({"user": user_payload(user), "invitation_status": invitation.delivery_status}, status=201)
    users = get_user_model().objects.using("default").select_related("leadzen_profile").filter(
        leadzen_profile__isnull=False, leadzen_profile__deleted_at__isnull=True,
    ).order_by("-date_joined")
    return JsonResponse({
        "totals": {"users": users.count(), "active": users.filter(is_active=True).count(),
                   "admins": users.filter(is_staff=True, is_active=True).count(),
                   "onboarded": users.filter(leadzen_profile__onboarding_completed_at__isnull=False).count()},
        "users": [user_payload(user) for user in users[:500]],
    })


@csrf_exempt
@require_http_methods(["POST"])
@access(admin=True)
def resend_invitation(request, user_id):
    from leadzen.accounts.invitations import issue_invitation
    user = get_user_model().objects.using("default").filter(pk=user_id, leadzen_profile__deleted_at__isnull=True, leadzen_profile__isnull=False).first()
    if user is None:
        return error("Account not found", 404)
    _, invitation = issue_invitation(request.actor, target=user)
    return JsonResponse({"invitation_status": invitation.delivery_status})


@csrf_exempt
@require_http_methods(["POST"])
def setup_invitation(request):
    from leadzen.accounts.invitations import accept_invitation, valid_invitation
    from leadzen.web import _cors, _token_is_valid
    if not _token_is_valid(request):
        return _cors(error("Unauthorized", 401), request)
    try:
        body = payload(request)
        if "password" in body:
            accept_invitation(body.get("token"), body.get("password"))
            response = JsonResponse({"ok": True, "redirect": "/login"})
        else:
            invitation = valid_invitation(body.get("token"))
            if invitation is None:
                raise ValueError("This setup link is invalid or expired. Ask your administrator for a new invitation.")
            response = JsonResponse({"name": invitation.user.first_name, "email": invitation.user.email})
    except (ValueError, ValidationError) as exc:
        response = error("; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
    return _cors(response, request)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@access(workspace=True)
def complete_tour(request):
    if request.method == "GET":
        return JsonResponse({"tour": tour_payload(request.actor.leadzen_profile)})
    body = payload(request)
    if set(body) - {"action", "currentStep"}:
        raise ValueError("Only action and currentStep are accepted")
    # Existing clients use an empty POST to complete the previous tour.
    action = body.get("action", "complete" if not body else None)
    if action not in ("start", "progress", "complete", "skip"):
        raise ValueError("Choose start, progress, complete or skip")
    current_step = body.get("currentStep")
    if current_step is not None and (not isinstance(current_step, str) or len(current_step) > 64 or not re.fullmatch(r"[a-z][a-z0-9-]*", current_step)):
        raise ValueError("currentStep must be a short lowercase step identifier")
    if action == "progress" and current_step is None:
        raise ValueError("currentStep is required for progress")
    with transaction.atomic(using="default"):
        profile = AccountProfile.objects.using("default").select_for_update().get(user=request.actor)
        if action == "progress" and (profile.tour_started_at is None or profile.tour_completed_at is not None or profile.tour_skipped_at is not None):
            return error("Start the tour before saving its progress", 409)
        now = timezone.now()
        if action == "start":
            profile.tour_started_at = now
            profile.tour_completed_at = profile.tour_skipped_at = None
            profile.tour_current_step = current_step or "welcome"
        else:
            if current_step is not None:
                profile.tour_current_step = current_step
            if action in ("complete", "skip"):
                profile.tour_started_at = profile.tour_started_at or now
                profile.tour_completed_at = now if action == "complete" else None
                profile.tour_skipped_at = now if action == "skip" else None
        profile.save(using="default", update_fields=["tour_started_at", "tour_current_step", "tour_completed_at", "tour_skipped_at"])
    return JsonResponse({"ok": True, "tour": tour_payload(profile)})


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
@access(admin=True)
def admin_user(request, user_id):
    with transaction.atomic(using="default"):
        user = get_user_model().objects.using("default").select_for_update().select_related("leadzen_profile").filter(
            pk=user_id, leadzen_profile__isnull=False, leadzen_profile__deleted_at__isnull=True,
        ).first()
        if user is None:
            return error("Account not found", 404)
        if user.pk == request.actor.pk:
            return error("You cannot deactivate or delete your own administrator account", 409)
        body = payload(request) if request.method == "PUT" else {}
        active = body.get("is_active", user.is_active)
        if not isinstance(active, bool):
            return error("is_active must be a boolean")
        removing_admin = user.is_staff and (request.method == "DELETE" or not active)
        if removing_admin and get_user_model().objects.using("default").filter(
            is_staff=True, is_active=True, leadzen_profile__deleted_at__isnull=True,
            leadzen_profile__isnull=False,
        ).exclude(pk=user.pk).count() == 0:
            return error("At least one active administrator must remain", 409)
        if request.method == "DELETE":
            user.is_active = False
            user.leadzen_profile.deleted_at = timezone.now()
            user.leadzen_profile.save(using="default", update_fields=["deleted_at"])
            action = "account_deleted"
        elif "password" in body:
            return error("Send a reset invitation so the employee can choose their password")
        else:
            user.is_active = active
            action = "account_activated" if active else "account_deactivated"
        user.save(using="default")
        LoginSession.objects.using("default").filter(user=user).delete()
        from leadzen.mcp.auth import revoke_actor_connections
        revoke_actor_connections(user.pk)
        audit(request.actor, action, user.pk)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@access()
def onboarding(request):
    from leadzen.config.models import SiteConfig
    from leadzen.configuration import SettingsError, _fernet, effective, finder_settings, lead_finder_credentials, save_dashboard_settings, validate_public
    from leadzen.workspaces import database_path, initialize_workspace, workspace_scope
    profile = request.actor.leadzen_profile
    if request.method == "GET":
        values = {"purpose": profile.purpose, "workspace_name": profile.workspace_name,
                  "product_docs": "", "campaign_target": "", "operator_country_code": "US", "booking_link": ""}
        if database_path(profile).is_file():
            with workspace_scope(profile):
                config = SiteConfig.load()
                values.update({name: getattr(config, name) for name in ("product_docs", "campaign_target", "operator_country_code", "booking_link")})
                from leadzen.web import _settings_payload
                values["connections"] = _settings_payload()
        return JsonResponse(values)
    body = payload(request)
    if body.get("purpose") not in {"zyene_reviews", "zyene_services", "other"}:
        return error("Select the purpose of this workspace")
    for key, limit in (("workspace_name", 160), ("product_docs", 10000), ("campaign_target", 10000)):
        if not isinstance(body.get(key), str) or not body[key].strip() or len(body[key]) > limit:
            return error(f"{key} is required and must be at most {limit} characters")
    country = str(body.get("operator_country_code", "")).upper()
    if country not in country_names:
        return error("Select a valid operator country")
    if body.get("accepted_legal_notice") is not True:
        return error("Confirm that you are authorized to use this mailbox and conduct this outreach")
    llm, mailbox = body.get("llm", {}), body.get("mailbox", {})
    if not isinstance(llm, dict) or not isinstance(mailbox, dict):
        return error("Connection settings are required")
    public = {"provider": llm.get("provider", ""), "model": llm.get("model", ""), "base_url": llm.get("base_url", ""),
              "mailbox_address": mailbox.get("address"), "smtp_host": mailbox.get("smtp_host", ""),
              "smtp_port": mailbox.get("smtp_port", 587), "imap_host": mailbox.get("imap_host", ""),
              "imap_port": mailbox.get("imap_port", 993), "signature": mailbox.get("signature", "")}
    public.update({"mail_transport": mailbox.get("transport", "smtp"), "mail_api_url": mailbox.get("api_url", ""),
                   "smtp_username": mailbox.get("smtp_username", ""), "ai_enabled": llm.get("enabled", True)})
    try:
        from leadzen.setup_wizard import validate_booking_link
        booking_link = validate_booking_link(body.get("booking_link", ""))
        lead_finder_credentials(body)
        public = validate_public(public)
        if not public["mailbox_address"]:
            raise SettingsError("A sending email address is required")
        if public["ai_enabled"] and (not public["provider"] or not public["model"]):
            raise SettingsError("Select an AI provider and model, or disable AI for manual campaigns")
        _fernet()  # Refuse incomplete encryption setup before creating any workspace.
        for credential in (llm.get("api_key"), mailbox.get("password"), mailbox.get("api_key"), mailbox.get("imap_password")):
            if credential is not None and (not isinstance(credential, str) or len(credential) > 2000):
                raise SettingsError("Credentials must be text, at most 2000 characters")
        if public["mail_transport"] == "smtp" and not public["smtp_host"]:
            raise SettingsError("An SMTP host is required")
        initialize_workspace(profile)
        with workspace_scope(profile) as alias, transaction.atomic(using=alias):
            config = SiteConfig.load()
            for key in ("product_docs", "campaign_target"):
                setattr(config, key, body[key].strip())
            config.operator_name = request.actor.first_name
            config.operator_email = email_address(public["mailbox_address"])
            config.operator_country_code = country
            config.accepted_legal_notice = True
            config.booking_link = booking_link
            config.save()
            save_dashboard_settings(public, llm_api_key=llm.get("api_key"), mailbox_password=mailbox.get("password"), mail_api_key=mailbox.get("api_key"), imap_password=mailbox.get("imap_password"), **finder_settings(body, effective()))
            current = effective()
            if (current.ai_enabled and not current.llm_api_key) or not (current.mailbox_password if current.mail_transport == "smtp" else current.mail_api_key):
                raise SettingsError("Changing provider, endpoint or mailbox requires new credentials")
        profile.purpose = body["purpose"]
        profile.workspace_name = body["workspace_name"].strip()
        profile.onboarding_completed_at = timezone.now()
        profile.save(using="default")
        audit(request.actor, "workspace_configured", request.actor.pk)
        return JsonResponse({"ok": True, "user": user_payload(request.actor)})
    except SettingsError as exc:
        return error(str(exc), 503 if "LEADZEN_SETTINGS_KEY" in str(exc) else 400)

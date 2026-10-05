from django.urls import path

from leadzen import web
from leadzen.accounts import views as accounts
from leadzen import campaigns
from leadzen import crm
from leadzen.chat import views as chat
from leadzen import setup_wizard
from leadzen import home
from leadzen import discovery
from leadzen import outreach, workspace_actions
from leadzen import activity, autopilot
from leadzen import workspace_settings
from leadzen.mcp import views as mcp_views
from leadzen.mcp.transport import endpoint as mcp_endpoint


urlpatterns = [
    path("mcp", mcp_endpoint),
    path(".well-known/oauth-protected-resource", mcp_views.resource_metadata),
    path(".well-known/oauth-protected-resource/mcp", mcp_views.resource_metadata),
    path(".well-known/oauth-authorization-server", mcp_views.authorization_metadata),
    path("mcp/oauth/register", mcp_views.register_client),
    path("mcp/oauth/authorize", mcp_views.authorize),
    path("mcp/oauth/token", mcp_views.token),
    path("mcp/oauth/revoke", mcp_views.revoke),
    path("api/mcp/connections", mcp_views.connections),
    path("api/mcp/authorize", mcp_views.consent),
    path("", web.dashboard_entry),
    path("api/settings/backup", workspace_settings.backup),
    path("api/activity", activity.feed),
    path("api/autopilot", autopilot.settings),
    path("api/activity/logs", activity.developer_logs),
    path("api/inbox/check", workspace_actions.check_replies),
    path("api/attention", workspace_actions.attention),
    path("api/outreach", outreach.overview),
    path("api/outreach/reviews", outreach.reviews),
    path("api/outreach/reviews/<uuid:review_id>", outreach.review),
    path("api/outreach/reviews/<uuid:review_id>/drafts/<uuid:draft_id>", outreach.draft),
    path("api/inbox/conversations", outreach.conversations),
    path("api/inbox/conversations/<int:thread_id>", outreach.conversation),
    path("api/discovery", discovery.discovery),
    path("api/discovery/<uuid:run_id>", discovery.progress),
    path("api/discovery/<uuid:run_id>/emails", discovery.emails),
    path("api/discovery/<uuid:run_id>/<str:action>", discovery.progress),
    path("api/target", home.target),
    path("api/onboarding/wizard", setup_wizard.wizard),
    path("api/onboarding/test", setup_wizard.test_connection),
    path("api/onboarding/complete", setup_wizard.complete),
    path("api/chat/context", chat.workspace_context),
    path("api/chat/threads/<uuid:thread_id>/stream", chat.stream),
    path("api/chat/threads", chat.threads),
    path("api/chat/threads/<uuid:thread_id>", chat.thread),
    path("api/chat/threads/<uuid:thread_id>/messages", chat.message),
    path("api/chat/runs/<uuid:run_id>", chat.run),
    path("api/chat/runs/<uuid:run_id>/approval", chat.run, {"action": "approval"}),
    path("api/chat/runs/<uuid:run_id>/cancel", chat.run, {"action": "cancel"}),
    path("api/auth/login", accounts.sign_in),
    path("api/auth/logout", accounts.sign_out),
    path("api/auth/me", accounts.me),
    path("api/auth/password", accounts.change_password),
    path("api/auth/setup", accounts.setup_invitation),
    path("api/admin/users", accounts.admin_users),
    path("api/admin/users/<int:user_id>", accounts.admin_user),
    path("api/admin/users/<int:user_id>/invite", accounts.resend_invitation),
    path("api/onboarding", accounts.onboarding),
    path("api/tour", accounts.complete_tour),
    path("api/health", web.health),
    path("api/ready", web.ready),
    path("api/settings", web.runtime_settings),
    path("api/overview", web.overview),
    path("api/inbox", web.inbox),
    path("api/suppression", web.suppression),
    path("api/leads", web.leads),
    path("api/contacts", campaigns.add_contacts),
    path("api/contacts/<int:deal_id>", campaigns.contact),
    path("api/contacts/<int:deal_id>/email", crm.work_email),
    path("api/campaigns", campaigns.campaigns),
    path("api/campaigns/<uuid:campaign_id>", campaigns.campaign),
    path("api/campaigns/<uuid:campaign_id>/preview", campaigns.preview),
    path("api/campaigns/<uuid:campaign_id>/run", web.start_campaign),
    path("api/jobs", web.jobs),
    path("api/jobs/send", web.start_send),
]

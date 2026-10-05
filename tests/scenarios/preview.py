"""Seed a disposable local UI preview. Never run against a company database."""
import os
import django

if "leadzen-preview." not in os.environ.get("LEADZEN_DB", ""):
    raise SystemExit("A disposable leadzen-preview database is required")
django.setup()
from django.core.management import call_command
from django.utils import timezone
from leadzen.accounts.service import create_account
from leadzen.workspaces import initialize_workspace, workspace_scope
from leadzen.configuration import save_dashboard_settings
from leadzen.config.models import SiteConfig

call_command("migrate", verbosity=0, interactive=False)
password = "LeadZen-preview-only-3487!"
create_account(email="admin@preview.example", name="Preview administrator", password=password, is_admin=True, require_change=False)
create_account(email="employee@preview.example", name="Preview employee", password=password, require_change=False)
create_account(email="temporary@preview.example", name="Temporary employee", password=password)
user = create_account(email="ready@preview.example", name="Ready employee", password=password, require_change=False)
profile = user.leadzen_profile
initialize_workspace(profile)
with workspace_scope(profile):
    config = SiteConfig.load()
    config.product_docs, config.campaign_target = "Synthetic preview product", "Synthetic preview audience"
    config.save()
    save_dashboard_settings({"provider": "groq", "model": "openai/gpt-oss-120b", "mailbox_address": "sender@preview.example", "smtp_host": "smtp.zoho.com", "smtp_port": 587, "imap_host": "imap.zoho.com", "imap_port": 993}, llm_api_key="synthetic-preview-key", mailbox_password="synthetic-preview-password")
profile.workspace_name = "Preview outreach"
profile.purpose = "zyene_reviews"
profile.onboarding_completed_at = timezone.now()
profile.save()
print("Disposable preview ready")

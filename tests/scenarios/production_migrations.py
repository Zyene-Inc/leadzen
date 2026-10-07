"""Disposable clean/previous-release migration and preservation verification."""
import os
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()
if root.exists():
    raise SystemExit("Migration validation requires a new disposable directory")
root.mkdir(mode=0o700)
for key in list(os.environ):
    if key.startswith(("LEADZEN_", "OUTSEND_", "OPENOUTFIND_")) or key.endswith("API_KEY"):
        os.environ.pop(key)
os.environ.update(LEADZEN_DB=str(root / "control.sqlite3"),
                  LEADZEN_WORKSPACE_ROOT=str(root / "workspaces"),
                  LEADZEN_ENV="production",
                  DJANGO_SETTINGS_MODULE="leadzen.settings")

import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.management import call_command
from django.core.checks import run_checks
from django.utils import timezone

executor = MigrationExecutor(connection)
latest = executor.loader.graph.leaf_nodes()
previous = [(app, "0014_workspacecontext_chatthread_context_and_more" if app == "leadzen_config"
             else "0002_accountprofile_tour_completed_at_employeeinvitation" if app == "leadzen_accounts"
             else name) for app, name in latest]
executor.migrate(previous)
apps = executor.loader.project_state(previous).apps
user = apps.get_model("auth", "User").objects.create(username="synthetic-migration", email="migration@example.com")
completed = timezone.now()
profile = apps.get_model("leadzen_accounts", "AccountProfile").objects.create(user_id=user.pk, tour_completed_at=completed)
config = apps.get_model("leadzen_config", "SiteConfig").objects.create(product_docs="Synthetic preserved product", operator_email="sender@example.com")
runtime = apps.get_model("leadzen_config", "RuntimeSettings").objects.create(encrypted_secrets="synthetic-opaque-encrypted-credentials")
lead = apps.get_model("outsend_leads", "Lead").objects.create(lead_id="synthetic-preserved", email="lead@example.com", first_name="Synthetic")
deal = apps.get_model("outsend_leads", "Deal").objects.create(lead_id=lead.pk)
campaign = apps.get_model("leadzen_config", "EmailCampaign").objects.create(name="Synthetic preserved campaign", delay_timezone="Asia/Kolkata")
executor = MigrationExecutor(connection)
executor.migrate(latest)
apps = executor.loader.project_state(latest).apps
assert apps.get_model("auth", "User").objects.get(pk=user.pk).email == "migration@example.com"
saved_profile = apps.get_model("leadzen_accounts", "AccountProfile").objects.get(pk=profile.pk)
assert saved_profile.tour_completed_at == completed and saved_profile.tour_started_at == completed
assert apps.get_model("leadzen_config", "SiteConfig").objects.get(pk=config.pk).product_docs == "Synthetic preserved product"
saved_runtime = apps.get_model("leadzen_config", "RuntimeSettings").objects.get(pk=runtime.pk)
assert saved_runtime.lead_finder_provider == "bettercontact"
assert saved_runtime.encrypted_secrets == "synthetic-opaque-encrypted-credentials"
assert not apps.get_model("leadzen_config", "DiscoverySearch").objects.exists()
assert apps.get_model("outsend_leads", "Lead").objects.get(pk=lead.pk).email == "lead@example.com"
assert apps.get_model("outsend_leads", "Deal").objects.get(pk=deal.pk).lead_id == lead.pk
assert apps.get_model("leadzen_config", "EmailCampaign").objects.get(pk=campaign.pk).delay_timezone == "America/New_York"
assert not MigrationExecutor(connection).migration_plan(latest)
MigrationExecutor(connection).migrate(latest)
with connection.cursor() as cursor:
    assert cursor.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    assert cursor.execute("PRAGMA synchronous").fetchone() == (2,)
    assert cursor.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert not cursor.execute("PRAGMA foreign_key_check").fetchall()
assert not run_checks()
call_command("makemigrations", check=True, dry_run=True, verbosity=0)
print("Previous-release upgrade, data preservation, integrity, foreign keys, system checks and migration drift passed.")

# Exercise a second empty registry through every dependency/app migration.
connection.close()
connection.settings_dict["NAME"] = str(root / "clean.sqlite3")
executor = MigrationExecutor(connection)
executor.migrate(executor.loader.graph.leaf_nodes())
assert not MigrationExecutor(connection).migration_plan(executor.loader.graph.leaf_nodes())
with connection.cursor() as cursor:
    assert cursor.execute("PRAGMA synchronous").fetchone() == (2,)
    assert cursor.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert not cursor.execute("PRAGMA foreign_key_check").fetchall()
print("Clean database migrations and integrity passed; no production data accessed.")

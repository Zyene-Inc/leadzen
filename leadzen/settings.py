# leadzen/settings.py
"""LeadZen's shared registry for configuration, discovery, mail history, and jobs.

The finder and sender are reusable Django apps hosted in one database. Their
defaults define provider integration settings; LeadZen supplies durable runtime
configuration, the CLI, and the private dashboard API. Browser authentication is
handled by the separate Next.js dashboard, with token authentication on this API.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from openoutfind import defaults as find_defaults

# Before `django.setup()`, which is why it is a call here and not a name in a dict.
find_defaults.allow_async_unsafe()

ROOT_DIR = Path(__file__).resolve().parent.parent

BASE_DIR = ROOT_DIR


def state_dir(root: Path) -> Path:
    """Where the operator's own files live: the checkout, or `~/.leadzen` installed.

    Both children make the same choice for the same reason — from a wheel the package
    directory is inside site-packages, which is no place for a CRM, a mail history or a
    model cache, and may not be writable.
    """
    return root if (root / "manage.py").exists() else Path.home() / ".leadzen"


STATE_DIR = state_dir(ROOT_DIR)

# `--db PATH` sets LEADZEN_DB. One file: the finder's leads and the sender's mail log
# are rows in the same store, which is the whole point of hosting both app sets here.
DATABASE_PATH = Path(os.environ.get("LEADZEN_DB") or STATE_DIR / "data" / "db.sqlite3").expanduser()
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

from leadzen.upgrade import upgrade_database  # noqa: E402

upgrade_database(DATABASE_PATH)

# The sender resolves its own root at import time, and left alone it would answer
# `~/.openoutsend` — a second home appearing behind the operator's back for prompt lines
# nobody would think to look for. Set before `cold_outreach.defaults` is imported below,
# which is why that import is not at the top of the file.
os.environ.setdefault("OUTSEND_HOME", str(STATE_DIR))

from cold_outreach import defaults as send_defaults  # noqa: E402

# Spelled out rather than splatted from each child's `defaults.APPS`: this is the list
# that says what one process is, and reading it should not mean opening two other
# packages. The children's own lists stay the source of truth for *order* — both are in
# dependency order, and the sender's `emails` must follow its `leads`.
INSTALLED_APPS = [
    "leadzen.accounts.apps.AccountsConfig",
    # `django.contrib.sites` is the finder's (`setup_crm` seeds Site 1); `auth` is the
    # sender's (`emails.Message` points at `AUTH_USER_MODEL`) and holds the one operator
    # both children read.
    "django.contrib.sites",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    # This host's one model: the answers a person gave, which both children then read as
    # their environment. First, because the wizard writes it before either child runs.
    "leadzen.config.apps.ConfigAppConfig",
    "openoutfind.crm.apps.CrmConfig",
    "openoutfind.core.apps.CoreConfig",
    "cold_outreach.core",
    "cold_outreach.leads",
    "cold_outreach.emails",
]

# WSGI requires a stable configured key. Offline CLI/test invocations do not
# issue signed web capabilities and receive a process-local random default.
SECRET_KEY = os.environ.get("LEADZEN_SECRET_KEY") or secrets.token_urlsafe(64)

DEBUG = False

ROOT_URLCONF = "leadzen.urls"

MIDDLEWARE = [
    "leadzen.observability.RequestMetrics",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "leadzen.operations.maintenance.MaintenanceIntake",
]
APPEND_SLASH = False
SECURE_REFERRER_POLICY = "no-referrer"
SECURE_HSTS_SECONDS = 31536000
X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"leadzen_console": {"class": "logging.StreamHandler"}},
    "loggers": {"leadzen": {"handlers": ["leadzen_console"], "level": "INFO", "propagate": True}},
}

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("LEADZEN_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
    if host.strip()
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(DATABASE_PATH),
        # WAL lets `leadzen status` read while a find or send pass holds a write
        # lock; without it a concurrent read fails with "database is locked".
        "OPTIONS": {
            # FULL makes acknowledged production commits durable across a host
            # power loss; NORMAL may lose recent commits despite an intact DB.
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous="
            + ("FULL" if os.environ.get("LEADZEN_ENV") == "production" else "NORMAL") + ";",
            "transaction_mode": "IMMEDIATE",
        },
    }
}

# Splatted rather than spelled out — see the module docstring. The finder is handed this
# host's database path because this host owns it; the sender reads its own names from the
# environment, `OUTSEND_HOME` included, which is set above.
globals().update(find_defaults.app_settings(STATE_DIR, DATABASE_PATH))
globals().update(send_defaults.app_settings())

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATABASE_ROUTERS = ["leadzen.workspaces.WorkspaceRouter"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

SITE_ID = 1

# Stored UTC; every business date, schedule and daily total uses New York time.
from leadzen.timezone import TIME_ZONE

USE_TZ = True

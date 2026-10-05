"""Fail closed before starting the production WSGI application.

The CLI and disposable fixtures may use local defaults. A network service must
have an explicit database, encryption key, signing key, hosts and HTTPS origins.
Errors identify variable names only, never supplied configuration values.
"""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured


REQUIRED = (
    "LEADZEN_ENV",
    "LEADZEN_DB", "LEADZEN_WORKSPACE_ROOT", "LEADZEN_SETTINGS_KEY",
    "LEADZEN_SECRET_KEY", "LEADZEN_DASHBOARD_TOKEN", "LEADZEN_ALLOWED_HOSTS",
    "LEADZEN_PUBLIC_URL", "LEADZEN_DASHBOARD_ORIGINS",
)


def _https_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.port is not None
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or any(c.isspace() for c in value) or "\\" in value):
            return False
        host = parsed.hostname
        host.encode("ascii")
        if "%" in host:
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            labels = host.split(".")
            if (len(host) > 253 or len(labels) < 2
                    or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
                    # Numeric aliases can be normalized by browsers into local
                    # IPv4 addresses; a DNS suffix must contain a letter.
                    or not re.search(r"[a-z]", labels[-1])
                    or host == "localhost.localdomain"
                    or host.endswith((".localhost", ".localdomain", ".local", ".internal", ".lan", ".home", ".home.arpa", ".onion"))):
                return False
            canonical_host = host
        else:
            if not address.is_global or address.is_multicast:
                return False
            canonical_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
        # Reject uppercase, trailing dots, explicit :443/empty ports, alternate
        # address spellings and delimiter-only query/fragment components.
        return value == "https://" + canonical_host
    except (ValueError, TypeError, UnicodeError, AttributeError):
        return False


def validate_environment(environ=None) -> None:
    env = os.environ if environ is None else environ
    invalid = {name for name in REQUIRED if not env.get(name, "").strip()}
    if env.get("LEADZEN_ENV") != "production":
        invalid.add("LEADZEN_ENV")
    if env.get("DJANGO_SETTINGS_MODULE", "leadzen.settings") != "leadzen.settings":
        invalid.add("DJANGO_SETTINGS_MODULE")
    for name in ("LEADZEN_DB", "LEADZEN_WORKSPACE_ROOT"):
        if not Path(env.get(name, "")).is_absolute():
            invalid.add(name)
    try:
        Fernet(env.get("LEADZEN_SETTINGS_KEY", "").encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        invalid.add("LEADZEN_SETTINGS_KEY")
    for name, minimum in (("LEADZEN_SECRET_KEY", 50), ("LEADZEN_DASHBOARD_TOKEN", 32)):
        value = env.get(name, "")
        if len(value) < minimum or len(set(value)) < 8 or value != value.strip() or any(c.isspace() for c in value) or "replace-with" in value.lower():
            invalid.add(name)
    hosts = [v.strip() for v in env.get("LEADZEN_ALLOWED_HOSTS", "").split(",")]
    if not all(hosts) or any("*" in host or "/" in host or "://" in host or host == "testserver" for host in hosts):
        invalid.add("LEADZEN_ALLOWED_HOSTS")
    origin = env.get("LEADZEN_PUBLIC_URL", "")
    if not _https_origin(origin):
        invalid.add("LEADZEN_PUBLIC_URL")
    origins = [v.strip() for v in env.get("LEADZEN_DASHBOARD_ORIGINS", "").split(",")]
    if not all(_https_origin(v) for v in origins) or origin not in origins:
        invalid.add("LEADZEN_DASHBOARD_ORIGINS")
    if env.get("LEADZEN_MCP_ALLOW_LOCAL") == "1":
        invalid.add("LEADZEN_MCP_ALLOW_LOCAL")
    if invalid:
        raise ImproperlyConfigured("Missing or invalid production variables: " + ", ".join(sorted(invalid)))


if __name__ == "__main__":
    validate_environment()
    print("Production environment validation passed.")

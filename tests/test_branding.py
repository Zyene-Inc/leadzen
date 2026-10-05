"""Branding must survive a clean sender install and preserve existing records."""
import sqlite3
from types import SimpleNamespace

from leadzen import branding
from leadzen.upgrade import CURRENT_APP_LABEL, LEGACY_APP_LABEL, upgrade_database


def test_finder_banner_uses_leadzen_identity(capsys):
    from openoutfind.core.logging import print_banner
    branding.configure_finder()
    print_banner()
    assert capsys.readouterr().err.strip() == branding.PRODUCT_TITLE


def test_customer_message_omits_tool_footer_and_keeps_opt_out():
    from cold_outreach.emails import sender

    mailbox = SimpleNamespace(from_address="sender@example.com", signature="Karthik\nZyene Reviews")
    message = sender._build_message(mailbox, "customer@example.com", "Quick question", "How do you handle reviews?", None, None, None)
    body = message.get_content()
    assert "How do you handle reviews?" in body
    assert "Karthik\nZyene Reviews" in body
    assert sender.OPT_OUT_LINE in body
    assert "Sent with" not in body
    assert "mailto:sender+unsub@example.com" in message["List-Unsubscribe"]


def test_sender_branding_hook_covers_pristine_library():
    dependency = SimpleNamespace(ATTRIBUTION="original tool", _attribute=lambda body: body + "\noriginal tool")
    branding.configure_sender(dependency)
    assert dependency._attribute("customer message") == "customer message"
    assert dependency.ATTRIBUTION == ""


def test_database_upgrade_preserves_rows_and_creates_recovery_copy(tmp_path):
    database = tmp_path / "existing.sqlite3"
    table = LEGACY_APP_LABEL + "_siteconfig"
    with sqlite3.connect(database) as connection:
        connection.execute(f'CREATE TABLE "{table}" (id INTEGER PRIMARY KEY, value TEXT)')
        connection.execute(f'INSERT INTO "{table}" VALUES (1, ?)', ("retained-secret",))
        connection.execute("CREATE TABLE django_migrations (id INTEGER PRIMARY KEY, app TEXT, name TEXT)")
        connection.execute("INSERT INTO django_migrations VALUES (1, ?, '0001_initial')", (LEGACY_APP_LABEL,))
        connection.execute("CREATE TABLE django_content_type (id INTEGER PRIMARY KEY, app_label TEXT, model TEXT)")
        connection.execute("INSERT INTO django_content_type VALUES (1, ?, 'siteconfig')", (LEGACY_APP_LABEL,))
        connection.execute("CREATE TABLE lead_history (id INTEGER PRIMARY KEY, message TEXT)")
        connection.execute("INSERT INTO lead_history VALUES (42, 'saved message')")
    backup = upgrade_database(database)
    assert backup and backup.is_file()
    assert upgrade_database(database) is None
    with sqlite3.connect(database) as connection:
        assert connection.execute(f'SELECT value FROM "{CURRENT_APP_LABEL}_siteconfig"').fetchone() == ("retained-secret",)
        assert connection.execute("SELECT app FROM django_migrations").fetchone() == (CURRENT_APP_LABEL,)
        assert connection.execute("SELECT app_label FROM django_content_type").fetchone() == (CURRENT_APP_LABEL,)
        assert connection.execute("SELECT id, message FROM lead_history").fetchone() == (42, "saved message")
    with sqlite3.connect(backup) as connection:
        assert connection.execute(f'SELECT value FROM "{table}"').fetchone() == ("retained-secret",)


def test_current_database_needs_no_upgrade(tmp_path):
    database = tmp_path / "current.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(f'CREATE TABLE "{CURRENT_APP_LABEL}_siteconfig" (id INTEGER PRIMARY KEY)')
    assert upgrade_database(database) is None
    assert not database.with_name("current.before-leadzen.sqlite3").exists()


def test_incomplete_recovery_copy_blocks_upgrade(tmp_path):
    import pytest
    database = tmp_path / "existing.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(f'CREATE TABLE "{LEGACY_APP_LABEL}_siteconfig" (id INTEGER PRIMARY KEY)')
        connection.execute(f'INSERT INTO "{LEGACY_APP_LABEL}_siteconfig" VALUES (42)')
    database.with_name("existing.before-leadzen.sqlite3").touch()
    with pytest.raises(RuntimeError, match="recovery copy"):
        upgrade_database(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute(f'SELECT id FROM "{LEGACY_APP_LABEL}_siteconfig"').fetchall() == [(42,)]

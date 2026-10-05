# leadzen/config/apps.py
from django.apps import AppConfig


class ConfigAppConfig(AppConfig):
    name = "leadzen.config"
    # Namespaced like the children's, for the same reason: three app sets share one
    # registry and a bare `config` is exactly the label somebody else will want.
    label = "leadzen_config"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from leadzen.branding import configure_sender, configure_finder
        from leadzen.mailboxes import configure_mailbox_clock
        from leadzen.timezone import configure_business_clock
        from leadzen.production_logging import configure_production_logging

        configure_production_logging()
        configure_sender()
        configure_finder()
        configure_business_clock()
        configure_mailbox_clock()

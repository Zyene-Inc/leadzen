"""Keep untrusted provider diagnostics and customer data out of production logs."""
import logging
import os


PRIVATE_LOGGERS = ("cold_outreach", "openoutfind", "httpx", "httpx2", "httpcore", "httpcore2",
    "urllib3", "requests", "openai", "anthropic", "groq", "cohere", "google", "mistralai", "pydantic_ai",
    "django.request", "django.security")


def configure_production_logging():
    """Protect future child loggers as well as already imported dependencies.

    A filter on a parent logger does not filter records propagated by children.
    The record factory runs before any console/file handler can persist a raw
    prompt, mailbox identity or provider exception. Safe app summaries and the
    original event level/logger name remain available for incident triage.
    """
    original = logging.getLogRecordFactory()
    if getattr(original, "_leadzen_private", False):
        return

    def record_factory(*args, **kwargs):
        record = original(*args, **kwargs)
        private = any(record.name == name or record.name.startswith(name + ".") for name in PRIVATE_LOGGERS)
        if os.environ.get("LEADZEN_ENV") == "production" and private:
            record.msg = "Provider/dependency event. Check saved workspace status and connection settings."
            record.args = ()
            record.exc_info = record.exc_text = record.stack_info = None
        return record

    record_factory._leadzen_private = True
    logging.setLogRecordFactory(record_factory)

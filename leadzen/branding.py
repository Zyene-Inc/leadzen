"""Product identity at the boundary with the installed finder and sender."""
from __future__ import annotations

import re
from contextlib import contextmanager
from contextlib import redirect_stderr, redirect_stdout
import sys

PRODUCT_TITLE = "LeadZen by Zyene"

# These patterns are used only for output from older dependencies and saved job logs.
_LEGACY_DISPLAY = re.compile(r"Open\s*Outreach", re.IGNORECASE)


def display_text(value: str) -> str:
    return _LEGACY_DISPLAY.sub(PRODUCT_TITLE, value)


class _BrandedOutput:
    def __init__(self, stream):
        self.stream = stream

    def write(self, value: str):
        return self.stream.write(display_text(value))

    def __getattr__(self, name):
        return getattr(self.stream, name)


@contextmanager
def branded_output():
    """Present dependency messages with the company's product identity."""
    with redirect_stdout(_BrandedOutput(sys.stdout)), redirect_stderr(_BrandedOutput(sys.stderr)):
        yield


def configure_sender(sender=None) -> None:
    """Keep customer emails free of the dependency's fixed tool attribution.

    The pinned sender assembles messages through this hook. Apply the change at
    application startup so clean installs and worker processes behave consistently.
    The signature and unsubscribe behavior continue through the sender unchanged.
    """
    if sender is None:
        from cold_outreach.emails import sender
    if hasattr(sender, "_attribute"):
        sender._attribute = lambda body: body
    if hasattr(sender, "ATTRIBUTION"):
        sender.ATTRIBUTION = ""


def configure_finder() -> None:
    # ASCII lettering cannot be replaced by the ordinary text-output wrapper.
    from openoutfind.core import logging as finder_logging
    finder_logging.BANNER = f"\n{PRODUCT_TITLE}\n"

"""One business clock for LeadZen; persisted timestamps remain UTC instants."""
from zoneinfo import ZoneInfo

TIME_ZONE = "America/New_York"
NEW_YORK = ZoneInfo(TIME_ZONE)


def configure_business_clock():
    """Keep the pinned sender's CLI and imported clocks on New York time."""
    from django.utils import timezone
    from cold_outreach.core import business_time, sending_window
    from cold_outreach.emails.models import mailbox
    from cold_outreach.core.agents import outreach

    sending_window.operator_timezone = lambda: NEW_YORK
    mailbox.operator_timezone = sending_window.operator_timezone
    if not getattr(business_time.business_days_between, "_leadzen_clock", False):
        original = business_time.business_days_between

        def business_days_between(start, end):
            start = timezone.localtime(start, NEW_YORK) if timezone.is_aware(start) else start
            end = timezone.localtime(end, NEW_YORK) if timezone.is_aware(end) else end
            return original(start, end)

        business_days_between._leadzen_clock = True
        business_time.business_days_between = business_days_between
    outreach.business_days_between = business_time.business_days_between

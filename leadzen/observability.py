"""Safe request outcomes for production incident and latency monitoring."""
import logging
import os
import time
import uuid

logger = logging.getLogger("leadzen.requests")


class RequestMetrics:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        if os.environ.get("LEADZEN_ENV") == "production":
            request_id = uuid.uuid4().hex
            response["X-Request-ID"] = request_id
            match = getattr(request, "resolver_match", None)
            # The URL pattern contains placeholders, never submitted IDs/query/body.
            route = getattr(match, "route", None) or "unmatched"
            method = request.method if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else "OTHER"
            level = logging.ERROR if response.status_code >= 500 else logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(level, "request_id=%s method=%s route=%s status=%s duration_ms=%d",
                       request_id, method, route, response.status_code,
                       round((time.monotonic() - started) * 1000))
        return response

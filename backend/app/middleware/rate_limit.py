"""Shared rate limiter used by route modules.

Lives in its own module to avoid a circular import between `app.main` (which
constructs the FastAPI app and attaches the limiter) and individual route
modules that need to decorate handlers with `@limiter.limit(...)`."""

from fastapi import Request
from slowapi import Limiter


def _client_ip(request: Request) -> str:
    """Resolve the real client IP behind ALB + CloudFront.

    `request.client.host` returns the ALB's internal IP (10.0.x.x), so all
    traffic would share a single rate-limit bucket. The real client IP is in
    X-Forwarded-For (CloudFront writes it, then ALB appends the immediate
    client). The LEFTMOST entry is the original client."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # XFF format: "client, proxy1, proxy2" — first entry is the client
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Per-client-IP limiter. Limits are applied at decorator sites.
limiter = Limiter(key_func=_client_ip, default_limits=[])

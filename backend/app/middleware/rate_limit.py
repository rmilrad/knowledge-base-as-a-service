"""Shared rate limiter used by route modules.

Lives in its own module to avoid a circular import between `app.main` (which
constructs the FastAPI app and attaches the limiter) and individual route
modules that need to decorate handlers with `@limiter.limit(...)`."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Per-IP limiter. Limits are applied at decorator sites in route modules.
limiter = Limiter(key_func=get_remote_address, default_limits=[])

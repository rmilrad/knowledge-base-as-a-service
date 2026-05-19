import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.router import router
from app.middleware.rate_limit import limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import settings

    logger = logging.getLogger("kbaas")
    if not settings.jwt_secret_key:
        logger.critical("JWT_SECRET_KEY is not set — authentication will not work!")
        raise RuntimeError("JWT_SECRET_KEY must be set")
    logger.info("KBaaS backend starting")

    # Start the MCP session manager
    from app.mcp_app import mcp
    async with mcp.session_manager.run():
        logger.info("MCP session manager started")
        yield

    logger.info("KBaaS backend shutting down")


app = FastAPI(title="KBaaS", version="0.1.0", lifespan=lifespan)

# Hook up the rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger = logging.getLogger("kbaas.http")
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"{request.method} {request.url.path} -> {response.status_code}")
    return response

from app.config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# MCP endpoint: POST /api/mcp/{kb_id}
# Handles the MCP Streamable HTTP protocol with per-KB isolation
from app.mcp_app import mcp, _current_kb_id, _current_auth  # noqa: E402

# Trigger lazy initialization of the session manager
_mcp_starlette_app = mcp.streamable_http_app()

from mcp.server.fastmcp.server import StreamableHTTPASGIApp  # noqa: E402

_mcp_handler = StreamableHTTPASGIApp(mcp.session_manager)


@app.api_route("/api/mcp/{kb_id}", methods=["GET", "POST", "DELETE"])
async def mcp_endpoint(kb_id: str, request: Request):
    """MCP Streamable HTTP endpoint — one per knowledge base.

    Auth scoping: any KB-scoped API key passed in the Authorization header is
    enforced by the per-route `enforce_api_key_kb_scope` calls in the backend
    API endpoints that the MCP tools invoke (e.g. /api/kb/{kb_id}/query).
    A key for KB-A cannot be used at /api/mcp/KB-B-id."""
    # Validate kb_id is a UUID up front (cheap defense-in-depth)
    import uuid as _uuid
    try:
        _uuid.UUID(kb_id)
    except (ValueError, AttributeError):
        return Response(content=b'{"error":"Invalid knowledge base ID"}', status_code=400, media_type="application/json")

    # Set context vars so MCP tools know which KB and auth to use
    kb_token = _current_kb_id.set(kb_id)
    auth_header = request.headers.get("authorization", "")
    auth_token = _current_auth.set(auth_header)

    try:
        # Build an ASGI scope with path=/ for the MCP handler
        scope = dict(request.scope)
        scope["path"] = "/"

        # Collect response
        response_started = False
        status_code = 200
        response_headers: list[tuple[bytes, bytes]] = []
        body_parts: list[bytes] = []

        async def receive():
            return await request._receive()

        async def send(message):
            nonlocal response_started, status_code, response_headers
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        await _mcp_handler(scope, receive, send)

        headers_dict = {k.decode(): v.decode() for k, v in response_headers}
        return Response(
            content=b"".join(body_parts),
            status_code=status_code,
            headers=headers_dict,
        )
    finally:
        _current_kb_id.reset(kb_token)
        _current_auth.reset(auth_token)

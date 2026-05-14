import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router

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
    yield
    logger.info("KBaaS backend shutting down")


app = FastAPI(title="KBaaS", version="0.1.0", lifespan=lifespan)


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

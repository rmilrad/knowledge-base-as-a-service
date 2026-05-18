from fastapi import APIRouter

from app.api import admin, auth, knowledge_bases, documents, query, api_keys, public

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(knowledge_bases.router, prefix="/kb", tags=["knowledge_bases"])
router.include_router(documents.router, prefix="/kb", tags=["documents"])
router.include_router(query.router, prefix="/kb", tags=["query"])
router.include_router(api_keys.router, prefix="/kb", tags=["api_keys"])
router.include_router(public.router, prefix="/v1", tags=["public_api"])
router.include_router(admin.router, prefix="/admin", tags=["admin"])

from fastapi import APIRouter

from apis.v1.memory import router as memory_v1_router

router = APIRouter(prefix="/api")
router.include_router(memory_v1_router, prefix="/v1")

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.database import connect, disconnect, ensure_collections
from apis.router import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect()
    logger.info("MongoDB connected")
    created = await ensure_collections()
    if created:
        logger.info(f"Created collections: {created}")
    yield
    logger.info("Shutting down — waiting for background tasks to complete...")
    await disconnect()
    logger.info("MongoDB disconnected — shutdown complete")


app = FastAPI(title="Memory Service", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=18000)

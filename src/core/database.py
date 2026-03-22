from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from core.settings import settings

client: AsyncIOMotorClient = None
db: AsyncIOMotorDatabase = None


async def connect() -> None:
    global client, db
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]


async def disconnect() -> None:
    global client
    if client:
        client.close()


def get_db() -> AsyncIOMotorDatabase:
    return db


REQUIRED_COLLECTIONS = ["l1_daily", "l2_weekly", "l3_monthly"]


async def ensure_collections() -> list[str]:
    existing = await db.list_collection_names()
    created = []
    for name in REQUIRED_COLLECTIONS:
        if name not in existing:
            await db.create_collection(name)
            created.append(name)
    return created

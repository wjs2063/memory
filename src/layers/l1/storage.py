from datetime import datetime

from core.database import get_db
from core.timezone import KST, now_kst
from models.conversation import L1Memory

COLLECTION = "l1_daily"


async def store(user_id: str, human_message: str, ai_message: str) -> str:
    doc = L1Memory(
        user_id=user_id,
        data={"human_message": human_message, "ai_message": ai_message},
        created_at=now_kst().isoformat(),
    )
    result = await get_db()[COLLECTION].insert_one(doc.model_dump())
    return str(result.inserted_id)


async def get_daily(user_id: str, date: datetime) -> list[dict]:
    start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=KST)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    cursor = get_db()[COLLECTION].find(
        {
            "user_id": user_id,
            "created_at": {"$gte": start.isoformat(), "$lt": end.isoformat()},
        }
    )
    return await cursor.to_list(length=None)

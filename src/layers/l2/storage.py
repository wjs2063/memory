from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from core.database import get_db
from core.timezone import KST, now_kst
from models.conversation import L2Memory

COLLECTION = "l2_weekly"


class AnalysisAlgorithm(ABC):
    """L2 분석 알고리즘 인터페이스. MemoryBank 등 다양한 알고리즘으로 교체 가능."""

    @abstractmethod
    async def analyze(self, conversations: list[dict]) -> dict:
        ...


class DefaultAnalysis(AnalysisAlgorithm):
    """기본 분석: 대화 수와 원본 메시지 목록만 저장."""

    async def analyze(self, conversations: list[dict]) -> dict:
        return {
            "total_conversations": len(conversations),
            "messages": [c["data"] for c in conversations],
        }


_algorithm: AnalysisAlgorithm = DefaultAnalysis()


def set_algorithm(algo: AnalysisAlgorithm) -> None:
    global _algorithm
    _algorithm = algo


async def aggregate_week(user_id: str, week_start: datetime) -> str | None:
    from layers.l1.storage import COLLECTION as L1_COLLECTION

    start = week_start.replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=KST
    )
    end = start + timedelta(days=7)
    cursor = get_db()[L1_COLLECTION].find(
        {
            "user_id": user_id,
            "created_at": {"$gte": start.isoformat(), "$lt": end.isoformat()},
        }
    )
    conversations = await cursor.to_list(length=None)
    if not conversations:
        return None
    summary = await _algorithm.analyze(conversations)
    doc = L2Memory(
        user_id=user_id,
        data=summary,
        week_start=start.isoformat(),
        created_at=now_kst().isoformat(),
    )
    result = await get_db()[COLLECTION].insert_one(doc.model_dump())
    return str(result.inserted_id)


async def get_weekly(user_id: str, start: datetime, end: datetime) -> list[dict]:
    cursor = get_db()[COLLECTION].find(
        {
            "user_id": user_id,
            "week_start": {"$gte": start.isoformat(), "$lt": end.isoformat()},
        }
    )
    return await cursor.to_list(length=None)

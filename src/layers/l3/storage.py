from abc import ABC, abstractmethod
from datetime import datetime
from calendar import monthrange

from core.database import get_db
from core.timezone import KST, now_kst
from models.conversation import L3Memory

COLLECTION = "l3_monthly"


class AnalysisAlgorithm(ABC):
    @abstractmethod
    async def analyze(self, weekly_summaries: list[dict]) -> dict:
        ...


class DefaultAnalysis(AnalysisAlgorithm):
    async def analyze(self, weekly_summaries: list[dict]) -> dict:
        return {
            "total_weeks": len(weekly_summaries),
            "weekly_summaries": [s["data"] for s in weekly_summaries],
        }


_algorithm: AnalysisAlgorithm = DefaultAnalysis()


def set_algorithm(algo: AnalysisAlgorithm) -> None:
    global _algorithm
    _algorithm = algo


async def aggregate_month(user_id: str, year: int, month: int) -> str | None:
    from layers.l2.storage import COLLECTION as L2_COLLECTION

    start = datetime(year, month, 1, tzinfo=KST)
    _, last_day = monthrange(year, month)
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=KST)
    cursor = get_db()[L2_COLLECTION].find(
        {
            "user_id": user_id,
            "week_start": {"$gte": start.isoformat(), "$lt": end.isoformat()},
        }
    )
    weekly_summaries = await cursor.to_list(length=None)
    if not weekly_summaries:
        return None
    summary = await _algorithm.analyze(weekly_summaries)
    doc = L3Memory(
        user_id=user_id,
        data=summary,
        month_start=start.isoformat(),
        created_at=now_kst().isoformat(),
    )
    result = await get_db()[COLLECTION].insert_one(doc.model_dump())
    return str(result.inserted_id)

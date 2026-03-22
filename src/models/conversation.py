from pydantic import BaseModel, Field


class L1Memory(BaseModel):
    """L1 (daily) - 단일 Human/AI 메시지 쌍."""
    user_id: str
    data: dict
    kind: str = "daily"
    created_at: str  # isoformat KST


class L2Memory(BaseModel):
    """L2 (weekly) - 주간 패턴 분석 결과."""
    user_id: str
    data: dict
    kind: str = "weekly"
    week_start: str  # isoformat KST
    created_at: str  # isoformat KST


class L3Memory(BaseModel):
    """L3 (monthly) - 월간 패턴 분석 결과."""
    user_id: str
    data: dict
    kind: str = "monthly"
    month_start: str  # isoformat KST
    created_at: str  # isoformat KST

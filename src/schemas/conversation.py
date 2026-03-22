from pydantic import BaseModel


class ConversationIn(BaseModel):
    user_id: str
    human_message: str
    ai_message: str


class ConversationOut(BaseModel):
    id: str
    user_id: str
    human_message: str
    ai_message: str
    created_at: str  # isoformat KST


class WeeklySummaryOut(BaseModel):
    user_id: str
    week_start: str  # isoformat KST
    summary: dict
    created_at: str  # isoformat KST


class MonthlySummaryOut(BaseModel):
    user_id: str
    month_start: str  # isoformat KST
    summary: dict
    created_at: str  # isoformat KST
